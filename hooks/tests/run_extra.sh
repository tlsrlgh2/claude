#!/bin/bash
# 여러 줄 명령 + 실제 규모 성능 테스트 (판정만, 명령은 실행하지 않음)
H=~/.claude/hooks/mask-secrets.sh
D=$(cd "$(dirname "$0")" && pwd)
t() { # $1=기대 $2=cwd $3=command
  s=$(date +%s%N)
  out=$(jq -n --arg d "$2" --arg c "$3" '{tool_name:"Bash",cwd:$d,tool_input:{command:$c}}' | bash "$H"); rc=$?
  ms=$(( ($(date +%s%N) - s) / 1000000 ))
  if printf '%s' "$out" | grep -q '"deny"'; then r="차단"; else r="통과"; fi
  [[ $rc -ne 0 ]] && r="오류($rc)"
  [[ "$r" == "$1" ]] && m=OK || m=FAIL
  printf '%-4s 기대=%s 결과=%s %5dms  %s\n' "$m" "$1" "$r" "$ms" "$(printf '%s' "$3" | tr '\n' '⏎' | cut -c1-70)"
}
echo "---- 여러 줄 / heredoc ----"
t 통과 "$D" $'cat > /tmp/x <<\'EOF\'\nit\'s grep -rn Password src\nEOF\necho done'
t 통과 "$D" $'git commit -m "$(cat <<\'EOF\'\nfix: don\'t cat *\nEOF\n)"'
t 차단 "$D" $'cat > /tmp/x <<EOF\nhello\nEOF\ngrep -rn Password src'
t 통과 "$D" $'python3 - <<\'EOF\'\nprint("it\'s ok")\nEOF'
t 차단 "$D" $'echo start\ngrep -rn Password src'
t 차단 "$D" $'grep -rn \\\n  Password src'
t 통과 "$D" $'git commit -m "line1\nline2; cat *"'
echo "---- 실제 규모 (~/git 전체 / 프로젝트 단위) ----"
t 통과 /home/ghsin/git "grep -rn zzqq_none_xyz ."
t 통과 /home/ghsin/git "rg -n zzqq_none_xyz"
for p in kigepe geme dmsnew2024; do
  [[ -d /home/ghsin/git/$p ]] && t 통과 "/home/ghsin/git/$p" "grep -rn zzqq_none_xyz src"
done
t 통과 /home/ghsin/git "ls -la && git -C kigepe status"
