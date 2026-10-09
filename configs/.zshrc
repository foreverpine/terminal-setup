#!/bin/zsh
# ─── terminal-setup: Zsh config ─────────────────────────────────────
# Powered by: Starship + zsh-autosuggestions + zsh-syntax-highlighting + fzf + fnm

# Resolve user-installed tools before initializing the prompt; deduplicate PATH.
typeset -U path
path=("$HOME/.local/bin" "$HOME/.npm-global/bin" "$HOME/.opencode/bin" "$HOME/.local/share/fnm" $path)
export PATH

# ─── Homebrew ────────────────────────────────────────────────────────
if [[ -d /opt/homebrew ]]; then
    export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
    BREW_PREFIX="/opt/homebrew"
elif [[ -d /usr/local/Cellar ]]; then
    export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
    BREW_PREFIX="/usr/local"
else
    BREW_PREFIX=""
fi

# ─── Per-server environment (before tool discovery/init) ─────────────
# PATH, proxy and tool environment belong here. Use $HOME, not a username.
[[ -r "$HOME/.zshrc.env" ]] && source "$HOME/.zshrc.env"

# ─── pnpm ────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == darwin* ]]; then
    export PNPM_HOME="${PNPM_HOME:-$HOME/Library/pnpm}"
else
    export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
fi
path=("$PNPM_HOME" $path)
export PATH

# ─── Starship prompt ────────────────────────────────────────────────
if command -v starship &>/dev/null; then
    eval "$(starship init zsh)"
fi

# ─── Zsh plugins (via Homebrew) ──────────────────────────────────────
# Autosuggestions (fish-like suggestions)
if [[ -n "$BREW_PREFIX" && -f "$BREW_PREFIX/share/zsh-autosuggestions/zsh-autosuggestions.zsh" ]]; then
    source "$BREW_PREFIX/share/zsh-autosuggestions/zsh-autosuggestions.zsh"
elif [[ -f /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
    source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
    ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=8'
    ZSH_AUTOSUGGEST_STRATEGY=(history completion)
fi

# Completions
if [[ -n "$BREW_PREFIX" && -d "$BREW_PREFIX/share/zsh-completions" ]]; then
    fpath=("$BREW_PREFIX/share/zsh-completions" $fpath)
elif [[ -d /usr/share/zsh-completions ]]; then
    fpath=(/usr/share/zsh-completions $fpath)
fi
autoload -Uz compinit && compinit

# Substring + case-insensitive completion
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}' 'r:|=*' 'l:|=*'

# ─── History ─────────────────────────────────────────────────────────
HISTSIZE=100000
SAVEHIST=100000
HISTFILE=~/.zsh_history
setopt EXTENDED_HISTORY
setopt HIST_EXPIRE_DUPS_FIRST
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_SPACE
setopt SHARE_HISTORY
setopt INC_APPEND_HISTORY

# ─── History prefix search (↑/↓) ─────────────────────────────────────
# up-line-or-beginning-search: cursor stays at prefix position,
# matched tail shown as gray autosuggestion — type more to narrow.
autoload -U up-line-or-beginning-search down-line-or-beginning-search
zle -N up-line-or-beginning-search
zle -N down-line-or-beginning-search
bindkey '^[[A' up-line-or-beginning-search
bindkey '^[[B' down-line-or-beginning-search

# ─── fzf ─────────────────────────────────────────────────────────────
if [[ -f ~/.fzf.zsh ]]; then
    source ~/.fzf.zsh
elif command -v fzf &>/dev/null; then
    # Ubuntu 24.04 ships an older fzf without --zsh; use its packaged scripts.
    if _fzf_init="$(fzf --zsh 2>/dev/null)"; then
        eval "$_fzf_init"
    else
        [[ -r /usr/share/doc/fzf/examples/completion.zsh ]] && source /usr/share/doc/fzf/examples/completion.zsh
        [[ -r /usr/share/doc/fzf/examples/key-bindings.zsh ]] && source /usr/share/doc/fzf/examples/key-bindings.zsh
    fi
    unset _fzf_init
fi
export FZF_DEFAULT_OPTS='--height 40% --layout=reverse --border'
# Use fd for fzf if available
if command -v fd &>/dev/null; then
    export FZF_DEFAULT_COMMAND='fd --type f --hidden --follow --exclude .git'
    export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
    export FZF_ALT_C_COMMAND='fd --type d --hidden --follow --exclude .git'
fi

# ─── Zoxide (smart cd) ──────────────────────────────────────────────
if command -v zoxide &>/dev/null; then
    eval "$(zoxide init zsh)"
fi

# ─── fnm (Node version manager) ─────────────────────────────────────
if command -v fnm &>/dev/null; then
    eval "$(fnm env --use-on-cd --shell zsh)"
fi

# ─── Conda (portable detection; no forced base activation) ────────────
for _conda_base in "${CONDA_HOME:-$HOME/miniconda3}" "$HOME/anaconda3" "$HOME/miniforge3" "$HOME/mambaforge"; do
    if [[ -r "$_conda_base/etc/profile.d/conda.sh" ]]; then
        source "$_conda_base/etc/profile.d/conda.sh"
        break
    fi
done
unset _conda_base

# ─── SSH key switcher (fallback for multi-account setups) ────────────
# Usage: set-ssh-key lewis-official-20260224
# Prefer ~/.ssh/config Host aliases for automatic matching.
# This is a fallback for edge cases where you need to force a specific key.
function set-ssh-key() {
    local key="$HOME/.ssh/$1"
    if [[ ! -f "$key" ]]; then
        echo "Key not found: $key" >&2
        echo "Available keys:" >&2
        ls ~/.ssh/*.pub 2>/dev/null | sed 's/.*\//  /; s/\.pub$//' >&2
        return 1
    fi
    ssh-add -D 2>/dev/null
    ssh-add "$key"
    echo "Active SSH key: $1"
}

# ─── Aliases ─────────────────────────────────────────────────────────
if command -v eza &>/dev/null; then
    alias ls='eza --icons --group-directories-first'
    alias l='eza -l --icons --group-directories-first'
    alias la='eza -la --icons --group-directories-first'
    alias ll='eza -la --icons --group-directories-first'
    alias lt='eza --tree --icons --level=2'
else
    alias ll='ls -alF'
fi
command -v bat &>/dev/null && alias cat='bat'
command -v fd &>/dev/null && alias find='fd'
command -v rg &>/dev/null && alias grep='rg'
command -v btop &>/dev/null && alias top='btop'
command -v lazygit &>/dev/null && alias lg='lazygit'

# ─── Local overrides (not versioned; machine/personal) ───────────────
# Shared commands installed with the Git-backed server profile.
[[ -r "$HOME/.config/terminal-setup/ccm.zsh" ]] && source "$HOME/.config/terminal-setup/ccm.zsh"

# Put personal functions, aliases and ZLE widgets in ~/.zshrc.local.
# Use ~/.zshrc.env for PATH/proxy needed by the initializers above.
# Syntax highlighting is loaded below, after all local widgets.
[[ -r "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"

# ─── zsh-syntax-highlighting ──────────────────────────────────────────
# Load this at the very end of .zshrc so widgets created by compinit,
# zle -N, and other plugins are included in syntax highlighting.
if [[ -n "$BREW_PREFIX" && -f "$BREW_PREFIX/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]]; then
    source "$BREW_PREFIX/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
elif [[ -f /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
    source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi
