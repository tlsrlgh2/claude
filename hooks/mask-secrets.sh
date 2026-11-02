#!/bin/bash
# Claude Code PreToolUse hook: 민감 설정 파일 접근 시 비밀번호/IP 마스킹
# 대상: *.properties(전체), context.xml, context-datasource.xml, .env*
# - Read  : 원본 차단 후 마스킹된 내용을 대신 전달 (비밀번호·IP는 로컬 sed로 제거됨)
# - Bash  : 민감 파일명이 포함된 명령 차단 (cat 등 우회 방지)
# - Grep  : 민감 파일 직접 대상 검색 차단
set -euo pipefail

input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')

FILE_RE='(\.properties|context(-datasource)?\.xml|/\.env[A-Za-z0-9._-]*)$'
CMD_RE='\.properties|context(-datasource)?\.xml|(^|[ /"'\''=])\.env'

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

mask_file() {
  sed -E \
    -e 's/^([[:space:]]*#?[[:space:]]*[^=]*([Pp]assword|PASSWORD|[Pp]asswd|[Pp]wd|[Ss]ecret|SECRET|[Cc]redential)[^=]*=).*/\1[MASKED]/' \
    -e 's/(([Pp]assword|[Pp]asswd|[Pp]wd|[Ss]ecret)[[:space:]]*=[[:space:]]*")[^"]*(")/\1[MASKED]\3/g' \
    -e "s/(([Pp]assword|[Pp]asswd|[Pp]wd|[Ss]ecret)[[:space:]]*=[[:space:]]*')[^']*(')/\1[MASKED]\3/g" \
    -e 's/([0-9]{1,3}\.){3}[0-9]{1,3}/[MASKED_IP]/g' \
    "$1"
}

case "$tool" in
  Read)
    fp=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
    if [[ -n "$fp" && -f "$fp" ]] && printf '%s' "$fp" | grep -qiE "$FILE_RE"; then
      masked=$(mask_file "$fp")
      deny "[민감 설정 파일 — 원본 Read는 차단되었고, 아래는 비밀번호·IP가 로컬에서 마스킹된 내용입니다]
$masked"
    fi
    ;;
  Bash)
    cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
    if printf '%s' "$cmd" | grep -qiE "$CMD_RE"; then
      deny "민감 설정 파일(*.properties/context.xml/.env)은 Bash로 접근할 수 없습니다. Read 도구를 사용하세요 — 비밀번호·IP가 마스킹된 내용이 제공됩니다."
    fi
    ;;
  Grep)
    gp=$(printf '%s' "$input" | jq -r '.tool_input.path // empty')
    if [[ -n "$gp" ]] && printf '%s' "$gp" | grep -qiE "$FILE_RE"; then
      deny "민감 설정 파일은 Grep으로 직접 검색할 수 없습니다. Read 도구를 사용하세요 — 마스킹된 내용이 제공됩니다."
    fi
    ;;
esac

exit 0
