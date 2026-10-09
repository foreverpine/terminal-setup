#!/usr/bin/env python3
"""Export an installable server baseline, including local configuration dependencies."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from server_runtime import Installer, load_baseline

REPO = Path(__file__).resolve().parents[1]
HOME_FILES = {
    ".zshrc.env", ".zshrc.local", ".npmrc", ".condarc", ".tmux.conf", ".gitconfig",
    ".config/pip/pip.conf", ".config/zellij/config.kdl", ".ccm_config",
    ".local/bin/ccm", ".local/bin/ccc", ".local/share/ccm/ccm.sh",
    ".claude/settings.json", ".claude/statusline-command.sh", ".codex/config.toml",
    ".config/terminal-setup/ccm.zsh",
    ".config/opencode/opencode.json", ".config/opencode/opencode.jsonc",
}
MANAGED = {"repo/configs/.zshrc": ".zshrc",
           "repo/configs/starship.toml": ".config/starship.toml"}
BASELINE = "repo/configs/server-baseline.json"


def allowed_home_file(name):
    return name in HOME_FILES or bool(re.fullmatch(r"\.local/share/ccm/lang/[a-zA-Z_-]+\.json", name))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_private(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)


def capture_versions(baseline, home):
    result = copy.deepcopy(baseline)
    installer = Installer(home, baseline)
    for command in ["node", "fnm", "uv", "zellij", *baseline["npm"]]:
        executable = shutil.which(command) or installer.which(command)
        if not executable:
            continue
        try:
            probe = subprocess.run([executable, "--version"], env=installer.env,
                                   capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            print(f"Version unavailable: {command}; retaining baseline version")
            continue
        version = re.search(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.]+)?", probe.stdout)
        if probe.returncode == 0 and version:
            if command in result["npm"]:
                result["npm"][command]["version"] = version.group()
            else:
                result[command] = version.group()
    return result


def export_snapshot(home, destination, repo=REPO, dry_run=False):
    home, destination = Path(home).absolute(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Export destination already exists: {destination}")
    if not (home / ".zshrc").is_file():
        raise ValueError(f"No .zshrc to capture under {home}")
    files = {name for name in HOME_FILES if (home / name).is_file()}
    files.update(str(p.relative_to(home)) for p in (home / ".local/share/ccm/lang").glob("*.json")
                 if allowed_home_file(str(p.relative_to(home))) and p.is_file())
    if files.intersection({".local/bin/ccm", ".local/bin/ccc"}) and ".local/share/ccm/ccm.sh" not in files:
        raise ValueError("ccm/ccc launchers exist but their ccm.sh dependency is missing")
    if dry_run:
        print(f"[dry-run] Export installer, runtime versions, .zshrc, Starship and {len(files)} local files to {destination}")
        return
    baseline = capture_versions(load_baseline(repo / "configs/server-baseline.json"), home)
    baseline["custom_commands"] = [name for name in ("ccm", "ccc") if f".local/bin/{name}" in files]
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".server-export-", dir=destination.parent))
    try:
        # The bundle carries its installer; the new server needs no GitHub access
        # to this private repository. Only known installation assets are copied.
        for name in ("setup.sh", "sync.sh", "migrate.sh", "install.sh", "scripts/server_runtime.py",
                     "scripts/server_profile.py",
                     "scripts/server_snapshot.py", "scripts/install-zoxide.sh",
                     "configs/.zshrc", "configs/.zshrc.env.example",
                     "configs/.zshrc.local.example", "configs/starship.toml"):
            target = staging / "repo" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / name, target)
        shutil.copytree(repo / "bin", staging / "repo/bin")
        for name in ("configs/server", "scripts/bin", "vendor/ccm"):
            shutil.copytree(repo / name, staging / "repo" / name)
        for name in files:
            mode = 0o700 if name.startswith(".local/bin/") or name.endswith(".sh") else 0o600
            write_private(staging / "home" / name, (home / name).read_bytes(), mode)
        for bundled, local in MANAGED.items():
            if (home / local).is_file():
                write_private(staging / bundled, (home / local).read_bytes())
        write_private(staging / BASELINE, (json.dumps(baseline, indent=2) + "\n").encode())
        captured = [*(f"home/{name}" for name in sorted(files)), *MANAGED, BASELINE]
        manifest = {"format": 1, "source_home": str(home),
                    "files": {name: digest(staging / name) for name in captured}}
        write_private(staging / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
        write_private(staging / "install.sh", b'#!/usr/bin/env bash\nset -euo pipefail\n'
                      b'BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
                      b'exec bash "$BUNDLE_DIR/repo/migrate.sh" apply "$BUNDLE_DIR" "$@"\n', 0o700)
        write_private(staging / "README.txt", (
            "Run: bash install.sh --dry-run, then bash install.sh, then exec zsh.\n"
            "Requires Debian/Ubuntu/WSL, Python 3, sudo and access to installation sources.\n"
            "This directory contains private proxy/application/provider configuration.\n"
            "It does not contain SSH keys, CLI OAuth logins, ccm saved accounts, projects,\n"
            "Conda project environments, Docker data or GPU drivers. Sign in to CLIs on the new server.\n"
            "Proxy addresses are preserved: ensure the endpoint/tunnel exists on the new server.\n"
            "Existing tools are kept; old Node majors are upgraded via fnm. Missing tools use\n"
            "captured versions. Conda uses the current\n"
            "official Miniconda installer; apt package versions follow the target OS.\n"
        ).encode())
        os.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(f"Exported server baseline: {destination}")
    print(f"Captured {len(files)} local files, actual Zsh/Starship settings, tool versions and ccm dependencies.")


def deployment_files(bundle, target):
    manifest = json.loads((bundle / "manifest.json").read_text())
    if manifest.get("format") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Unsupported snapshot manifest")
    source_home = manifest.get("source_home", "")
    if not isinstance(source_home, str) or not source_home.startswith("/") or source_home == "/":
        raise ValueError("Invalid source home in snapshot")
    if any(char in str(target) for char in "\n\r\"'`$\\"):
        raise ValueError("Target home contains unsupported shell quoting characters")
    required = {*MANAGED, BASELINE}
    if not required.issubset(manifest["files"]):
        raise ValueError("Snapshot is missing managed configuration or baseline")
    result = []
    for name, expected in manifest["files"].items():
        if name not in required and not (name.startswith("home/") and allowed_home_file(name[5:])):
            raise ValueError(f"Unexpected snapshot path: {name}")
        source = bundle / name
        if not source.is_file() or source.is_symlink() or digest(source) != expected:
            raise ValueError(f"Missing or corrupted snapshot file: {name}")
        if name == BASELINE:
            load_baseline(source)
            continue
        relative = MANAGED.get(name, name[5:])
        content = source.read_text()
        # JSON/TOML/INI values and the quoted shell paths used by this baseline
        # must refer to the destination account, not the original username.
        content = content.replace(source_home, str(target))
        mode = 0o700 if relative.startswith(".local/bin/") or relative.endswith(".sh") else 0o600
        result.append((relative, content.encode(), mode))
    return result


def validate_destination(target, relative):
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"Invalid configuration path: {relative}")
    destination = target / relative
    for parent in (destination, *destination.parents):
        if parent.is_symlink():
            raise ValueError(f"Refusing to replace configuration through a symlink: {parent}")
        if parent == target:
            break
    if destination.exists() and not destination.is_file():
        raise ValueError(f"Expected a configuration file: {destination}")
    for parent in destination.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"Expected a directory: {parent}")
        if parent == target:
            break


def apply_files(files, target, dry_run=False):
    """Preflight and atomically apply explicit files, backing up changed contents."""
    files = list(files)
    for relative, _, _ in files:
        validate_destination(target, relative)
    validate_destination(target, ".local/state/terminal-setup/backups/.preflight")
    backup = None
    for relative, content, mode in files:
        destination = target / relative
        if destination.is_file() and destination.read_bytes() == content:
            continue
        if dry_run:
            print(f"[dry-run] Back up if present, then apply: {destination}")
            continue
        if destination.exists():
            if backup is None:
                root = target / ".local/state/terminal-setup/backups"
                root.mkdir(parents=True, exist_ok=True)
                backup = Path(tempfile.mkdtemp(prefix="server-migration-", dir=root))
                print(f"Backup: {backup}")
            write_private(backup / relative, destination.read_bytes(), destination.stat().st_mode & 0o777)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                os.fchmod(handle.fileno(), mode)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        print(f"Applied: {destination}")


def apply_snapshot(bundle, target, config_only=False, dry_run=False):
    bundle, target = Path(bundle).absolute(), Path(target).absolute()
    if not config_only and not dry_run and target != Path.home():
        raise ValueError("Software installation must target the current user; use --config-only with --target")
    files = deployment_files(bundle, target)
    apply_files(files, target, dry_run)
    if not config_only:
        args = ["bash", str(bundle / "repo/setup.sh"), "--server", "--keep-config"]
        if dry_run:
            args.append("--dry-run")
        subprocess.run(args, env=dict(os.environ, HOME=str(target)), check=True)
    print("Preview complete; no files changed." if dry_run else "Server snapshot applied.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "apply"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config-only", action="store_true", help="Apply configuration without installing software")
    parser.add_argument("--target", type=Path, default=Path.home())
    args = parser.parse_args()
    if args.action == "export":
        if args.config_only or args.target != Path.home():
            parser.error("--config-only/--target are for apply")
        export_snapshot(Path.home(), args.directory, dry_run=args.dry_run)
    else:
        apply_snapshot(args.directory, args.target, args.config_only, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
