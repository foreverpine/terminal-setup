"""Export a real-shaped server setup and restore it under another username."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("server_snapshot", REPO / "scripts/server_snapshot.py")
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "old-user"
        self.target = self.root / "new user"
        self.bundle = self.root / "bundle"
        files = {
            ".zshrc": '# portable shell\nsource "$HOME/.zshrc.env"\n',
            ".zshrc.env": 'export http_proxy=http://proxy.example.invalid:7890\n',
            ".zshrc.local": 'alias ll="ls -l"\n',
            ".config/starship.toml": 'format = "custom prompt"\n',
            ".config/zellij/config.kdl": 'theme "custom"\n',
            ".npmrc": f'prefix={self.source}/.npm-global\n',
            ".local/bin/ccm": f'#!/bin/sh\nexec "{self.source}/.local/share/ccm/ccm.sh" "$@"\n',
            ".local/bin/ccc": '#!/bin/sh\necho custom-ccc\n',
            ".local/share/ccm/ccm.sh": '#!/bin/sh\nprintf "%s\\n" "$HOME"\n',
            ".local/share/ccm/lang/en.json": '{}\n',
            ".ccm_config": 'provider-key-placeholder\n',
            ".ssh/id_ed25519": 'DO NOT COPY SSH KEY\n',
            ".codex/auth.json": 'DO NOT COPY LOGIN\n',
        }
        for name, content in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            if name.startswith(".local/") and not name.endswith(".json"):
                path.chmod(0o755)
        with patch.object(snapshot, "capture_versions", side_effect=lambda baseline, home: baseline):
            snapshot.export_snapshot(self.source, self.bundle)

    def test_export_is_self_contained_private_and_uses_actual_configs(self):
        self.assertTrue((self.bundle / "install.sh").exists())
        self.assertTrue((self.bundle / "repo/setup.sh").exists())
        self.assertEqual((self.bundle / "repo/configs/starship.toml").read_text(),
                         (self.source / ".config/starship.toml").read_text())
        self.assertEqual(self.bundle.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.bundle / "home/.ccm_config").stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.bundle / "home/.ssh").exists())
        self.assertFalse((self.bundle / "home/.codex/auth.json").exists())

    def test_config_migration_relocates_dependencies_and_is_repeatable(self):
        snapshot.apply_snapshot(self.bundle, self.target, config_only=True)
        result = subprocess.run([str(self.target / ".local/bin/ccm")],
                                env=dict(os.environ, HOME=str(self.target)),
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), str(self.target))
        self.assertIn(str(self.target), (self.target / ".npmrc").read_text())
        self.assertEqual((self.target / ".config/zellij/config.kdl").read_text(), 'theme "custom"\n')
        self.assertEqual((self.target / ".zshrc.env").stat().st_mode & 0o777, 0o600)
        mtime = (self.target / ".zshrc.env").stat().st_mtime_ns
        snapshot.apply_snapshot(self.bundle, self.target, config_only=True)
        self.assertEqual((self.target / ".zshrc.env").stat().st_mtime_ns, mtime)
        self.assertFalse((self.target / ".local/state/terminal-setup/backups").exists())

    def test_dry_run_never_creates_target_or_executes_installers(self):
        with patch.object(snapshot.subprocess, "run", side_effect=AssertionError("executed during preview")):
            snapshot.apply_snapshot(self.bundle, self.target, config_only=True, dry_run=True)
        self.assertFalse(self.target.exists())

    def test_full_install_uses_the_bundle_and_preserves_migrated_config(self):
        # A full install must not sync the old username back over relocated files.
        setup = self.bundle / "repo/setup.sh"
        setup.write_text('#!/bin/bash\nset -e\n[[ "$1" == --server && "$2" == --keep-config ]]\n'
                         '[[ -f "$HOME/.zshrc.env" && -x "$HOME/.local/bin/ccm" ]]\n')
        with patch.dict(os.environ, HOME=str(self.target)):
            snapshot.apply_snapshot(self.bundle, self.target)
        self.assertIn(str(self.target), (self.target / ".local/bin/ccm").read_text())

    def test_invalid_parent_directory_fails_before_any_write(self):
        self.target.mkdir()
        (self.target / ".config").write_text("not a directory")
        with self.assertRaises(ValueError):
            snapshot.apply_snapshot(self.bundle, self.target, config_only=True)
        self.assertFalse((self.target / ".zshrc.env").exists())

    def test_changed_config_is_backed_up_before_replacement(self):
        self.target.mkdir()
        (self.target / ".zshrc.local").write_text("# target customizations\n")
        snapshot.apply_snapshot(self.bundle, self.target, config_only=True)
        backups = list((self.target / ".local/state/terminal-setup/backups").glob("*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / ".zshrc.local").read_text(), "# target customizations\n")

    def test_corrupt_or_unsafe_bundle_fails_before_deployment(self):
        manifest_path = self.bundle / "manifest.json"
        original = manifest_path.read_text()
        data = json.loads(original)
        data["files"]["../escape"] = next(iter(data["files"].values()))
        manifest_path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            snapshot.apply_snapshot(self.bundle, self.target, config_only=True)
        manifest_path.write_text(original)
        (self.bundle / "home/.zshrc.env").write_text("corrupt transfer\n")
        with self.assertRaises(ValueError):
            snapshot.apply_snapshot(self.bundle, self.target, config_only=True)
        self.assertFalse(self.target.exists())

    def test_destination_symlink_is_rejected_before_any_write(self):
        self.target.mkdir()
        (self.target / ".local").symlink_to(self.source / ".local", target_is_directory=True)
        with self.assertRaises(ValueError):
            snapshot.apply_snapshot(self.bundle, self.target, config_only=True)
        self.assertFalse((self.target / ".zshrc").exists())


if __name__ == "__main__":
    unittest.main()
