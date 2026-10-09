#!/usr/bin/env bash
# Export this server's baseline or apply a previously exported snapshot.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/server_snapshot.py" "$@"
