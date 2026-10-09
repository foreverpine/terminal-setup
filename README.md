# 🖥️ terminal-setup

> 🔧 **Personal fork** of [`lewislulu/terminal-setup`](https://github.com/lewislulu/terminal-setup), customized for my own daily use.
> **Primary environment: Ubuntu 24.04 + Zsh.** The customization architecture (versioned template + local override) is documented in [`CLAUDE.md`](CLAUDE.md).

One-script terminal environment setup for **macOS**, **Debian/Ubuntu**, and **Windows (WSL)**. Run on a fresh machine, get a fully configured terminal in minutes.

**🇨🇳 [中文版文档](README_CN.md)**

<p align="center">
  <img src="assets/ghostty.png" width="80" alt="Ghostty">
  &nbsp;&nbsp;
  <img src="assets/fish.png" width="80" alt="Fish Shell">
  &nbsp;&nbsp;
  <img src="assets/zsh.png" width="80" alt="Zsh">
  &nbsp;&nbsp;
  <img src="assets/starship.png" width="80" alt="Starship">
</p>

<p align="center">
  <img src="assets/demo-2x.gif" width="600" alt="Demo">
</p>

## Supported Platforms

| Platform | Status | Package Manager |
|----------|--------|----------------|
| 🐧 **Debian / Ubuntu** | ✅ **My primary environment** — daily-driven on Ubuntu 24.04 | apt + bundled binaries |
| 🍎 **macOS** | ✅ Upstream primary — supported via Homebrew | Homebrew |
| 🪟 **Windows (WSL)** | 🧪 Inherited from upstream — not personally tested | apt (inside WSL) |
| 🪟 **Windows (native)** | ⛔ Not supported | Use WSL instead |

> **Note:** This is a personal config repo. I use it daily on **Ubuntu 24.04 + Zsh**. The macOS/WSL paths are inherited from upstream `lewislulu/terminal-setup` (developed on macOS; Linux/WSL added later) and should still work, but I only actively maintain the Ubuntu/Zsh path.

## Quick Start

### Docker and NVIDIA GPUs

On a new Ubuntu/Debian server with a working NVIDIA driver (`nvidia-smi`), run
`./docker-setup.sh --gpu`. Preview with `--dry-run`. Repository and registry-mirror
settings live in `configs/docker.json`; no images or container data are migrated.
This is separate from normal Zsh sync. See [Docker setup](DOCKER_SETUP.md).

### Clone and install on the next server

```bash
git clone git@github.com:foreverpine/terminal-setup.git
cd terminal-setup
./install.sh
exec zsh
```

The repository now carries the server tools, runtimes, CLI applications, actual
Starship/Zellij preferences, Conda/npm settings, CLI preferences, status-line
script and the ccm/ccc implementation. No archive transfer is needed.
Preview with `./install.sh --dry-run`; Debian/Ubuntu/WSL installation uses sudo.

Credential-free defaults live in `configs/server/`; the existing server's ccm
implementation and translations live in `vendor/ccm/`. Existing application
settings and credentials are preserved. Shared shell functions load before
`~/.zshrc.local`, so personal overrides still take precedence.

API keys, private gateway endpoints, login sessions and project trust stay out
of Git. Configure credentials on the destination in `~/.ccm_config` or environment
variables in `~/.zshrc.env`; set that server's proxy there too. The repository's
Claude defaults omit gateway-specific model overrides and work with normal login.

For updates, run `git pull --ff-only` then `./install.sh`. To trial configuration
deployment without installing software, use
`./install.sh --config-only --target /tmp/server-preview`.

### Optional private snapshot migration

Export a self-contained baseline with the current configuration and dependencies:

```bash
./migrate.sh export ./snapshots/current
rsync -a ./snapshots/current/ new-server:~/terminal-baseline/
# On the new server:
cd ~/terminal-baseline
bash install.sh --dry-run
bash install.sh
exec zsh
```

The bundle includes its installer, captured runtime/CLI versions, actual Zsh and
Starship settings, local environment/functions, Git/npm/Conda/Zellij/CLI settings,
ccm/ccc scripts and language files, ccm provider configuration and the known Claude
status-line script. It replaces absolute source HOME paths with the destination
HOME, validates the entire snapshot first and backs up changed target configs.

The default server install now also installs fnm/Node, pnpm, uv/uvx, Miniconda,
tmux/Zellij, Claude Code, Codex, OpenCode, dsh and agently-cli. Missing user tools
use captured versions; existing tools are retained, except Node majors older than
the baseline are upgraded through fnm. apt versions follow the target
distribution; Miniconda uses its current official installer. A final missing-tool
check fails instead of reporting success with an incomplete baseline.

Requires Debian/Ubuntu/WSL, Python 3, sudo and access to installation sources.
Snapshots contain private configuration and are excluded from Git; copy them
only to your own server. Proxy endpoints/tunnels must be reachable from there;
installation uses the invoking shell's proxy environment. SSH keys, OAuth logins,
saved ccm accounts, project Conda environments, projects, Docker data and GPU
drivers are not copied. Sign in to application CLIs on the destination.
Do not edit bundle files in place (checksums detect changes); adjust settings on
the destination after applying, or adjust the source and export a fresh snapshot.

Use `./migrate.sh apply SNAPSHOT --target /tmp/server-test --config-only` for an
isolated configuration trial, and `python3 scripts/server_runtime.py --check`
to verify command availability. Migration backups retain relative paths under
`~/.local/state/terminal-setup/backups/server-migration-*`; restore individual
files from there. `sync.sh --restore` only handles Zsh and Starship.

See [the full migration guide](README_CN.md#按当前服务器配置新服务器推荐).

### Sync Zsh templates between servers

On a new Debian/Ubuntu/WSL server, copy this repository and run:

```bash
cd ~/terminal-setup
./sync.sh --install
exec zsh
```

This installs the complete server baseline without desktop/font or optional
software prompts. It also configures Git delta (backing up `.gitconfig`) and
attempts to set Zsh as the login shell. The checkout includes actual non-secret
defaults and ccm scripts; snapshots additionally carry private machine settings.

For later updates, run `./sync.sh --pull` in a clean Git checkout, or copy the
updated repository and run `./sync.sh`. Configuration-only sync needs no sudo or
network. Commit and push template changes before pulling them on another server.
If this private repository is unavailable there, copy the directory using rsync.

The managed files are `~/.zshrc` and `~/.config/starship.toml`. Existing
`~/.zshrc.env` and `~/.zshrc.local` are preserved, including symlinks; missing
files are seeded with commented examples (mode 600). Unchanged files are skipped. Changed files are backed up under
`~/.local/state/terminal-setup/backups/`, with a restore command printed.

```bash
./sync.sh --dry-run
./sync.sh --install --dry-run
./sync.sh --restore /path/to/backup
./sync.sh --target /tmp/zsh-preview
./sync.sh --local-dir ~/server-config
```

Restore only replaces files present in the backup; it does not remove newly
created files or undo installed software, Git settings or login-shell changes.
Restore does not change `.zshrc.env` or `.zshrc.local`.
Edit the versioned templates for shared settings. Put per-server PATH, proxies
and tool environment in `.zshrc.env`, which runs **before tool initialization**.
Keep functions, aliases and widgets in `.zshrc.local`, which runs afterwards,
before syntax highlighting. Existing `.zshrc.local` remains compatible; move any
PATH/proxy exports to `.zshrc.env` when they need to affect initialization.
Both hooks run from interactive `.zshrc`, not from `.zshenv`.

Prepare a directory outside the repository for each server containing
`.zshrc.env` and/or `.zshrc.local`. Start from the examples in `configs/`, use
`$HOME` instead of hardcoded usernames and choose a proxy reachable from the
target server (`127.0.0.1` means that server itself). Transfer the directory,
then run `./sync.sh --local-dir ~/server-config --install` on the target, or omit
`--install` if dependencies are ready. Preview by adding `--dry-run`.
The installer does not execute these Zsh files; export any proxy required for
installation in the invoking shell first.

Import copies only these two hook files, not external scripts they reference.
Existing files with different contents cause an error before deployment or
installation; merge them manually. Identical files are preserved. If a previous
sync already seeded examples, edit those files directly or merge first.
Shell history, zoxide data and SSH keys are not synced.
Enable a Nerd Font in the terminal on your client computer.

Run migration/rollback checks with `python3 -m unittest discover -s tests -v`.
See [the Chinese guide](README_CN.md#日常同步-zsh-模板) for template transfer examples.

### macOS

```bash
git clone https://github.com/foreverpine/terminal-setup.git
cd terminal-setup && ./setup.sh
```

### Debian / Ubuntu

```bash
git clone https://github.com/foreverpine/terminal-setup.git
cd terminal-setup && ./setup.sh
```

### Windows (WSL)

First install WSL if you haven't:
```powershell
# In PowerShell (Admin)
wsl --install
```

Then inside WSL:
```bash
git clone https://github.com/foreverpine/terminal-setup.git
cd terminal-setup && ./setup.sh
```

### Options

```bash
./setup.sh --fish       # Fish shell
./setup.sh --zsh        # Zsh + fish-like plugins
./setup.sh --dry-run    # Preview what would be done (no changes)
```

One-liner (auto-clones):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/foreverpine/terminal-setup/main/setup.sh)
```

## Choose Your Shell

| | 🐟 Fish | 🐚 Zsh |
|---|---------|---------|
| **POSIX** | ❌ Own syntax | ✅ Compatible |
| **Autosuggestions** | ✅ Built-in | ✅ via plugin |
| **Syntax Highlighting** | ✅ Built-in | ✅ via plugin |
| **Node Manager** | fnm (shared) | fnm (shared) |
| **Config** | `~/.config/fish/config.fish` | `~/.zshrc` |
| **Best for** | Clean defaults, no fuss | Scripting, POSIX compat |

## Stack

| Component | What |
|-----------|------|
| **[Ghostty](https://ghostty.org)** | GPU-accelerated terminal emulator |
| **Fish** or **Zsh** | Shell (your choice) |
| **[Starship](https://starship.rs)** | Cross-shell prompt (Catppuccin Mocha theme) |
| **MesloLGS NF** | Nerd Font for icons & powerline glyphs |
| **[bat](https://github.com/sharkdp/bat)** | `cat` with syntax highlighting & line numbers |
| **[eza](https://github.com/eza-community/eza)** | `ls` with icons, git status, tree view |
| **[fd](https://github.com/sharkdp/fd)** | `find` but fast & intuitive |
| **[ripgrep](https://github.com/BurntSushi/ripgrep)** | `grep` but orders of magnitude faster |
| **[fzf](https://github.com/junegunn/fzf)** | Fuzzy finder (Ctrl+R / Ctrl+T / Alt+C) |
| **[btop](https://github.com/aristocratos/btop)** | Beautiful system monitor |
| **[zoxide](https://github.com/ajeetdsouza/zoxide)** | Smart `cd` that learns your habits |
| **[jq](https://github.com/jqlang/jq)** | JSON processor |
| **[tldr](https://github.com/tldr-pages/tldr)** | Simplified man pages with examples |
| **[delta](https://github.com/dandavison/delta)** | Beautiful git diffs with syntax highlighting |
| **[lazygit](https://github.com/jesseduffield/lazygit)** | Git TUI |
| **[fnm](https://github.com/Schniz/fnm)** | Fast Node Manager (Rust) |
| **[Zellij](https://zellij.dev)** | Modern terminal multiplexer (optional) |

## What It Does

1. Installs **package manager** (Homebrew on macOS, apt on Linux)
2. Installs **Ghostty** terminal (macOS; Linux users install separately)
3. Downloads **MesloLGS NF** nerd fonts
4. Installs your **shell** of choice + plugins
5. Installs all **CLI tools** (Homebrew on macOS, apt + GitHub releases on Linux)
6. Installs **Starship** prompt with Catppuccin Mocha config
7. Installs **fnm** + **Node.js** LTS (optional)
8. Installs **Zellij** terminal multiplexer (optional)
9. Deploys all config files (existing configs are backed up with timestamps)

## Platform Notes

### macOS
- Full support, everything installs via Homebrew
- Ghostty installs as a native macOS app

### Debian / Ubuntu
- CLI tools install via apt where available, GitHub releases for others (delta, lazygit, eza)
- `bat` → `batcat`, `fd` → `fdfind` — symlinks are created automatically
- Fonts install to `~/.local/share/fonts/`
- Ghostty is not in apt — install manually via [snap, build from source](https://ghostty.org/docs/install), or use another terminal
- Zsh plugins install via apt or git clone

### Windows (WSL)
- Everything runs inside WSL (Ubuntu/Debian layer)
- Terminal emulator runs on the Windows side — use [Windows Terminal](https://aka.ms/terminal) or [Ghostty for Windows](https://ghostty.org)
- Script detects WSL automatically and adapts
- If run in native Windows (MINGW/Git Bash), the script will prompt you to install WSL

## Aliases / Abbreviations

| Shortcut | Expands To |
|----------|-----------|
| `ls` | `eza --icons --group-directories-first` |
| `ll` | `eza -la --icons --group-directories-first` |
| `lt` | `eza --tree --icons --level=2` |
| `cat` | `bat` |
| `find` | `fd` |
| `grep` | `rg` |
| `top` | `btop` |
| `lg` | `lazygit` |

## fzf Keybindings

| Key | What |
|-----|------|
| `Ctrl+R` | Fuzzy search command history |
| `Ctrl+T` | Fuzzy find files (uses `fd` as backend) |
| `Alt+C` | Fuzzy cd into directory |

## fnm — Node Version Manager

```bash
fnm install 22            # Install Node 22
fnm install --lts         # Install latest LTS
fnm default 22            # Set default version
fnm use 22                # Switch in current shell
echo "22" > .node-version # Auto-switch when entering this directory
```

## SSH Key Switcher

Both shell configs include a `set-ssh-key` function for quick SSH key switching:

```bash
set-ssh-key my-key-name     # Clears agent, loads ~/.ssh/my-key-name
set-ssh-key                  # Shows available keys on error
```

> **Best practice:** Prefer `~/.ssh/config` with `Host` aliases and `IdentitiesOnly yes` for automatic key selection. The `set-ssh-key` function is a fallback for edge cases.

---

## Design Decisions

### Why Ghostty?

GPU-accelerated, native macOS app, fast startup, clean config format. It's what iTerm2 should have been — modern, minimal, and doesn't try to do everything. Still early but moving fast.

### Why Starship over Powerlevel10k?

- **Cross-shell:** Same prompt config works in both Fish and Zsh. p10k is Zsh-only.
- **TOML config:** Declarative and readable vs p10k's wizard-generated mess.
- **Rust binary:** Fast, no shell framework dependency.
- **Catppuccin theme:** Consistent with the rest of the stack.

If you only use Zsh and want maximum prompt speed, p10k's instant prompt is technically faster. But Starship is fast enough and works everywhere.

### Why Fish AND Zsh? Why not just one?

Different people have different needs:

- **Fish:** Best out-of-box experience. Autosuggestions, syntax highlighting, completions — all built-in, zero config. But it's not POSIX-compatible, so `bash` scripts won't work directly, and some tools assume POSIX shell syntax.
- **Zsh:** POSIX-compatible, so all bash scripts and one-liners work. With plugins (autosuggestions + syntax-highlighting), you get 90% of Fish's UX. The trade-off: more moving parts.

If you're primarily a user/developer who runs other people's scripts → **Zsh**.
If you want the cleanest shell experience and don't mind the occasional `bash script.sh` → **Fish**.

### Why Homebrew for Zsh plugins? Why not zinit/antidote/sheldon?

We only install 3 Zsh plugins: `zsh-autosuggestions`, `zsh-syntax-highlighting`, `zsh-completions`.

For 3 plugins, a plugin manager is overkill:

- **zinit:** Original author abandoned it. Community fork (zdharma-continuum) exists but adds complexity for no gain at this scale. Turbo mode and ice modifiers are powerful but unnecessary here.
- **antidote/sheldon:** Good tools, but still an extra layer. More things that can break.
- **Oh My Zsh:** Framework, not a plugin manager. Loads 100+ files on startup. Slow.
- **Homebrew:** Already installed, `brew install` + one `source` line in `.zshrc`. Updates via `brew upgrade`. Zero extra dependencies. Done.

**Rule of thumb:** If you have <5 plugins, Homebrew direct install. If you have 10+, consider antidote or sheldon.

> **On Linux:** Zsh plugins install via apt (`zsh-autosuggestions`, `zsh-syntax-highlighting` packages) or git clone as fallback.

### Why fnm over nvm?

| | fnm | nvm |
|---|-----|-----|
| **Language** | Rust | Bash |
| **Shell startup** | ~1ms | ~200-400ms (or lazy-load hack) |
| **Fish support** | ✅ Native | ❌ Needs nvm.fish (separate project) |
| **Zsh support** | ✅ Native | ✅ Native |
| **Auto-switch** | ✅ `--use-on-cd` (reads `.node-version`, `.nvmrc`) | ⚠️ Needs hook script |
| **Install** | `brew install fnm` / `curl` | curl script, modifies shell rc |
| **Shared across shells** | ✅ Same Node installs for Fish & Zsh | ❌ nvm.fish and nvm-sh use different paths |

The killer reasons:
1. **Speed:** nvm adds 200-400ms to shell startup. fnm adds ~1ms. This matters when you open terminals frequently.
2. **Unified:** One tool, one Node install location (`~/.local/share/fnm/`), works identically in Fish and Zsh. With nvm, you'd need nvm-sh for Zsh and nvm.fish for Fish — two different tools with incompatible storage paths.
3. **Auto-switch:** `fnm env --use-on-cd` reads `.node-version` or `.nvmrc` files and switches automatically when you `cd` into a project. No extra hooks needed.
4. **nvm.fish is a community project**, not official nvm. It works well but it's another dependency with its own quirks (custom `nvm_data` path, `set --universal nvm_default_version`).

If you have existing `.nvmrc` files in your projects, fnm reads them — fully compatible.

### Why MesloLGS NF specifically?

- Designed for terminal use (monospace, clear at small sizes)
- Includes all Nerd Font glyphs (icons, powerline, devicons)
- Same font used by Powerlevel10k — battle-tested in terminals
- Available in Regular/Bold/Italic/Bold Italic

Alternatives: JetBrains Mono Nerd Font, Fira Code Nerd Font. All good choices. MesloLGS just has the widest compatibility.

### Why git-delta for diffs?

Git's default diff output is functional but ugly. Delta adds:
- Syntax highlighting in diffs
- Line numbers
- Side-by-side view
- Proper word-level diff highlighting
- Navigate between files with `n`/`N`

Configured globally — works with `git diff`, `git log -p`, `git show`, etc. Zero behavior change, just better output.

### Why zoxide over plain cd?

zoxide learns your most-used directories. After a few days:

```bash
z proj      # jumps to ~/projects (or wherever you go most with "proj" in the path)
z doc       # jumps to ~/Documents
zi          # interactive fuzzy selection with fzf
```

It's `cd` with a brain. Falls back to regular `cd` behavior for explicit paths.

### Why fzf?

The single most impactful CLI tool you can install:

- **Ctrl+R:** Fuzzy search through command history (replaces the terrible default reverse-i-search)
- **Ctrl+T:** Find any file by fuzzy name match
- **Alt+C:** cd into any directory by fuzzy match
- Integrates with `fd` automatically (faster than `find`, respects `.gitignore`)

Once you use fzf for a week, you can't go back.

## License

MIT
