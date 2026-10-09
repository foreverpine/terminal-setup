"""Run the shell template in isolated homes to verify extension points."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("zsh"), "requires zsh")
class ZshrcTests(unittest.TestCase):
    def test_environment_is_loaded_before_tools_and_local_overrides_still_run_last(self):
        with tempfile.TemporaryDirectory(prefix="zsh-server-") as tmp:
            home = Path(tmp)
            tools = home / "custom tools"
            tools.mkdir()
            starship = tools / "starship"
            starship.write_text(
                '#!/bin/sh\n'
                'printf "%s|%s\\n" "$http_proxy" "$PHASE" >> "$HOME/init.log"\n'
            )
            starship.chmod(0o755)
            (home / ".zshrc.env").write_text(
                'path=("$HOME/custom tools" $path)\n'
                'export http_proxy=http://proxy.example.invalid:8080\n'
                'export PHASE=early\n'
                'export PNPM_HOME="$HOME/custom pnpm"\n'
                '(( ENV_LOADS += 1 ))\n'
            )
            (home / ".zshrc.local").write_text(
                'export PHASE=late\nalias server_alias="echo server"\n'
            )
            result = subprocess.run(
                [shutil.which("zsh"), "-dfi", "-c",
                 'source "$1"; source "$1"; '
                 'print -r -- "$PHASE|$ENV_LOADS"; '
                 'print -rl -- $path; alias server_alias',
                 "zsh-test", str(REPO / "configs/.zshrc")],
                env={"HOME": tmp, "PATH": "/usr/bin:/bin", "TERM": "xterm"},
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home / "init.log").exists(), result.stderr)
            self.assertEqual((home / "init.log").read_text().splitlines(),
                             ["http://proxy.example.invalid:8080|early"] * 2)
            lines = result.stdout.splitlines()
            self.assertIn("late|2", lines)
            self.assertEqual(lines.count(str(tools)), 1)
            self.assertEqual(lines.count(str(home / "custom pnpm")), 1)
            self.assertIn("server_alias='echo server'", lines)


if __name__ == "__main__":
    unittest.main()
