#!/bin/bash
# mask-secrets.sh Grep 폴더 검색 판정 테스트
H=~/.claude/hooks/mask-secrets.sh
D=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$D/src/main/java"
printf 'class A { String Password = getPw(); }\n' > "$D/src/main/java/A.java"
pass=0; fail=0
g() { # $1=기대(차단/통과) $2=라벨 $3=tool_input json
  out=$(jq -n --arg d "$D" --argjson ti "$3" '{tool_name:"Grep",cwd:$d,tool_input:$ti}' | bash "$H"); rc=$?
  if printf '%s' "$out" | grep -q '"deny"'; then r="차단"; else r="통과"; fi
  [[ $rc -ne 0 ]] && r="오류(exit $rc)"
  if [[ "$r" == "$1" ]]; then mark=OK; pass=$((pass+1)); else mark=FAIL; fail=$((fail+1)); fi
  printf '%-4s 기대=%s 결과=%s  %s\n' "$mark" "$1" "$r" "$2"
}
S="$D/src"
g 차단 "폴더 content Password"            "{\"pattern\":\"Password\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 차단 "path 생략(cwd) content"           '{"pattern":"Password","output_mode":"content"}'
g 차단 "상대경로 src, count"              '{"pattern":"jdbc","path":"src","output_mode":"count"}'
g 차단 "-i password"                      "{\"pattern\":\"password\",\"-i\":true,\"path\":\"$S\",\"output_mode\":\"content\"}"
g 차단 "glob *.prop*"                     "{\"pattern\":\"Url\",\"glob\":\"*.prop*\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 차단 "glob 중괄호(해석 불확실)"         "{\"pattern\":\"Url\",\"glob\":\"**/*.{java,xml}\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 차단 "잘못된 정규식(fail-closed)"       "{\"pattern\":\"(?<x\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 차단 "multiline"                        "{\"pattern\":\"Url\",\"multiline\":true,\"path\":\"$S\",\"output_mode\":\"content\"}"
g 통과 "files_with_matches(기본 모드)"    "{\"pattern\":\"Password\",\"path\":\"$S\"}"
g 통과 "glob *.java content"              "{\"pattern\":\"Password\",\"glob\":\"*.java\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 통과 "민감파일에 없는 검색어"           "{\"pattern\":\"getPw\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 통과 "민감파일 없는 폴더"               "{\"pattern\":\"Password\",\"path\":\"$S/main/java\",\"output_mode\":\"content\"}"
g 차단 "type=java (ripgrep java에 properties 포함)" "{\"pattern\":\"Password\",\"type\":\"java\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 차단 "type=xml (context.xml 포함)"      "{\"pattern\":\"Url\",\"type\":\"xml\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 차단 "type=목록 밖(jsp 등 미정의)"       "{\"pattern\":\"Password\",\"type\":\"jsp\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 통과 "type=js content"                  "{\"pattern\":\"Password\",\"type\":\"js\",\"path\":\"$S\",\"output_mode\":\"content\"}"
g 통과 "type=sql count"                   "{\"pattern\":\"Password\",\"type\":\"sql\",\"path\":\"$S\",\"output_mode\":\"count\"}"
echo "합계: OK=$pass FAIL=$fail"
echo "---- 성능: ~/git 전체, 매칭 없는 검색어 ----"
s=$(date +%s.%N)
out=$(jq -n '{tool_name:"Grep",cwd:"/home/ghsin/git",tool_input:{pattern:"zzqq_none_xyz",output_mode:"content"}}' | bash "$H"); rc=$?
e=$(date +%s.%N)
printf 'exit=%s deny=%s 소요=%.2fs\n' "$rc" "$(printf '%s' "$out" | grep -c deny)" "$(echo "$e - $s" | bc)"
