#!/bin/bash
# Claude Code status line
# Shows: current project directory | model name | weekly rate limit | 5h rate limit | context usage

input=$(cat)

model=$(echo "$input" | jq -r '.model.display_name // "unknown"')
cwd=$(echo "$input" | jq -r '.workspace.current_dir // empty')
[ -z "$cwd" ] && cwd="."

week_pct=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
five_pct=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
ctx_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')

# --- Weekly rate limit ---
if [ -n "$week_pct" ]; then
    week_str=$(awk -v p="$week_pct" 'BEGIN{printf "%.0f%%", p}')
else
    week_str="n/a"
fi

# --- 5-hour rate limit ---
if [ -n "$five_pct" ]; then
    five_str=$(awk -v p="$five_pct" 'BEGIN{printf "%.0f%%", p}')
else
    five_str="n/a"
fi

# --- Context usage ---
if [ -n "$ctx_pct" ]; then
    ctx_str=$(awk -v p="$ctx_pct" 'BEGIN{printf "%.0f%%", p}')
else
    ctx_str="n/a"
fi

# --- Colors (dimmed-friendly) ---
C_RESET='\033[0m'
C_DIR='\033[37m'
C_MODEL='\033[36m'
C_WEEK='\033[35m'
C_5H='\033[33m'
C_CTX='\033[32m'

printf "${C_DIR}%s${C_RESET} | ${C_MODEL}%s${C_RESET} | ${C_WEEK}week: %s${C_RESET} | ${C_5H}5h: %s${C_RESET} | ${C_CTX}ctx: %s${C_RESET}\n" \
    "$cwd" "$model" "$week_str" "$five_str" "$ctx_str"
