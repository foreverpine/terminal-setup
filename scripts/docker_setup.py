#!/usr/bin/env python3
"""Install Docker's signed apt packages and apply a portable daemon configuration."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
DOCKER_PACKAGES = ["docker-ce", "docker-ce-cli", "containerd.io",
                   "docker-buildx-plugin", "docker-compose-plugin"]
GPU_PACKAGES = ["nvidia-container-toolkit", "nvidia-container-toolkit-base",
                "libnvidia-container-tools", "libnvidia-container1"]
NVIDIA_BASE = "https://nvidia.github.io/libnvidia-container"


def validate_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise ValueError("Repository/mirror URLs must be HTTPS URLs without whitespace")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ValueError("Repository/mirror URLs must use HTTPS without credentials or query strings")
    return value.rstrip("/")


def platform_info(text):
    values = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            parsed = shlex.split(value)
            values[key] = parsed[0] if parsed else ""
    distro = values.get("ID")
    codename = values.get("UBUNTU_CODENAME") or values.get("VERSION_CODENAME", "")
    if distro not in ("ubuntu", "debian") or not re.fullmatch(r"[a-z0-9_-]+", codename):
        raise ValueError("This installer requires Ubuntu or Debian with a release codename")
    return distro, codename


def merge_daemon(existing, mirrors):
    if not isinstance(existing, dict) or not isinstance(mirrors, list):
        raise ValueError("daemon.json must be an object and registry-mirrors must be a list")
    return {**existing, "registry-mirrors": [validate_url(url) for url in mirrors]}


class ConfigWriter:
    """Back up changed files and replace them atomically, without following symlinks."""
    def __init__(self, backup_root):
        self.backup_root = Path(backup_root)
        self.backup = None

    def write(self, destination, content, mode=0o644):
        destination = Path(destination)
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError(f"Refusing to replace non-regular configuration: {destination}")
        if destination.exists() and destination.read_bytes() == content:
            return False
        if destination.exists():
            if self.backup is None:
                self.backup_root.mkdir(parents=True, exist_ok=True)
                self.backup = Path(tempfile.mkdtemp(
                    prefix=datetime.now().strftime("%Y%m%d-%H%M%S-"), dir=self.backup_root))
                print(f"Backup: {self.backup}", flush=True)
            shutil.copy2(destination, self.backup / destination.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                os.fchmod(handle.fileno(), mode)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        print(f"Applied: {destination}", flush=True)
        return True


def run(*command, capture=False):
    result = subprocess.run(command, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout or ""


def installed(package):
    result = subprocess.run(["dpkg-query", "-W", "-f=${Status}", package],
                            capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "install ok installed"


def service_active():
    return subprocess.run(["systemctl", "is-active", "--quiet", "docker"],
                          capture_output=True).returncode == 0


def check_workloads(allow_restart):
    if service_active():
        running = run("docker", "--host=unix:///var/run/docker.sock", "ps", "-q", capture=True)
        if running.strip() and not allow_restart:
            raise ValueError("Docker has running containers. Schedule downtime and use --restart to proceed")


def load_settings(path):
    settings = json.loads(path.read_text())
    if not isinstance(settings, dict) or set(settings) != {"docker-apt-base", "registry-mirrors"}:
        raise ValueError("Settings must contain docker-apt-base and registry-mirrors only")
    settings["docker-apt-base"] = validate_url(settings["docker-apt-base"])
    settings.update(merge_daemon({}, settings["registry-mirrors"]))
    return settings


def check_sources(gpu, directory=Path("/etc/apt/sources.list.d")):
    # Don't create competing Signed-By entries or overwrite a mixed source file.
    for path in directory.glob("*"):
        if path.suffix not in (".list", ".sources"):
            continue
        lines = [line for line in path.read_text().splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        docker_lines = [line for line in lines if "download.docker.com" in line or "docker-ce/linux" in line]
        nvidia_lines = [line for line in lines if "nvidia.github.io/libnvidia-container" in line]
        if ((docker_lines and path.name != "docker.list")
                or (path.name == "docker.list" and (len(docker_lines) != len(lines) or path.is_symlink()))):
            raise ValueError(f"Review the existing Docker apt source before proceeding: {path}")
        if gpu and ((nvidia_lines and path.name != "nvidia-container-toolkit.list")
                    or (path.name == "nvidia-container-toolkit.list"
                        and (len(nvidia_lines) != len(lines) or path.is_symlink()))):
            raise ValueError(f"Review the existing NVIDIA apt source before proceeding: {path}")


def install_packages(settings, gpu, writer):
    distro, codename = platform_info(Path("/etc/os-release").read_text())
    arch = run("dpkg", "--print-architecture", capture=True).strip()
    if not re.fullmatch(r"[a-z0-9]+", arch):
        raise ValueError("Unexpected dpkg architecture")
    if gpu and arch not in ("amd64", "arm64"):
        raise ValueError("GPU installation supports amd64 and arm64")
    conflicts = [p for p in ["docker.io", "docker-compose", "docker-compose-v2", "docker-doc",
                             "docker-buildx", "podman-docker", "containerd", "runc"] if installed(p)]
    if conflicts:
        raise ValueError("Conflicting packages need manual review; nothing removed: " + ", ".join(conflicts))
    check_sources(gpu)
    base = settings["docker-apt-base"] + "/" + distro
    sources = [(base + "/gpg", "/etc/apt/keyrings/docker.gpg", "/etc/apt/sources.list.d/docker.list",
                f"deb [arch={arch} signed-by=/etc/apt/keyrings/docker.gpg] {base} {codename} stable\n")]
    if gpu:
        sources.append((NVIDIA_BASE + "/gpgkey", "/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg",
                        "/etc/apt/sources.list.d/nvidia-container-toolkit.list",
                        "deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] "
                        f"{NVIDIA_BASE}/stable/deb/{arch} /\n"))
    print("[INSTALL] Configure signed apt repositories and install missing packages", flush=True)
    prerequisites = [p for p in ["ca-certificates", "curl", "gnupg"] if not installed(p)]
    if prerequisites:
        run("apt-get", "update")
        run("apt-get", "install", "-y", *prerequisites)
    with tempfile.TemporaryDirectory(prefix="docker-keys-") as directory:
        for index, (url, key_path, source_path, source) in enumerate(sources):
            # An existing valid key remains usable when a network is temporarily down.
            if not Path(key_path).is_file():
                raw = Path(directory) / f"key-{index}.asc"
                binary = Path(directory) / f"key-{index}.gpg"
                run("curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                    "--proto-redir", "=https", "--connect-timeout", "10", "--max-time", "60",
                    url, "--output", str(raw))
                run("gpg", "--batch", "--yes", "--dearmor", "--output", str(binary), str(raw))
                writer.write(Path(key_path), binary.read_bytes())
            writer.write(Path(source_path), source.encode())
    run("apt-get", "update")
    packages = DOCKER_PACKAGES + (GPU_PACKAGES if gpu else [])
    missing = [p for p in packages if not installed(p)]
    if missing:
        run("apt-get", "install", "-y", *missing)
    else:
        print("Packages already installed; no automatic version upgrade.")


def apply_daemon(root, settings, gpu, writer):
    destination = root / "etc/docker/daemon.json"
    if destination.is_symlink():
        raise ValueError("Review the daemon.json symlink before configuration")
    old_bytes = destination.read_bytes() if destination.exists() else None
    existing = json.loads(old_bytes) if old_bytes is not None else {}
    merged = merge_daemon(existing, settings["registry-mirrors"])
    with tempfile.TemporaryDirectory(prefix="docker-config-") as directory:
        staged = Path(directory) / "daemon.json"
        staged.write_text(json.dumps(merged, indent=2) + "\n")
        staged.chmod(0o600)
        if gpu:
            run("nvidia-ctk", "runtime", "configure", "--runtime=docker", "--config=" + str(staged))
        if root == Path("/"):
            run("dockerd", "--validate", "--config-file=" + str(staged))
        final = json.loads(staged.read_text())
        if final == existing:
            print("Docker daemon configuration is already up to date.")
            return False, old_bytes
        mode = (destination.stat().st_mode & 0o777) if destination.exists() else 0o600
        return writer.write(destination, staged.read_bytes(), mode), old_bytes


def activate_service(destination, changed, old_bytes, writer):
    try:
        run("systemctl", "enable", "docker")
        if changed:
            run("systemctl", "restart", "docker")
        elif not service_active():
            run("systemctl", "start", "docker")
    except subprocess.CalledProcessError:
        if changed:
            if old_bytes is None:
                destination.unlink()
            else:
                # Keep the pre-apply backup intact; restoring gets a separate backup.
                ConfigWriter(writer.backup_root).write(destination, old_bytes, destination.stat().st_mode & 0o777)
            print("Docker startup failed; restored the prior daemon configuration.", file=sys.stderr)
            try:
                run("systemctl", "restart", "docker")
            except subprocess.CalledProcessError:
                print("Docker still failed to start; inspect: journalctl -u docker", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", action="store_true", help="Install/configure NVIDIA Container Toolkit; working host driver required")
    parser.add_argument("--configure-only", action="store_true", help="Apply daemon settings only; do not install packages or apt sources")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sudo, network requests or file writes")
    parser.add_argument("--restart", action="store_true", help="Allow installation/restart while containers are running")
    parser.add_argument("--config", type=Path, default=REPO / "configs/docker.json", help="Settings JSON, e.g. configs/docker.local.json")
    parser.add_argument("--root", type=Path, default=Path("/"), help="Stage configuration under a test directory; requires --configure-only, no services")
    args = parser.parse_args()
    args.root = args.root.resolve()
    args.config = args.config.resolve()
    if args.root != Path("/") and not args.configure_only:
        parser.error("--root requires --configure-only; package installation only targets the live system")
    settings = load_settings(args.config)
    destination = args.root / "etc/docker/daemon.json"
    if args.dry_run:
        print("[PREVIEW] No files, packages, services or user groups will be changed.")
        if not args.configure_only:
            distro, codename = platform_info(Path("/etc/os-release").read_text())
            print(f"Docker apt: {settings['docker-apt-base']}/{distro} {codename} stable")
            print("Packages: " + " ".join(DOCKER_PACKAGES + (GPU_PACKAGES if args.gpu else [])))
        print("Registry mirrors: " + ", ".join(settings["registry-mirrors"]))
        print(f"Merge, validate and back up if changed: {destination}")
        if args.gpu:
            print(f"NVIDIA apt: {NVIDIA_BASE}/stable/deb/<architecture>")
            print("Require working nvidia-smi; configure runtime with nvidia-ctk.")
        if args.root == Path("/"):
            print("Start Docker, or restart after changed configuration; running workloads require --restart.")
        return
    if args.root == Path("/") and os.geteuid() != 0:
        # Read protected daemon settings only after privilege elevation.
        forwarded = [*sys.argv[1:], "--config", str(args.config)]
        os.execvp("sudo", ["sudo", "--", sys.executable, str(Path(__file__).resolve()), *forwarded])
    # Validate before package installation or any file replacement, never during preview.
    if destination.is_symlink():
        raise ValueError("Review the daemon.json symlink before configuration")
    if destination.exists():
        merge_daemon(json.loads(destination.read_text()), settings["registry-mirrors"])
    if args.root == Path("/"):
        if not Path("/run/systemd/system").is_dir():
            raise ValueError("This installer requires systemd (enable it first when using WSL)")
        check_workloads(args.restart)
        if args.gpu:
            if shutil.which("nvidia-smi") is None:
                raise ValueError("Install a suitable NVIDIA host driver first; nvidia-smi is missing")
            run("nvidia-smi", "-L")
    writer = ConfigWriter(args.root / "var/backups/terminal-setup/docker")
    if not args.configure_only:
        install_packages(settings, args.gpu, writer)
    print("[CONFIG] Merge daemon settings; preserve data-root, network and unrelated runtimes", flush=True)
    changed, old_bytes = apply_daemon(args.root, settings, args.gpu, writer)
    if args.root != Path("/"):
        print("Staged configuration only; no packages or services touched.")
        return
    print("[VERIFY] Activate Docker; no test image will be pulled", flush=True)
    activate_service(destination, changed, old_bytes, writer)
    runtimes = json.loads(run("docker", "--host=unix:///var/run/docker.sock", "info", "--format", "{{json .Runtimes}}", capture=True))
    if args.gpu and "nvidia" not in runtimes:
        raise ValueError("Docker is running but did not register the NVIDIA runtime")
    run("docker", "compose", "version")
    run("docker", "buildx", "version")
    print("Docker setup complete" + (" with NVIDIA runtime." if args.gpu else "."))
    print("No images, containers, volumes, Docker login credentials or GPU drivers were copied.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
