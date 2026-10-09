"""Exercise migration/rollback in temporary homes, without touching the real HOME."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="terminal-setup-test-")
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "new server home"

    def run_sync(self, *args, repo=REPO, check=True):
        return subprocess.run(
            ["bash", str(repo / "sync.sh"), "--target", str(self.target), *args],
            text=True, capture_output=True, check=check,
        )

    def backups(self):
        return list((self.target / ".local/state/terminal-setup/backups").glob("*"))

    def test_first_install_and_repeat_preserve_local_settings(self):
        self.run_sync()
        early = self.target / ".zshrc.env"
        self.assertEqual(early.stat().st_mode & 0o777, 0o600)
        early.write_text('export PATH="$HOME/server/bin:$PATH"\n')
        local = self.target / ".zshrc.local"
        self.assertEqual(local.stat().st_mode & 0o777, 0o600)
        local.write_text("export MACHINE_ONLY=keep-me\n")
        original_mtime = (self.target / ".zshrc").stat().st_mtime_ns
        result = self.run_sync()
        self.assertIn("already up to date", result.stdout)
        self.assertEqual((self.target / ".zshrc").stat().st_mtime_ns, original_mtime)
        self.assertEqual(local.read_text(), "export MACHINE_ONLY=keep-me\n")
        self.assertEqual(early.read_text(), 'export PATH="$HOME/server/bin:$PATH"\n')
        self.assertEqual(self.backups(), [])

    def make_profile(self):
        profile = Path(self.temp.name) / "server profile"
        profile.mkdir()
        (profile / ".zshrc.env").write_text('export PATH="$HOME/server/bin:$PATH"\n')
        (profile / ".zshrc.local").write_text('alias server="echo server"\n')
        return profile

    def test_import_profile_is_private_repeatable_and_dry_run_is_read_only(self):
        profile = self.make_profile()
        self.run_sync("--local-dir", str(profile), "--dry-run")
        self.assertFalse(self.target.exists())
        self.run_sync("--local-dir", str(profile))
        for name in (".zshrc.env", ".zshrc.local"):
            deployed = self.target / name
            self.assertEqual(deployed.read_text(), (profile / name).read_text())
            self.assertEqual(deployed.stat().st_mode & 0o777, 0o600)
        result = self.run_sync("--local-dir", str(profile))
        self.assertIn("already up to date", result.stdout)
        self.assertEqual(self.backups(), [])

    def test_conflicting_profile_fails_before_changing_any_file(self):
        profile = self.make_profile()
        self.target.mkdir()
        (self.target / ".zshrc.local").write_text("# keep local\n")
        (self.target / ".zshrc").write_text("# keep zsh\n")
        result = self.run_sync("--local-dir", str(profile), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicts", result.stderr)
        self.assertEqual((self.target / ".zshrc.local").read_text(), "# keep local\n")
        self.assertEqual((self.target / ".zshrc").read_text(), "# keep zsh\n")
        self.assertFalse((self.target / ".zshrc.env").exists())
        self.assertEqual(self.backups(), [])

    def test_invalid_profile_fails_before_deployment(self):
        if not shutil.which("zsh"):
            self.skipTest("requires zsh")
        profile = self.make_profile()
        (profile / ".zshrc.env").write_text("if then\n")
        result = self.run_sync("--local-dir", str(profile), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("parse error", result.stderr)
        self.assertFalse(self.target.exists())

    def test_partial_profile_seeds_the_other_hook_and_preserves_existing_symlinks(self):
        profile = self.make_profile()
        (profile / ".zshrc.local").unlink()
        self.target.mkdir()
        linked = self.target / "environment.zsh"
        shutil.copy2(profile / ".zshrc.env", linked)
        (self.target / ".zshrc.env").symlink_to(linked.name)
        self.run_sync("--local-dir", str(profile))
        self.assertTrue((self.target / ".zshrc.env").is_symlink())
        self.assertEqual((self.target / ".zshrc.local").read_text(),
                         (REPO / "configs/.zshrc.local.example").read_text())

    def test_empty_or_missing_profile_is_rejected(self):
        profile = Path(self.temp.name) / "profile"
        for exists in (False, True):
            if exists:
                profile.mkdir()
            result = self.run_sync("--local-dir", str(profile), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.target.exists())

    def test_install_imports_hooks_before_delegating_to_installer(self):
        profile = self.make_profile()
        repo = Path(self.temp.name) / "repo"
        shutil.copytree(REPO / "configs", repo / "configs")
        shutil.copy2(REPO / "sync.sh", repo / "sync.sh")
        # Simulate only the installer's config deployment, without sudo/network.
        (repo / "setup.sh").write_text(
            '#!/bin/bash\nset -e\n[[ "$1" == --server ]]\n'
            '[[ -f "$HOME/.zshrc.env" && -f "$HOME/.zshrc.local" ]]\n'
            'bash "$(dirname "$0")/sync.sh"\n'
        )
        subprocess.run(
            ["bash", str(repo / "sync.sh"), "--install", "--local-dir", str(profile)],
            env=dict(os.environ, HOME=str(self.target)), check=True,
            capture_output=True, text=True, timeout=15,
        )
        self.assertTrue((self.target / ".zshrc").exists())
        for name in (".zshrc.env", ".zshrc.local"):
            self.assertEqual((self.target / name).read_text(), (profile / name).read_text())

    def test_local_hook_directory_fails_before_overwriting_managed_files(self):
        (self.target / ".zshrc.env").mkdir(parents=True)
        (self.target / ".zshrc").write_text("# keep\n")
        result = self.run_sync(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.target / ".zshrc").read_text(), "# keep\n")
        self.assertFalse((self.target / ".zshrc.local").exists())

    def test_backup_and_restore_existing_configuration(self):
        (self.target / ".config").mkdir(parents=True)
        old_zsh = "# custom shell configuration\n"
        old_prompt = 'format = "$directory"\n'
        (self.target / ".zshrc").write_text(old_zsh)
        (self.target / ".config/starship.toml").write_text(old_prompt)
        self.run_sync()
        backup = self.backups()[0]
        self.assertEqual((backup / ".zshrc").read_text(), old_zsh)
        self.run_sync("--restore", str(backup))
        self.assertEqual((self.target / ".zshrc").read_text(), old_zsh)
        self.assertEqual((self.target / ".config/starship.toml").read_text(), old_prompt)
        self.assertEqual(len(self.backups()), 2)  # rollback is itself reversible

    def test_dry_run_never_creates_target_or_backups(self):
        self.run_sync("--dry-run")
        self.assertFalse(self.target.exists())
        self.run_sync()
        (self.target / ".zshrc").write_text("# changed\n")
        self.run_sync("--dry-run")
        self.assertEqual((self.target / ".zshrc").read_text(), "# changed\n")
        self.assertEqual(self.backups(), [])

    def test_existing_symlink_target_is_not_overwritten_and_link_can_be_restored(self):
        self.target.mkdir()
        original = self.target / "personal.zsh"
        original.write_text("# external dotfiles\n")
        (self.target / ".zshrc").symlink_to("personal.zsh")
        self.run_sync()
        self.assertEqual(original.read_text(), "# external dotfiles\n")
        self.assertFalse((self.target / ".zshrc").is_symlink())
        self.run_sync("--restore", str(self.backups()[0]))
        self.assertTrue((self.target / ".zshrc").is_symlink())
        self.assertEqual(os.readlink(self.target / ".zshrc"), "personal.zsh")

    def test_missing_local_symlink_target_is_preserved(self):
        self.target.mkdir()
        (self.target / ".zshrc.local").symlink_to("machine-not-mounted.zsh")
        (self.target / ".zshrc.env").symlink_to("environment-not-mounted.zsh")
        self.run_sync()
        self.assertTrue((self.target / ".zshrc.local").is_symlink())
        self.assertFalse((self.target / "machine-not-mounted.zsh").exists())
        self.assertTrue((self.target / ".zshrc.env").is_symlink())
        self.assertFalse((self.target / "environment-not-mounted.zsh").exists())

    def test_invalid_destination_fails_before_overwriting_other_files(self):
        (self.target / ".config/starship.toml").mkdir(parents=True)
        (self.target / ".zshrc").write_text("# keep\n")
        result = self.run_sync(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.target / ".zshrc").read_text(), "# keep\n")
        self.assertEqual(self.backups(), [])

    def test_invalid_template_fails_before_deployment(self):
        if not shutil.which("zsh"):
            self.skipTest("requires zsh")
        repo = Path(self.temp.name) / "repo"
        shutil.copytree(REPO / "configs", repo / "configs")
        shutil.copy2(REPO / "sync.sh", repo / "sync.sh")
        (repo / "configs/.zshrc").write_text("if then\n")
        result = self.run_sync(repo=repo, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())

    def test_pull_applies_updated_script_and_templates_from_local_remote(self):
        root = Path(self.temp.name)
        remote, author, client = (root / n for n in ("remote.git", "author", "client"))

        def git(*args, cwd=None):
            return subprocess.run(["git", *map(str, args)], cwd=cwd, check=True,
                                  text=True, capture_output=True)

        git("init", "--bare", remote)
        git("clone", remote, author)
        shutil.copytree(REPO / "configs", author / "configs")
        shutil.copy2(REPO / "sync.sh", author / "sync.sh")
        git("config", "user.name", "Sync Test", cwd=author)
        git("config", "user.email", "sync-test@example.invalid", cwd=author)
        git("add", ".", cwd=author)
        git("commit", "-m", "initial", cwd=author)
        git("push", "origin", "HEAD", cwd=author)
        git("clone", remote, client)
        with (author / "configs/.zshrc").open("a") as f:
            f.write("\n# synced update\n")
        script = author / "sync.sh"
        script.write_text(script.read_text().replace(
            "Configuration ready.", "Updated script ran. Configuration ready."))
        git("add", ".", cwd=author)
        git("commit", "-m", "update", cwd=author)
        git("push", "origin", "HEAD", cwd=author)
        profile = self.make_profile()
        result = self.run_sync("--pull", "--local-dir", str(profile), repo=client)
        self.assertIn("Updated script ran", result.stdout)
        self.assertIn("# synced update", (self.target / ".zshrc").read_text())
        self.assertEqual((self.target / ".zshrc.env").read_text(),
                         (profile / ".zshrc.env").read_text())
        with (client / "configs/.zshrc").open("a") as f:
            f.write("# uncommitted\n")
        result = self.run_sync("--pull", repo=client, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local changes", result.stderr)

    def test_install_preview_does_not_execute_privileged_or_network_commands(self):
        stubs = Path(self.temp.name) / "bin"
        stubs.mkdir()
        for name in ("sudo", "curl", "wget", "git", "chsh", "apt-get"):
            command = stubs / name
            command.write_text('#!/bin/sh\necho "UNEXPECTED EXECUTION" >&2\nexit 99\n')
            command.chmod(0o755)
        env = dict(os.environ, PATH=f"{stubs}:{os.environ['PATH']}")
        result = subprocess.run(["bash", str(REPO / "sync.sh"), "--install", "--dry-run"],
                                env=env, stdin=subprocess.DEVNULL, text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("UNEXPECTED EXECUTION", result.stderr)
        self.assertNotIn("Install fnm", result.stdout)
        self.assertNotIn("Install Zellij?", result.stdout)
        self.assertNotIn("Ghostty config deployed", result.stdout)


if __name__ == "__main__":
    unittest.main()
