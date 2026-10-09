# Shared ccm/ccc functions. Personal overrides may follow in ~/.zshrc.local.
unalias ccm 2>/dev/null || true
unset -f ccm 2>/dev/null || true
ccm() {
  local script="${HOME}/.local/share/ccm/ccm.sh"
  if [[ ! -f "$script" ]]; then
    local default1="${XDG_DATA_HOME:-$HOME/.local/share}/ccm/ccm.sh"
    local default2="$HOME/.ccm/ccm.sh"
    if [[ -f "$default1" ]]; then
      script="$default1"
    elif [[ -f "$default2" ]]; then
      script="$default2"
    fi
  fi
  if [[ ! -f "$script" ]]; then
    echo "ccm error: script not found at $script" >&2
    return 1
  fi

  case "$1" in
    ""|"help"|"-h"|"--help"|"status"|"st"|"config"|"cfg"|"save-account"|"switch-account"|"list-accounts"|"delete-account"|"current-account"|"debug-keychain"|"project")
      "$script" "$@"
      ;;
    *)
      eval "$("$script" "$@")"
      ;;
  esac
}

unalias ccc 2>/dev/null || true
unset -f ccc 2>/dev/null || true
ccc() {
  if [[ $# -eq 0 ]]; then
    echo "Usage: ccc <model> [region|variant] [claude-options]"
    echo "       ccc open <provider> [claude-options]"
    echo "       ccc <account> [claude-options]"
    echo "       ccc <model>:<account> [claude-options]"
    return 1
  fi

  local model=""
  local open_provider=""
  local region_arg=""
  local seed_variant=""

  if [[ "$1" == "open" ]]; then
    shift || true
    if [[ $# -lt 1 ]]; then
      echo "Usage: ccc open <provider> [claude-options]"
      return 1
    fi
    model="open"
    open_provider="$1"
    shift || true
  else
    model="$1"
    shift || true
  fi

  _is_known_model() {
    case "$1" in
      deepseek|ds|glm|glm5|kimi|kimi2|qwen|minimax|mm|seed|doubao|claude|sonnet|s|open)
        return 0 ;;
      *)
        return 1 ;;
    esac
  }

  if [[ "$model" != "open" ]] && [[ "$model" != *:* ]] && ! _is_known_model "$model" && [[ ! "$model" =~ ^- ]]; then
    local account="$model"
    echo "Switching account to $account..."
    ccm switch-account "$account" || return 1
    ccm current-account || true
    ccm claude || return 1
  else
    if [[ "$model" == "open" ]]; then
      echo "Switching to OpenRouter ($open_provider)..."
      ccm open "$open_provider" || return 1
    else
      case "$model" in
        kimi|kimi2|qwen|glm|glm5|minimax|mm)
          if [[ "${1:-}" =~ ^(global|china|cn)$ ]]; then
            region_arg="$1"
            shift || true
          fi
          ;;
        seed|doubao)
          if [[ "${1:-}" =~ ^(doubao|glm|glm5|deepseek|ds|kimi|kimi2)$ ]]; then
            seed_variant="$1"
            shift || true
          fi
          ;;
      esac

      if [[ -n "$seed_variant" ]]; then
        echo "Switching to $model ($seed_variant)..."
        ccm "$model" "$seed_variant" || return 1
      elif [[ -n "$region_arg" ]]; then
        echo "Switching to $model ($region_arg)..."
        ccm "$model" "$region_arg" || return 1
      else
        echo "Switching to $model..."
        ccm "$model" || return 1
      fi
    fi
  fi

  local claude_args=("$@")

  echo ""
  echo "Launching Claude Code..."
  echo "   Model: $ANTHROPIC_MODEL"
  echo "   Base URL: ${ANTHROPIC_BASE_URL:-Default (Anthropic)}"
  echo ""

  if ! type -p claude >/dev/null 2>&1; then
    echo "'claude' CLI not found. Install: npm install -g @anthropic-ai/claude-code" >&2
    return 127
  fi

  if [[ ${#claude_args[@]} -eq 0 ]]; then
    exec claude
  else
    exec claude "${claude_args[@]}"
  fi
}
# <<< ccm function end <<<
