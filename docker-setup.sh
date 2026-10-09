#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    echo 'Install Python first: sudo apt-get install python3' >&2
    exit 1
fi
exec python3 "$SCRIPT_DIR/scripts/docker_setup.py" "$@"
