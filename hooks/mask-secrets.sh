#!/bin/bash
# Claude Code PreToolUse hook: 민감 설정 파일 접근 시 비밀번호/IP 마스킹
# 대상: *.properties(전체), context.xml, context-datasource.xml, .env*
# - Read  : 원본 차단 후 마스킹된 내용을 대신 전달 (비밀번호·IP는 로컬 sed로 제거됨)
# - Bash  : 민감 파일명이 포함된 명령 차단 (cat 등 우회 방지)
#           + 폴더·와일드카드 대상 읽기 명령이 민감 파일 내용을 출력할 수 있으면 차단 (scan-bash-read.py)
# - Grep  : 민감 파일 직접 대상 검색 차단 + 폴더 검색(content/count 모드)에서
#           범위 내 민감 파일이 검색어에 걸리면 차단 (판정 불가 시 차단, fail-closed)
#           ※ Linux 기본 설정에서는 Grep 도구가 비활성이라 검색은 대부분 Bash grep으로 들어온다
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
    "$1" \
  | python3 -I "$(dirname "$0")/mask-xml.py"   # XML 형태(<property name="password" value=...> 등) 보완
}

case "$tool" in
  Read)
    fp=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
    if [[ -n "$fp" && -f "$fp" ]] && printf '%s' "$fp" | grep -qiE "$FILE_RE"; then
      # 마스킹 실패 시 훅이 오류 종료하면 Read가 원본으로 실행됨(fail-open) → 내용 없이 차단
      masked=$(mask_file "$fp") || deny "민감 설정 파일 마스킹에 실패해 내용을 표시하지 않습니다. 사용자에게 필요한 값을 직접 확인해 달라고 요청하세요."
      deny "[민감 설정 파일 — 원본 Read는 차단되었고, 아래는 비밀번호·IP가 로컬에서 마스킹된 내용입니다]
$masked"
    fi
    ;;
  Bash)
    cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
    if printf '%s' "$cmd" | grep -qiE "$CMD_RE"; then
      deny "민감 설정 파일(*.properties/context.xml/.env)은 Bash로 접근할 수 없습니다. Read 도구를 사용하세요 — 비밀번호·IP가 마스킹된 내용이 제공됩니다."
    fi

    # 폴더·와일드카드 대상 읽기 명령(grep -r, rg, cat *, find -exec, xargs 등) 검사 → scan-bash-read.py
    # 읽기 명령 단어가 없으면 생략(성능). 검사기 실패·시간 초과는 차단(fail-closed)
    if printf '%s' "$cmd" | grep -qE 'grep|rg|ag|ack|find|xargs|cat|tac|head|tail|less|more|nl|od|xxd|hexdump|strings|sed|awk|cut|sort|uniq|paste|diff|cmp|base64|column|fold|fmt|jq|iconv|vi|view|nano|bat'; then
      reason=$(printf '%s' "$input" | timeout 25 python3 -I "$(dirname "$0")/scan-bash-read.py" 2>/dev/null) \
        || reason="민감 파일 검사기 실행 실패(fail-closed). 명령 범위를 좁혀 다시 시도하세요."
      [[ -n "$reason" ]] && deny "$reason"
    fi
    ;;
  Grep)
    gp=$(printf '%s' "$input" | jq -r '.tool_input.path // empty')
    if [[ -n "$gp" ]] && printf '%s' "$gp" | grep -qiE "$FILE_RE"; then
      deny "민감 설정 파일은 Grep으로 직접 검색할 수 없습니다. Read 도구를 사용하세요 — 마스킹된 내용이 제공됩니다."
    fi

    # 폴더 검색(path 생략 = cwd): 줄 내용이 노출되는 content/count 모드에서
    # 범위 안의 민감 파일이 검색어에 걸리면 차단. 판정 불가 시 차단(fail-closed).
    mode=$(printf '%s' "$input" | jq -r '.tool_input.output_mode // "files_with_matches"')
    [[ "$mode" == "files_with_matches" ]] && exit 0

    # type이 민감 파일을 포함할 수 없는 언어면 통과 (허용 목록 — 목록 밖은 아래 검사)
    # ※ java는 ripgrep 정의상 *.properties 포함, xml은 context*.xml 포함 → 넣지 말 것
    typ=$(printf '%s' "$input" | jq -r '.tool_input.type // empty')
    case "$typ" in
      js|ts|css|html|sql|py|sh|md) exit 0 ;;
    esac

    hcwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
    root=${gp:-${hcwd:-.}}
    [[ "$root" != /* && -n "$hcwd" ]] && root="$hcwd/$root"
    [[ -d "$root" ]] || exit 0

    pat=$(printf '%s' "$input" | jq -r '.tool_input.pattern // empty')
    glob=$(printf '%s' "$input" | jq -r '.tool_input.glob // empty')
    icase=$(printf '%s' "$input" | jq -r '.tool_input["-i"] // false')
    multi=$(printf '%s' "$input" | jq -r '.tool_input.multiline // false')
    GUIDE="검색 범위에 민감 설정 파일(*.properties/context.xml/.env)이 포함되어 줄 내용이 노출될 수 있습니다. glob으로 대상 확장자를 좁히거나(예: \"*.java\"), output_mode를 files_with_matches로 바꾸세요. 민감 파일 내용은 Read 도구로 보세요 — 마스킹된 내용이 제공됩니다."

    sens=$(timeout 10 find "$root" \( -name .git -o -name node_modules \) -prune -o -type f \
             \( -name '*.properties' -o -name context.xml -o -name context-datasource.xml -o -name '.env*' \) -print 2>/dev/null) \
      || frc=$?
    [[ ${frc:-0} -eq 124 ]] && deny "민감 파일 검사 시간 초과. $GUIDE"
    [[ -z "$sens" ]] && exit 0

    gopt=(-q -P); [[ "$icase" == "true" ]] && gopt+=(-i)
    while IFS= read -r f; do
      # 바깥 훅 timeout(settings.json 30초)에 걸리면 fail-open이 되므로 그 전에 스스로 차단
      (( SECONDS > 20 )) && deny "민감 파일 검사 시간 초과. $GUIDE"
      # glob 필터: 중괄호 등 해석 불확실한 glob은 매칭으로 간주(보수적)
      if [[ -n "$glob" && "$glob" != *[{}]* ]]; then
        rel=${f#"$root"/}
        # shellcheck disable=SC2053
        [[ "${f##*/}" == $glob || "$rel" == $glob ]] || continue
      fi
      [[ "$multi" == "true" ]] && deny "$GUIDE"
      rc=0; grep "${gopt[@]}" -e "$pat" -- "$f" 2>/dev/null || rc=$?
      [[ $rc -ne 1 ]] && deny "$GUIDE"   # 0=매칭, 2=정규식 해석 실패 → 차단
    done <<< "$sens"
    ;;
esac

exit 0
