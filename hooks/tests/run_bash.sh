#!/bin/bash
# mask-secrets.sh Bash 분기(scan-bash-read.py) 판정 테스트 — 명령은 실행하지 않고 훅에 입력만 넣는다
H=~/.claude/hooks/mask-secrets.sh
D=$(cd "$(dirname "$0")" && pwd)
pass=0; fail=0
while IFS='|' read -r exp cmd; do
  [[ -z "$exp" || "$exp" == \#* ]] && continue
  s=$(date +%s%N)
  out=$(jq -n --arg d "$D" --arg c "$cmd" '{tool_name:"Bash",cwd:$d,tool_input:{command:$c}}' | bash "$H"); rc=$?
  ms=$(( ($(date +%s%N) - s) / 1000000 ))
  if printf '%s' "$out" | grep -q '"deny"'; then r="차단"; else r="통과"; fi
  [[ $rc -ne 0 ]] && r="오류($rc)"
  if [[ "$r" == "$exp" ]]; then m=OK; pass=$((pass+1)); else m=FAIL; fail=$((fail+1)); fi
  printf '%-4s 기대=%s 결과=%s %4dms  %s\n' "$m" "$exp" "$r" "$ms" "$(printf '%s' "$cmd" | head -1)"
done <<'CASES'
# ---- 차단 기대 ----
차단|grep -rn Password src
차단|grep -rn Password .
차단|grep -Rni password src
차단|grep -r -e foo -e Password src
차단|grep -rn "Url\|jdbc" src
차단|grep -rc Password src
차단|grep -rn Password src --include="*.prop*"
차단|timeout 5 grep -rn Password src
차단|cd src && grep -rn Password .
차단|grep -rn TOKEN .
차단|grep -rn FAKE_DS src
차단|rg -n jdbc src
차단|rg jdbc
차단|rg -n Password -t java src
차단|rg -n '(?<x' src
차단|rg --no-heading -e Password src
차단|git grep -n Password
차단|cat src/main/resources/egovframework/egovProps/*
차단|head -n 5 src/**/*
차단|sed -n '1,3p' src/main/resources/*/*/*
차단|awk '{print}' src/main/resources/egovframework/egovProps/*
차단|cat .e*
차단|find src -type f -exec cat {} +
차단|find . -name "*.prop*" -exec grep -n Url {} \;
차단|find src -type f | xargs grep -n Password
차단|find src -type f -print0 | xargs -0 cat
차단|grep -rl Password src | xargs cat
차단|ls src | xargs -I{} sh -c 'cat {}'
# ---- 통과 기대 ----
통과|grep -rl Password src
통과|grep -rn getPw src
통과|grep -rn Password src --include="*.java"
통과|grep -rn Password src/main/java
통과|rg -n Password -g "*.java" src
통과|rg -n Password -g '!*.prop*' -g '!*.xml' src
통과|rg -n Password -t js src
통과|rg --files src
통과|cat src/main/java/A.java
통과|head -n 20 src/main/java/*.java
통과|find src -name "*.java" -exec grep -n Password {} +
통과|find src -name "*.java" | xargs grep -n Password
통과|grep -rl Password src | xargs sed -i s/a/a/
통과|echo hi | grep hi
통과|git status && ls -la src
통과|git log --oneline | head -5
통과|cat > /tmp/x <<'EOF'
CASES
echo "합계: OK=$pass FAIL=$fail"
