"""Verify the baseline installer without installing software on the test host."""
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import tarfile
import subprocess
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("server_runtime", REPO / "scripts/server_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "new home"
        self.baseline = runtime.load_baseline(REPO / "configs/server-baseline.json")

    def test_clean_server_plan_contains_runtimes_and_all_requested_apps_without_writes(self):
        with patch.object(runtime.shutil, "which", return_value=None), \
                patch.object(runtime.subprocess, "run", side_effect=AssertionError("executed during preview")):
            installer = runtime.Installer(self.home, self.baseline, dry_run=True, arch="aarch64")
            installer.install()
        plan = "\n".join(installer.plan)
        for expected in ["fnm", "24.16.0", "pnpm", "uv", "Miniconda3", "zellij",
                         "@anthropic-ai/claude-code", "@openai/codex", "opencode-ai"]:
            self.assertIn(expected, plan)
        self.assertIn("aarch64", plan)
        self.assertNotIn("x86_64", plan)
        self.assertFalse(self.home.exists())

    def test_installed_tools_are_preserved_without_reinstalling(self):
        with patch.object(runtime.shutil, "which", side_effect=lambda name, **kw: f"/bin/{name}"), \
                patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "v24.16.0\n")):
            installer = runtime.Installer(self.home, self.baseline, dry_run=True)
            installer.install()
        self.assertEqual(installer.plan, [])

    def test_old_system_node_is_replaced_by_a_compatible_fnm_runtime(self):
        with patch.object(runtime.shutil, "which", side_effect=lambda name, **kw: f"/bin/{name}"), \
                patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "v18.19.1\n")):
            installer = runtime.Installer(self.home, self.baseline, dry_run=True)
            installer.install()
        self.assertIn("fnm install 24.16.0", installer.plan)
        self.assertIn("fnm default 24.16.0", installer.plan)

    def test_changing_node_reinstalls_cli_from_old_node_globals_into_stable_prefix(self):
        old_cli = self.home / ".nvm/versions/node/v18.19.1/bin/claude"
        with patch.object(runtime.shutil, "which", side_effect=lambda name, **kw: str(old_cli) if name == "claude" else f"/bin/{name}"), \
                patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "v18.19.1\n")):
            installer = runtime.Installer(self.home, self.baseline, dry_run=True)
            installer.install()
        self.assertTrue(any("@anthropic-ai/claude-code" in command and ".npm-global" in command for command in installer.plan))

    def test_missing_dependency_fails_the_final_check(self):
        with patch.object(runtime.shutil, "which", side_effect=lambda name, **kw: None if name == "uv" else f"/bin/{name}"):
            self.assertEqual(runtime.Installer(self.home, self.baseline).missing(), ["uv"])

    def test_archive_installs_only_the_requested_executable_without_extracting_paths(self):
        archive = Path(self.temp.name) / "release.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            for name, content in [("uv-linux/uv", b"#!/bin/sh\necho uv\n"), ("../../outside", b"unexpected")]:
                member = tarfile.TarInfo(name)
                member.size = len(content)
                handle.addfile(member, io.BytesIO(content))
        installer = runtime.Installer(self.home, self.baseline)
        def download(*args):
            Path(args[-1]).write_bytes(archive.read_bytes())
        with patch.object(installer, "run", side_effect=download):
            installer.binaries("https://example.invalid/uv.tar.gz", ["uv"])
        self.assertEqual((self.home / ".local/bin/uv").stat().st_mode & 0o777, 0o755)
        self.assertFalse((Path(self.temp.name) / "outside").exists())

    def test_partial_conda_install_is_reported_instead_of_overwritten(self):
        (self.home / "miniconda3").mkdir(parents=True)
        with patch.object(runtime.shutil, "which", side_effect=lambda name, **kw: None if name == "conda" else f"/bin/{name}"), \
                patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "v24.16.0\n")):
            with self.assertRaisesRegex(ValueError, "Conda directory exists"):
                runtime.Installer(self.home, self.baseline).install()

    def test_invalid_baseline_cannot_inject_download_paths_or_package_options(self):
        path = Path(self.temp.name) / "baseline.json"
        for key, value in [("node", "../../bad"), ("uv", "1; touch bad")]:
            content = dict(self.baseline, **{key: value})
            path.write_text(json.dumps(content))
            with self.assertRaises(ValueError):
                runtime.load_baseline(path)
        content = json.loads(json.dumps(self.baseline))
        content["npm"]["codex"]["package"] = "--script=bad"
        path.write_text(json.dumps(content))
        with self.assertRaises(ValueError):
            runtime.load_baseline(path)


if __name__ == "__main__":
    unittest.main()
