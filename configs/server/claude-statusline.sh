#!/usr/bin/env bash
# Claude Code status line: session token consumption + context window usage.
# Reads the statusline JSON from stdin and prints a single summary line.

input=$(cat)

# Read a field from .context_window (jq preferred, python3 fallback).
cw() {
  field=$1
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$input" | jq -r --arg f "$field" '.context_window[$f] // empty' 2>/dev/null
  else
    printf '%s' "$input" | FIELD="$field" python3 -c '
import json, os, sys
try:
    d = (json.load(sys.stdin).get("context_window") or {}).get(os.environ.get("FIELD", ""))
except Exception:
    d = None
sys.stdout.write("" if d is None else str(d))
' 2>/dev/null
  fi
}

total_in=$(cw total_input_tokens)
total_out=$(cw total_output_tokens)
size=$(cw context_window_size)
used_pct=$(cw used_percentage)

total_in=${total_in:-0}
total_out=${total_out:-0}
size=${size:-0}

# Total tokens consumed by the current conversation (input incl. cache + output).
session_tokens=$((total_in + total_out))

# Human-readable number: 950, 45.3k, 1.2M
fmt() {
  awk -v n="$1" 'BEGIN {
    if (n >= 1000000) printf "%.1fM", n / 1000000
    else if (n >= 1000) printf "%.1fk", n / 1000
    else printf "%d", n
  }'
}

# Percent of context window used (integer), empty when unknown.
pct=""
if [ -n "$used_pct" ] && [ "$size" -gt 0 ] 2>/dev/null; then
  pct=$(awk -v u="$used_pct" 'BEGIN { printf "%.0f", u }')
fi

# ANSI colors (status line renders dimmed, keep them subtle).
C_RESET=$(printf '\033[0m')
C_DIM=$(printf '\033[2m')
C_CYAN=$(printf '\033[36m')
C_GREEN=$(printf '\033[32m')
C_YELLOW=$(printf '\033[33m')
C_RED=$(printf '\033[31m')

ctx_color=$C_GREEN
if [ -n "$pct" ]; then
  if [ "$pct" -ge 90 ]; then
    ctx_color=$C_RED
  elif [ "$pct" -ge 70 ]; then
    ctx_color=$C_YELLOW
  fi
fi

out="${C_CYAN}Tokens: $(fmt "$session_tokens")${C_RESET}"
out="${out} ${C_DIM}|${C_RESET}"
if [ -n "$pct" ]; then
  out="${out} ${ctx_color}Ctx: $(fmt "$total_in")/$(fmt "$size") (${pct}%)${C_RESET}"
else
  out="${out} ${C_DIM}Ctx: $(fmt "$total_in")/$(fmt "$size")${C_RESET}"
fi

printf '%s' "$out"
