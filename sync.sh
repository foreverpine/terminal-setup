#!/usr/bin/env bash
# Apply the same Zsh configuration on every server, preserving local overrides.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME"
DRY_RUN=false
INSTALL=false
PULL=false
RESTORE_DIR=""
LOCAL_DIR=""
REEXEC_ARGS=()

usage() {
    cat <<'EOF'
Usage: ./sync.sh [options]
  (no options)       Apply local Zsh + Starship templates; no sudo or network
  --install          Install server dependencies, then apply configuration
  --pull             Git fast-forward update, then apply the updated templates
  --dry-run          Preview without writing files, installing or fetching
  --restore DIR      Restore files from a printed backup directory
  --target DIR       Apply to another home directory (no --install)
  --local-dir DIR    Import .zshrc.env/.zshrc.local for this server; reject conflicts
  -h, --help         Show this help

Existing ~/.zshrc.env and ~/.zshrc.local are never overwritten.
Changed managed files are backed up to
~/.local/state/terminal-setup/backups/. Run `exec zsh` after applying changes.
EOF
}

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install) INSTALL=true; REEXEC_ARGS+=("$1"); shift ;;
        --pull) PULL=true; shift ;;
        --dry-run) DRY_RUN=true; REEXEC_ARGS+=("$1"); shift ;;
        --target|--restore|--local-dir)
            [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || die "$1 requires a directory"
            REEXEC_ARGS+=("$1" "$2")
            case "$1" in
                --target) TARGET_DIR="$2" ;;
                --restore) RESTORE_DIR="$2" ;;
                --local-dir) LOCAL_DIR="$2" ;;
            esac
            shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

