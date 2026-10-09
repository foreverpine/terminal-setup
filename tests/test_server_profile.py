"""The Git-only checkout must carry all baseline configuration dependencies."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class RepositoryInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="github-baseline-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "new account"

    def install(self, *args):
        return subprocess.run(["bash", str(REPO / "install.sh"), "--config-only", "--target", str(self.home), *args],
                              text=True, capture_output=True, check=True)

    def test_clone_install_deploys_real_defaults_and_portable_ccm_commands(self):
        self.install()
        self.assertTrue((self.home / ".config/zellij/config.kdl").is_file())
        self.assertTrue((self.home / ".claude/statusline-command.sh").is_file())
        self.assertTrue((self.home / ".local/share/ccm/lang/en.json").is_file())
        env = dict(os.environ, HOME=str(self.home), PATH=f"{self.home}/.local/bin:/usr/bin:/bin")
        result = subprocess.run([str(self.home / ".local/bin/ccm"), "--help"],
                                env=env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["zsh", "-df", "-c",
                                 'source "$HOME/.zshrc"; (( $+functions[ccm] && $+functions[ccc] ))'],
                                env=env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_credentials_and_application_settings_are_preserved(self):
        for name in [".ccm_config", ".claude/settings.json", ".codex/config.toml", ".npmrc"]:
            path = self.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("keep my server settings\n")
        self.install()
        for name in [".ccm_config", ".claude/settings.json", ".codex/config.toml", ".npmrc"]:
            self.assertEqual((self.home / name).read_text(), "keep my server settings\n")

    def test_preview_writes_nothing(self):
        self.install("--dry-run")
        self.assertFalse(self.home.exists())

    def test_repeat_install_does_not_rewrite_identical_files(self):
        self.install()
        path = self.home / ".config/terminal-setup/ccm.zsh"
        stamp = path.stat().st_mtime_ns
        self.install()
        self.assertEqual(path.stat().st_mtime_ns, stamp)

    def test_provider_credentials_are_empty_by_default_and_accept_environment_values(self):
        self.install()
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin"}
        result = subprocess.run(["bash", "-c", 'source "$HOME/.ccm_config"; [[ -z "$DEEPSEEK_API_KEY$GLM_API_KEY$CLAUDE_API_KEY" ]]'],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["bash", "-c", 'source "$HOME/.ccm_config"; [[ "$DEEPSEEK_API_KEY" == provided-for-test ]]'],
                                env=dict(env, DEEPSEEK_API_KEY="provided-for-test"), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_snapshot_install_does_not_reconfigure_existing_git_settings(self):
        stubs = Path(self.temp.name) / "bin"
        stubs.mkdir()
        (stubs / "delta").write_text("#!/bin/sh\nexit 0\n")
        (stubs / "delta").chmod(0o755)
        result = subprocess.run(["bash", str(REPO / "setup.sh"), "--server", "--keep-config", "--dry-run"],
                                env=dict(os.environ, HOME=str(self.home), PATH=f"{stubs}:/usr/bin:/bin"),
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("git config --global", result.stdout)
        self.assertNotIn("apt-get install -y git-delta", result.stdout)
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
