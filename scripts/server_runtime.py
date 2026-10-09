#!/usr/bin/env python3
"""Install missing user-level tools from the recorded server baseline."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]
CORE_COMMANDS = "zsh starship zoxide fzf eza bat fd rg btop jq tldr delta lazygit git curl wget rsync unzip zip tmux python3 pip3".split()
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.]+)?")
COMMAND = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")


def load_baseline(path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or set(data) != {"node", "fnm", "uv", "zellij", "npm", "custom_commands"}:
        raise ValueError("Unexpected baseline fields")
    for name in ("node", "fnm", "uv", "zellij"):
        if not isinstance(data[name], str) or not VERSION.fullmatch(data[name]):
            raise ValueError(f"Invalid version for {name}")
    if not isinstance(data["npm"], dict) or not isinstance(data["custom_commands"], list):
        raise ValueError("Invalid package/command list")
    for command, package in data["npm"].items():
        if (not COMMAND.fullmatch(command) or not isinstance(package, dict)
                or set(package) != {"package", "version"}
                or not isinstance(package["package"], str) or not isinstance(package["version"], str)
                or not re.fullmatch(r"(?:@[a-z0-9._-]+/)?[a-z0-9][a-z0-9._-]*", package["package"])
                or not VERSION.fullmatch(package["version"])):
            raise ValueError(f"Invalid npm package for {command}")
    if any(not isinstance(c, str) or not COMMAND.fullmatch(c) for c in data["custom_commands"]):
        raise ValueError("Invalid custom command")
    return data


class Installer:
    def __init__(self, home, baseline, dry_run=False, arch=None):
        self.home = Path(home)
        self.baseline = baseline
        self.dry_run = dry_run
        self.arch = arch or platform.machine()
        if self.arch not in ("x86_64", "aarch64"):
            raise ValueError(f"Server baseline supports Linux x86_64/aarch64, got {self.arch}")
        self.plan = []
        self.bin = self.home / ".local/bin"
        self.fnm_dir = Path(os.environ.get("FNM_DIR", str(self.home / ".local/share/fnm")))
        self.node_bin = self.fnm_dir / f"node-versions/v{baseline['node']}/installation/bin"
        paths = [self.bin, self.home / ".npm-global/bin", self.home / ".opencode/bin",
                 self.fnm_dir, self.node_bin, self.home / "miniconda3/condabin"]
        self.env = dict(os.environ, HOME=str(self.home), FNM_DIR=str(self.fnm_dir),
                        PATH=os.pathsep.join(map(str, paths)) + os.pathsep + os.environ.get("PATH", ""))

    def which(self, command):
        return shutil.which(command, path=self.env["PATH"])

    def compatible_node(self):
        executable = self.which("node")
        if not executable or not self.which("npm"):
            return False
        try:
            result = subprocess.run([executable, "--version"], env=self.env,
                                    capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return False
        version = re.fullmatch(r"v?(\d+)\.\d+\.\d+", result.stdout.strip())
        return (result.returncode == 0 and version is not None
                and int(version[1]) >= int(self.baseline["node"].split(".")[0]))

    def run(self, *args):
        args = list(map(str, args))
        self.plan.append(shlex.join(args))
        print(("[dry-run] " if self.dry_run else "Run: ") + self.plan[-1], flush=True)
        if not self.dry_run:
            subprocess.run(args, env=self.env, check=True)

    def binaries(self, url, names):
        if self.dry_run:
            self.plan.append(f"Download {url} -> {self.bin} ({', '.join(names)})")
            print("[dry-run] " + self.plan[-1], flush=True)
            return
        with tempfile.TemporaryDirectory(prefix="terminal-tools-") as tmp:
            archive = Path(tmp) / "archive"
            self.run("curl", "--fail", "--location", "--retry", "2", "--proto", "=https", url, "-o", archive)
            # Copy only regular executable members; never extract paths or links.
            for name in names:
                if url.endswith(".zip"):
                    with zipfile.ZipFile(archive) as handle:
                        content = handle.read(name)
                else:
                    with tarfile.open(archive) as handle:
                        members = [m for m in handle.getmembers() if m.isfile() and Path(m.name).name == name]
                        if len(members) != 1:
                            raise ValueError(f"Expected one {name} executable in {url}")
                        content = handle.extractfile(members[0]).read()
                self.bin.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=self.bin)
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(content)
                        os.fchmod(output.fileno(), 0o755)
                    os.replace(temporary, self.bin / name)
                finally:
                    Path(temporary).unlink(missing_ok=True)

    def install(self):
        b = self.baseline
        if not self.which("fnm"):
            asset = "fnm-linux" if self.arch == "x86_64" else "fnm-arm64"
            self.binaries(f"https://github.com/Schniz/fnm/releases/download/v{b['fnm']}/{asset}.zip", ["fnm"])
        changed_node = not self.compatible_node()
        if changed_node:
            self.run("fnm", "install", b["node"])
            self.run("fnm", "default", b["node"])
            self.env["PATH"] = str(self.node_bin) + os.pathsep + self.env["PATH"]
        for command, package in b["npm"].items():
            executable = self.which(command)
            resolved = str(Path(executable).resolve()) if executable else ""
            old_node_global = changed_node and ("/node-versions/" in resolved or "/.nvm/versions/" in resolved)
            if not executable or old_node_global:
                self.run("npm", "install", "--global", "--prefix", self.home / ".npm-global",
                         f"{package['package']}@{package['version']}")
        if not self.which("uv") or not self.which("uvx"):
            triple = f"{self.arch}-unknown-linux-gnu"
            self.binaries(f"https://github.com/astral-sh/uv/releases/download/{b['uv']}/uv-{triple}.tar.gz", ["uv", "uvx"])
        if not self.which("zellij"):
            triple = f"{self.arch}-unknown-linux-musl"
            self.binaries(f"https://github.com/zellij-org/zellij/releases/download/v{b['zellij']}/zellij-{triple}.tar.gz", ["zellij"])
        if not self.which("conda"):
            destination = self.home / "miniconda3"
            if destination.exists():
                raise ValueError(f"Conda directory exists but conda is unavailable: {destination}")
            url = f"https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-{self.arch}.sh"
            if self.dry_run:
                self.plan.append(f"Download {url}; bash installer -b -p {destination}")
                print("[dry-run] " + self.plan[-1], flush=True)
            else:
                with tempfile.TemporaryDirectory(prefix="terminal-conda-") as tmp:
                    script = Path(tmp) / "miniconda.sh"
                    self.run("curl", "--fail", "--location", "--retry", "2", "--proto", "=https", url, "-o", script)
                    self.run("bash", script, "-b", "-p", destination)

    def missing(self):
        commands = [*CORE_COMMANDS, "fnm", "node", "npm", "uv", "uvx", "conda", "zellij",
                    *self.baseline["npm"], *self.baseline["custom_commands"]]
        return [name for name in dict.fromkeys(commands) if not self.which(name)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true", help="Report missing tools without installing")
    parser.add_argument("--baseline", type=Path, default=REPO / "configs/server-baseline.json")
    args = parser.parse_args()
    installer = Installer(Path.home(), load_baseline(args.baseline), args.dry_run)
    if not args.check:
        installer.install()
    if not args.dry_run:
        missing = installer.missing()
        if missing:
            print("Missing baseline commands: " + ", ".join(missing), file=sys.stderr)
            return 1
        if not installer.compatible_node():
            print(f"Node does not meet baseline {installer.baseline['node']}; run ./sync.sh --install", file=sys.stderr)
            return 1
        print("Server baseline commands are available.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
