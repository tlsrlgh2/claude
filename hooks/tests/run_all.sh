#!/bin/bash
# mask-secrets.sh 훅 테스트 일괄 실행. 하나라도 실패하면 exit 1
# 더미 파일(src/, xml/, .env)의 비밀값은 전부 가짜(FAKE_*)다 — 실제 민감 파일로 테스트하지 말 것
# (훅에 구멍이 있으면 진짜 값이 출력된다)
D=$(cd "$(dirname "$0")" && pwd)
bash -n ~/.claude/hooks/mask-secrets.sh || exit 1
python3 -I -c 'import ast,sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]' \
  ~/.claude/hooks/scan-bash-read.py ~/.claude/hooks/mask-xml.py || exit 1

fail=0
b=$(bash "$D/run_bash.sh");  echo "Bash 판정   : $(grep 합계 <<<"$b")"
g=$(bash "$D/run_grep.sh");  echo "Grep 판정   : $(grep 합계 <<<"$g")"
e=$(bash "$D/run_extra.sh"); echo "여러줄·성능 : OK=$(grep -c '^OK' <<<"$e") FAIL=$(grep -c '^FAIL' <<<"$e")"
m=$(bash "$D/run_mask.sh" 2>/dev/null)
echo "XML 마스킹  : $(grep -E '노출된|보존된' <<<"$m" | tr '\n' ' ')"
echo "EUC-KR/실패 : ✅ $(grep -c '^✅' <<<"$m") / ❌ $(grep -c '^❌' <<<"$m")"
echo "properties  : $(grep -c 'Password=\[MASKED\]' <<<"$m")줄 마스킹"

grep -h '^FAIL' <<<"$b"$'\n'"$g"$'\n'"$e" && fail=1
grep -q 'FAIL=[1-9]' <<<"$b$g" && fail=1
grep -q '^❌' <<<"$m" && fail=1
grep -q '노출된 비밀값: 없음' <<<"$m" || fail=1
grep -q 'Password=\[MASKED\]' <<<"$m" || fail=1

[[ $fail -eq 0 ]] && echo "==> 전체 통과" || echo "==> 실패 있음 (각 run_*.sh를 직접 실행해 상세 확인)"
exit $fail
