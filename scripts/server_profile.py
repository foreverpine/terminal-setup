#!/usr/bin/env python3
"""Deploy the credential-free server profile stored in a Git checkout."""
import argparse
from pathlib import Path
import sys

from server_snapshot import apply_files

REPO = Path(__file__).resolve().parents[1]
# Application settings are seeds: preserve existing machine/account configuration.
SEEDS = {
    "configs/server/condarc": ".condarc",
    "configs/server/npmrc": ".npmrc",
    "configs/server/zellij.kdl": ".config/zellij/config.kdl",
    "configs/server/claude-settings.json": ".claude/settings.json",
    "configs/server/codex.toml": ".codex/config.toml",
    "configs/server/opencode.jsonc": ".config/opencode/opencode.jsonc",
    "configs/server/ccm.config.example": ".ccm_config",
    "vendor/ccm/ccm.sh": ".local/share/ccm/ccm.sh",
    "vendor/ccm/lang/en.json": ".local/share/ccm/lang/en.json",
    "vendor/ccm/lang/zh.json": ".local/share/ccm/lang/zh.json",
    "scripts/bin/ccm": ".local/bin/ccm",
    "scripts/bin/ccc": ".local/bin/ccc",
    "configs/server/claude-statusline.sh": ".claude/statusline-command.sh",
}
# Shared shell commands have a separate file so user overrides remain last.
MANAGED = {"configs/server/ccm.zsh": ".config/terminal-setup/ccm.zsh"}


def deploy(home, dry_run=False):
    files = []
    for source, relative in {**SEEDS, **MANAGED}.items():
        destination = home / relative
        if source in SEEDS and (destination.exists() or destination.is_symlink()):
            print(f"Preserved: {destination}")
            continue
        content = (REPO / source).read_bytes()
        mode = 0o700 if relative.startswith(".local/bin/") or relative.endswith(".sh") else 0o600
        files.append((relative, content, mode))
    apply_files(files, home, dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path.home())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        deploy(args.target.absolute(), args.dry_run)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