[[ "$TARGET_DIR" == /* ]] || TARGET_DIR="$PWD/$TARGET_DIR"
[[ ! -e "$TARGET_DIR" || -d "$TARGET_DIR" ]] || die "Target is not a directory: $TARGET_DIR"
if [[ -n "$RESTORE_DIR" ]] && { $INSTALL || $PULL || [[ -n "$LOCAL_DIR" ]]; }; then
    die "--restore cannot be combined with --install, --pull or --local-dir"
fi
if $INSTALL && [[ "$TARGET_DIR" != "$HOME" ]]; then
    die "--install works on the current user's home; use --target only for configuration"
fi

if $PULL; then
    [[ -e "$SCRIPT_DIR/.git" ]] || die "--pull requires a Git checkout; otherwise copy the repository and run ./sync.sh"
    if $DRY_RUN; then
        printf '[dry-run] git -C %q pull --ff-only (preview below uses local templates)\n' "$SCRIPT_DIR"
    else
        [[ -z "$(git -C "$SCRIPT_DIR" status --porcelain)" ]] || die "Repository has local changes; commit or stash them before --pull"
        git -C "$SCRIPT_DIR" pull --ff-only
        # Reload the script too, so installer changes take effect in this run.
        exec bash "$SCRIPT_DIR/sync.sh" "${REEXEC_ARGS[@]}"
    fi
fi

RELATIVE_FILES=(.zshrc .config/starship.toml)
SOURCE_FILES=("$SCRIPT_DIR/configs/.zshrc" "$SCRIPT_DIR/configs/starship.toml")
if [[ -n "$RESTORE_DIR" ]]; then
    [[ -d "$RESTORE_DIR" ]] || die "Backup directory not found: $RESTORE_DIR"
    SOURCE_FILES=("$RESTORE_DIR/.zshrc" "$RESTORE_DIR/.config/starship.toml")
    FOUND=false
    for source_file in "${SOURCE_FILES[@]}"; do
        if [[ -e "$source_file" || -L "$source_file" ]]; then FOUND=true; fi
    done
    $FOUND || die "No Zsh or Starship backup found in $RESTORE_DIR"
fi

# Validate every destination before changing any of them.
for i in "${!RELATIVE_FILES[@]}"; do
    destination="$TARGET_DIR/${RELATIVE_FILES[$i]}"
    [[ ! -d "$destination" ]] || die "Expected a file, found a directory: $destination"
    parent="$(dirname "$destination")"
    [[ ! -e "$parent" || -d "$parent" ]] || die "Expected a directory: $parent"
    if [[ -z "$RESTORE_DIR" ]]; then
        [[ -f "${SOURCE_FILES[$i]}" ]] || die "Missing template: ${SOURCE_FILES[$i]}"
    fi
done
if [[ -f "${SOURCE_FILES[0]}" ]] && command -v zsh >/dev/null 2>&1; then
    zsh -n "${SOURCE_FILES[0]}"
fi

# Environment is loaded early; interactive overrides are loaded late.
# Import only these two files, never arbitrary files from a supplied directory.
OVERRIDE_FILES=()
OVERRIDE_SOURCES=()
if [[ -z "$RESTORE_DIR" ]]; then
    OVERRIDE_FILES=(.zshrc.env .zshrc.local)
    if [[ -n "$LOCAL_DIR" ]]; then
        [[ -d "$LOCAL_DIR" ]] || die "Local configuration directory not found: $LOCAL_DIR"
        [[ -e "$LOCAL_DIR/.zshrc.env" || -L "$LOCAL_DIR/.zshrc.env" ||
           -e "$LOCAL_DIR/.zshrc.local" || -L "$LOCAL_DIR/.zshrc.local" ]] ||
            die "No .zshrc.env or .zshrc.local found in $LOCAL_DIR"
    fi
    for relative in "${OVERRIDE_FILES[@]}"; do
        destination="$TARGET_DIR/$relative"
        source_file="$SCRIPT_DIR/configs/$relative.example"
        [[ ! -d "$destination" ]] || die "Expected a file, found a directory: $destination"
        if [[ -n "$LOCAL_DIR" && ( -e "$LOCAL_DIR/$relative" || -L "$LOCAL_DIR/$relative" ) ]]; then
            source_file="$LOCAL_DIR/$relative"
            [[ -f "$source_file" && -r "$source_file" ]] || die "Expected a readable file: $source_file"
            if [[ -e "$destination" || -L "$destination" ]] && ! cmp -s "$source_file" "$destination"; then
                die "Import conflicts with $destination; compare and merge it manually (existing file preserved)"
            fi
        fi
        OVERRIDE_SOURCES+=("$source_file")
        if [[ ! -e "$destination" && ! -L "$destination" ]]; then
            [[ -f "$source_file" && -r "$source_file" ]] || die "Missing local template: $source_file"
            if command -v zsh >/dev/null 2>&1; then
                zsh -n "$source_file"
            fi
        fi
    done
fi

BACKUP_DIR=""
TEMP_FILE=""
trap 'if [[ -n "$TEMP_FILE" ]]; then rm -f -- "$TEMP_FILE"; fi' EXIT
CHANGED=false
for i in "${!OVERRIDE_FILES[@]}"; do
    destination="$TARGET_DIR/${OVERRIDE_FILES[$i]}"
    [[ -e "$destination" || -L "$destination" ]] && continue
    if $DRY_RUN; then
        printf '[dry-run] Create local configuration: %s (from %s)\n' "$destination" "${OVERRIDE_SOURCES[$i]}"
    else
        mkdir -p "$TARGET_DIR"
        install -m 600 "${OVERRIDE_SOURCES[$i]}" "$destination"
        CHANGED=true
        printf 'Created: %s (server settings; preserved on future syncs)\n' "$destination"
    fi
done

if $INSTALL; then
    INSTALL_ARGS=(--server)
    $DRY_RUN && INSTALL_ARGS+=(--dry-run)
    exec bash "$SCRIPT_DIR/setup.sh" "${INSTALL_ARGS[@]}"
fi

for i in "${!RELATIVE_FILES[@]}"; do
    relative="${RELATIVE_FILES[$i]}"
    source_file="${SOURCE_FILES[$i]}"
    destination="$TARGET_DIR/$relative"
    [[ -e "$source_file" || -L "$source_file" ]] || continue
    # A restore must preserve the original symlink, even when contents match.
    if [[ ! -L "$source_file" && ! -L "$destination" ]] && cmp -s "$source_file" "$destination"; then
        printf 'Unchanged: %s\n' "$destination"
        continue
    fi
    if $DRY_RUN; then
        printf '[dry-run] Back up if present, then apply: %s\n' "$destination"
        continue
    fi
    if [[ -e "$destination" || -L "$destination" ]]; then
        if [[ -z "$BACKUP_DIR" ]]; then
            backup_root="$TARGET_DIR/.local/state/terminal-setup/backups"
            mkdir -p "$backup_root"
            BACKUP_DIR="$(mktemp -d "$backup_root/$(date +%Y%m%d-%H%M%S).XXXXXX")"
            printf 'Backup: %s\n' "$BACKUP_DIR"
        fi
        mkdir -p "$BACKUP_DIR/$(dirname "$relative")"
        cp -pP "$destination" "$BACKUP_DIR/$relative"
    fi
    mkdir -p "$(dirname "$destination")"
    TEMP_FILE="$(mktemp "$destination.tmp.XXXXXX")"
    # Copy via a sibling temporary file; never follow an existing destination link.
    rm -f -- "$TEMP_FILE"
    cp -pP "$source_file" "$TEMP_FILE"
    mv -f "$TEMP_FILE" "$destination"
    TEMP_FILE=""
    CHANGED=true
    printf 'Applied: %s\n' "$destination"
done

if [[ -n "$BACKUP_DIR" ]]; then
    printf 'Restore: bash %q --target %q --restore %q\n' "$SCRIPT_DIR/sync.sh" "$TARGET_DIR" "$BACKUP_DIR"
fi
if $DRY_RUN; then
    printf 'Preview complete; no files changed.\n'
elif $CHANGED; then
    printf 'Configuration ready. Open a new terminal or run: exec zsh\n'
else
    printf 'Configuration is already up to date.\n'
fi

if [[ -z "$RESTORE_DIR" && "$TARGET_DIR" == "$HOME" ]]; then
    export PATH="$HOME/.local/bin:$PATH"
    MISSING=()
    for tool in zsh starship zoxide fzf eza bat fd rg btop jq tldr delta lazygit; do
        command -v "$tool" >/dev/null 2>&1 || MISSING+=("$tool")
    done
    if [[ ${#MISSING[@]} -gt 0 ]]; then
        printf 'Missing tools: %s. Install with: ./sync.sh --install\n' "${MISSING[*]}"
    fi
fi
