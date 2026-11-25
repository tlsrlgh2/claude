#!/bin/bash
# Read 마스킹 테스트: FAKE_SECRET_* 는 전부 가려져야 하고 KEEP_* 는 남아야 한다
H=~/.claude/hooks/mask-secrets.sh
D=$(cd "$(dirname "$0")" && pwd)
X="$D/xml/context-datasource.xml"
reason() { jq -n --arg p "$1" '{tool_name:"Read",tool_input:{file_path:$p}}' | bash "$H" | jq -r '.hookSpecificOutput.permissionDecisionReason // "(차단 안 됨)"'; }

echo "==== 1. XML 형태별 마스킹 ===="
out=$(reason "$X")
leak=$(printf '%s' "$out" | grep -o 'FAKE_SECRET_[0-9]*' | sort -u | tr '\n' ' ')
keep_src=$(grep -o 'KEEP_[A-Z0-9]*' "$X" | sort -u | wc -l)
keep_out=$(printf '%s' "$out" | grep -o 'KEEP_[A-Z0-9]*' | sort -u | wc -l)
masked=$(printf '%s' "$out" | grep -o '\[MASKED\]' | wc -l)
echo "노출된 비밀값: ${leak:-없음}"
echo "보존된 일반값: $keep_out / $keep_src"
echo "[MASKED] 개수: $masked (비밀값 11개)"
echo "IP 마스킹: $(printf '%s' "$out" | grep -c 'MASKED_IP')줄"
echo "--- 마스킹 결과 ---"; printf '%s\n' "$out" | grep -vE '^\s*<!--'

echo; echo "==== 2. EUC-KR 파일 ===="
mkdir -p "$D/euckr"
python3 -I -c '
import sys
s = "<!-- 한글 주석 -->\n<property name=\"password\" value=\"FAKE_SECRET_E\"/>\n<property name=\"desc\" value=\"한글값KEEP\"/>\n"
open(sys.argv[1], "wb").write(s.encode("euc-kr"))' "$D/euckr/context.xml"
out=$(reason "$D/euckr/context.xml")
printf '%s' "$out" | grep -q FAKE_SECRET_E && echo "❌ 비밀값 노출" || echo "✅ 비밀값 가림"
printf '%s' "$out" | grep -q '마스킹에 실패' && echo "❌ 디코딩 실패로 차단됨" || echo "✅ 정상 표시 (EUC-KR 바이트 보존)"

echo; echo "==== 3. 마스킹 단계 실패 시 fail-closed ===="
B=$(mktemp -d)
for c in bash jq sed cat grep dirname env; do ln -s "$(command -v $c)" "$B/$c"; done   # python3 없는 PATH
out=$(jq -n --arg p "$X" '{tool_name:"Read",tool_input:{file_path:$p}}' | PATH="$B" bash "$H"); rc=$?
r=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecisionReason // empty' 2>/dev/null)
echo "exit=$rc"
if printf '%s' "$r" | grep -q '마스킹에 실패'; then echo "✅ 내용 없이 차단"; else echo "❌ 차단 안 됨 / 출력: $(printf '%s' "$out" | head -c 200)"; fi
printf '%s' "$out" | grep -q FAKE_SECRET && echo "❌ 비밀값 노출" || echo "✅ 비밀값 미노출"
rm -rf "$B"

echo; echo "==== 4. 기존 properties 회귀 ===="
reason "$D/src/main/resources/egovframework/egovProps/globals.properties"
