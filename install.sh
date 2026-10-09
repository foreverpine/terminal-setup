#!/usr/bin/env bash
# Clone this repository, then run ./install.sh on the new server.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_ONLY=false
DRY_RUN=false
TARGET_DIR="$HOME"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --config-only) CONFIG_ONLY=true; shift ;;
        --target)
            [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || { echo '--target requires a directory' >&2; exit 1; }
            TARGET_DIR="$2"; shift 2 ;;
        -h|--help)
            echo 'Usage: ./install.sh [--dry-run] [--config-only [--target DIR]]'
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done
ARGS=()
$DRY_RUN && ARGS+=(--dry-run)
if $CONFIG_ONLY; then
    python3 "$SCRIPT_DIR/scripts/server_profile.py" --target "$TARGET_DIR" "${ARGS[@]}"
    exec bash "$SCRIPT_DIR/sync.sh" --target "$TARGET_DIR" "${ARGS[@]}"
fi
[[ "$TARGET_DIR" == "$HOME" ]] || { echo '--target requires --config-only' >&2; exit 1; }
exec bash "$SCRIPT_DIR/sync.sh" --install "${ARGS[@]}"
