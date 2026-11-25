#!/usr/bin/env python3
# [Windows용] 민감정보 훅(mask_secrets.py) 테스트 — Windows/Linux 어디서나 실행 가능 (Python만 필요)
#   python run_all.py          → 마지막 줄 "==> 전체 통과" 이면 정상, 실패 시 exit 1
#   python run_all.py -v       → 모든 케이스 결과 출력
# 더미 파일(src/, xml/, .env)의 비밀값은 전부 가짜(FAKE_*)다. 실제 민감 파일로 테스트하지 말 것.
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass

D = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(D), 'mask_secrets.py')
VERBOSE = '-v' in sys.argv
results = {'ok': 0, 'fail': 0}


def run_hook(payload, env=None):
    e = dict(os.environ)
    e.pop('MASK_HOOK_DEBUG', None)
    if env:
        e.update(env)
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload).encode('utf-8'),
                       capture_output=True, env=e, timeout=60)
    out = p.stdout.decode('utf-8', 'replace')
    reason = ''
    try:
        reason = json.loads(out)['hookSpecificOutput']['permissionDecisionReason'] if out.strip() else ''
    except Exception:
        pass
    decision = '차단' if ('"deny"' in out or p.returncode == 2) else ('통과' if p.returncode == 0 else '오류(%d)' % p.returncode)
    return decision, reason, p


def expect(exp, label, got, extra=''):
    ok = exp == got
    results['ok' if ok else 'fail'] += 1
    if VERBOSE or not ok:
        print('%-4s 기대=%s 결과=%s  %s %s' % ('OK' if ok else 'FAIL', exp, got, label, extra))


def cmd_case(tool, exp, cmd, cwd=D):
    t = time.monotonic()
    got, _, p = run_hook({'tool_name': tool, 'cwd': cwd, 'tool_input': {'command': cmd}})
    ms = int((time.monotonic() - t) * 1000)
    err = p.stderr.decode('utf-8', 'replace').strip().splitlines()[-1:] if p.returncode not in (0,) else ''
    expect(exp, '[%s] %s' % (tool, cmd.replace('\n', ' / ')[:80]), got, '(%dms) %s' % (ms, err or ''))


# ---------------------------------------------------------------- 1. Bash (Git Bash) — Linux판과 같은 케이스
BASH = [
    ('차단', 'grep -rn Password src'), ('차단', 'grep -rn Password .'), ('차단', 'grep -Rni password src'),
    ('차단', 'grep -r -e foo -e Password src'), ('차단', 'grep -rn "Url\\|jdbc" src'), ('차단', 'grep -rc Password src'),
    ('차단', 'grep -rn Password src --include="*.prop*"'), ('차단', 'timeout 5 grep -rn Password src'),
    ('차단', 'cd src && grep -rn Password .'), ('차단', 'grep -rn TOKEN .'), ('차단', 'grep -rn FAKE_DS src'),
    ('차단', 'rg -n jdbc src'), ('차단', 'rg jdbc'), ('차단', 'rg -n Password -t java src'), ('차단', "rg -n '(?<x' src"),
    ('차단', 'rg --no-heading -e Password src'), ('차단', 'git grep -n Password'),
    ('차단', 'cat src/main/resources/egovframework/egovProps/*'), ('차단', 'head -n 5 src/**/*'),
    ('차단', "sed -n '1,3p' src/main/resources/*/*/*"), ('차단', "awk '{print}' src/main/resources/egovframework/egovProps/*"),
    ('차단', 'cat .e*'), ('차단', 'find src -type f -exec cat {} +'), ('차단', 'find . -name "*.prop*" -exec grep -n Url {} \\;'),
    ('차단', 'find src -type f | xargs grep -n Password'), ('차단', 'find src -type f -print0 | xargs -0 cat'),
    ('차단', 'grep -rl Password src | xargs cat'), ('차단', "ls src | xargs -I{} sh -c 'cat {}'"),
    ('차단', 'echo start\ngrep -rn Password src'), ('차단', 'grep -rn \\\n  Password src'),
    ('차단', 'cat > /tmp/x <<EOF\nhello\nEOF\ngrep -rn Password src'),
    ('차단', 'grep -rn Password "src\\main"'),                               # Windows식 역슬래시 경로
    ('차단', 'powershell -Command "gci -r src | sls Password"'),             # bash 안의 PowerShell
    ('차단', 'cmd //c "findstr /s jdbc *"'),
    ('차단', 'bash -c "grep -rn Password src"'),
    ('차단', 'cat src/main/resources/egovframework/egovProps/globals.properties'),  # 파일명 직접
    ('통과', 'grep -rl Password src'), ('통과', 'grep -rn getPw src'), ('통과', 'grep -rn Password src --include="*.java"'),
    ('통과', 'grep -rn Password src/main/java'), ('통과', 'rg -n Password -g "*.java" src'),
    ('통과', "rg -n Password -g '!*.prop*' -g '!*.xml' src"), ('통과', 'rg -n Password -t js src'), ('통과', 'rg --files src'),
    ('통과', 'cat src/main/java/A.java'), ('통과', 'head -n 20 src/main/java/*.java'),
    ('통과', 'find src -name "*.java" -exec grep -n Password {} +'), ('통과', 'find src -name "*.java" | xargs grep -n Password'),
    ('통과', 'grep -rl Password src | xargs sed -i s/a/a/'), ('통과', 'echo hi | grep hi'),
    ('통과', 'git status && ls -la src'), ('통과', 'git log --oneline | head -5'),
    ('통과', "cat > /tmp/x <<'EOF'\nit's grep -rn Password src\nEOF\necho done"),
    ('통과', 'git commit -m "$(cat <<\'EOF\'\nfix: don\'t cat *\nEOF\n)"'),
    ('통과', 'git commit -m "line1\nline2; cat *"'),
]

# ---------------------------------------------------------------- 2. PowerShell
ENC = base64.b64encode('gci -r src | sls Password'.encode('utf-16-le')).decode()
PS = [
    ('차단', r'Select-String -Path src\main\resources\egovframework\egovProps\* -Pattern Password'),
    ('차단', r'sls Password src\main\resources\egovframework\*\*'),
    ('차단', 'gci -r src | sls Password'),
    ('차단', 'Get-ChildItem src -Recurse -File | Select-String -Pattern jdbc'),
    ('차단', 'Get-ChildItem -Path . -Recurse -Include *.prop* | Select-String Url'),
    ('차단', 'gci src -Recurse | ForEach-Object { Get-Content $_.FullName }'),
    ('차단', 'gci -Recurse src | % { gc $_ }'),
    ('차단', r'Get-Content src\main\resources\egovframework\egovProps\*'),
    ('차단', 'gc src/main/resources/*/*/*'),
    ('차단', 'type .e*'),
    ('차단', 'findstr /s /i password *.*'),
    ('차단', 'findstr /S /C:"FAKE_DS" *'),
    ('차단', 'cmd /c "findstr /s jdbc *"'),
    ('차단', 'powershell -Command "gci -r src | sls Password"'),
    ('차단', 'pwsh -EncodedCommand ' + ENC),
    ('차단', 'rg -n jdbc src'),
    ('차단', 'git grep -n Password'),
    ('차단', r"sls -Path src\main\resources\egovframework\egovProps\* -Pattern '(?<x'"),
    ('차단', 'Get-ChildItem -Recurse | Select-String -NotMatch xyz'),
    ('차단', 'gci -s | sls TOKEN'),
    ('차단', '$r = $(gci -r src | sls Password); $r'),
    ('차단', 'Set-Location src; gci -r | sls Password'),
    ('차단', r'Get-Content src\main\resources\egovframework\egovProps\globals.properties'),  # 파일명 직접
    ('통과', 'gci -r src -Filter *.java | sls Password'),
    ('통과', r'sls -Path src\main\java\*.java -Pattern Password'),
    ('통과', 'gci -r src | sls getPw'),
    ('통과', 'gci -r src | sls Password -Quiet'),
    ('통과', 'findstr /s /m password *'),
    ('통과', 'Get-ChildItem -Recurse src | Select-Object Name'),
    ('통과', r'Get-Content src\main\java\A.java'),
    ('통과', 'git status'),
    ('통과', 'gci -r src -Include *.java | sls Password'),
    ('통과', 'rg -n Password -g "*.java" src'),
    ('통과', r'Select-String -Path src\* -Pattern Password'),
    ('통과', 'gci -r src -Directory | sls Password'),
    ('통과', 'Write-Output "hello" | Select-String hello'),
]

# ---------------------------------------------------------------- 3. Grep 도구
S = os.path.join(D, 'src')
GREP = [
    ('차단', '폴더 content', {'pattern': 'Password', 'path': S, 'output_mode': 'content'}),
    ('차단', 'path 생략(cwd)', {'pattern': 'Password', 'output_mode': 'content'}),
    ('차단', '상대경로 count', {'pattern': 'jdbc', 'path': 'src', 'output_mode': 'count'}),
    ('차단', '역슬래시 경로', {'pattern': 'jdbc', 'path': S.replace('/', '\\'), 'output_mode': 'content'}),
    ('차단', '-i', {'pattern': 'password', '-i': True, 'path': S, 'output_mode': 'content'}),
    ('차단', 'glob *.prop*', {'pattern': 'Url', 'glob': '*.prop*', 'path': S, 'output_mode': 'content'}),
    ('차단', 'glob 중괄호', {'pattern': 'Url', 'glob': '**/*.{java,xml}', 'path': S, 'output_mode': 'content'}),
    ('차단', '잘못된 정규식', {'pattern': '(?<x', 'path': S, 'output_mode': 'content'}),
    ('차단', 'multiline', {'pattern': 'Url', 'multiline': True, 'path': S, 'output_mode': 'content'}),
    ('차단', 'type=java', {'pattern': 'Password', 'type': 'java', 'path': S, 'output_mode': 'content'}),
    ('차단', '민감파일 직접', {'pattern': 'x', 'path': os.path.join(S, 'main', 'resources', 'egovframework', 'egovProps', 'globals.properties')}),
    ('통과', 'files_with_matches', {'pattern': 'Password', 'path': S}),
    ('통과', 'glob *.java', {'pattern': 'Password', 'glob': '*.java', 'path': S, 'output_mode': 'content'}),
    ('통과', '없는 검색어', {'pattern': 'getPw', 'path': S, 'output_mode': 'content'}),
    ('통과', '민감파일 없는 폴더', {'pattern': 'Password', 'path': os.path.join(S, 'main', 'java'), 'output_mode': 'content'}),
    ('통과', 'type=js', {'pattern': 'Password', 'type': 'js', 'path': S, 'output_mode': 'content'}),
]


def main():
    print('== 1. Bash 명령 판정')
    for exp, c in BASH:
        cmd_case('Bash', exp, c)
    print('== 2. PowerShell 명령 판정')
    for exp, c in PS:
        cmd_case('PowerShell', exp, c)
    print('== 3. Grep 도구 판정')
    for exp, label, ti in GREP:
        got, _, _ = run_hook({'tool_name': 'Grep', 'cwd': D, 'tool_input': ti})
        expect(exp, '[Grep] ' + label, got)

    print('== 4. Read 마스킹')
    props = os.path.join(D, 'src', 'main', 'resources', 'egovframework', 'egovProps', 'globals.properties')
    for label, path in (('properties', props), ('properties 역슬래시 경로', props.replace('/', '\\'))):
        got, reason, _ = run_hook({'tool_name': 'Read', 'tool_input': {'file_path': path}})
        ok = got == '차단' and 'Password=[MASKED]' in reason and 'FAKE' not in reason and '[MASKED_IP]' in reason
        expect('정상', '[Read] ' + label, '정상' if ok else '이상')
    got, reason, _ = run_hook({'tool_name': 'Read', 'tool_input': {'file_path': os.path.join(D, '.env').replace('/', '\\')}})
    expect('차단', '[Read] .env 역슬래시 경로', got)
    xml = os.path.join(D, 'xml', 'context-datasource.xml')
    got, reason, _ = run_hook({'tool_name': 'Read', 'tool_input': {'file_path': xml}})
    leaks = sorted(set(w for w in reason.replace('"', ' ').replace("'", ' ').replace('<', ' ').replace('>', ' ').split()
                       if w.startswith('FAKE_SECRET')))
    keep_src = set(w for w in open(xml, encoding='utf-8').read().replace('"', ' ').replace('<', ' ').replace('>', ' ').replace(':', ' ').split() if w.startswith('KEEP_'))
    keep_out = set(w for w in reason.replace('"', ' ').replace('<', ' ').replace('>', ' ').replace(':', ' ').split() if w.startswith('KEEP_'))
    expect('없음', '[Read] XML 11가지 형태 — 노출된 비밀값', ', '.join(leaks) or '없음')
    expect('%d' % len(keep_src), '[Read] XML 일반값 보존 개수', '%d' % len(keep_out & keep_src))

    tmp = tempfile.mkdtemp()
    try:
        ek = os.path.join(tmp, 'context.xml')
        with open(ek, 'wb') as f:
            f.write('<!-- 한글 주석 -->\n<property name="password" value="FAKE_SECRET_E"/>\n<property name="desc" value="한글값KEEP"/>\n'.encode('cp949'))
        got, reason, _ = run_hook({'tool_name': 'Read', 'tool_input': {'file_path': ek}})
        expect('정상', '[Read] EUC-KR(cp949) 파일', '정상' if ('FAKE_SECRET_E' not in reason and '한글값KEEP' in reason) else '이상')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print('== 5. 안전장치')
    p = subprocess.run([sys.executable, HOOK], input=b'{not json', capture_output=True, timeout=30)
    expect('2', '내부 오류 시 exit 2(차단)', str(p.returncode))
    got, _, _ = run_hook({'tool_name': 'Read', 'tool_input': {'file_path': os.path.join(D, 'src', 'main', 'java', 'A.java')}})
    expect('통과', '[Read] 일반 파일은 그대로', got)
    log = os.path.join(os.path.dirname(D), 'debug-input.log')
    if os.path.exists(log):
        os.remove(log)
    run_hook({'tool_name': 'Bash', 'cwd': D, 'tool_input': {'command': 'echo debug'}}, env={'MASK_HOOK_DEBUG': '1'})
    expect('생성', '진단 로그(MASK_HOOK_DEBUG=1)', '생성' if os.path.exists(log) else '없음')
    if os.path.exists(log):
        os.remove(log)
    p = subprocess.run([sys.executable, '-c', 'import sys; sys.path.insert(0, sys.argv[1]); import scan_bash_read as s; '
                        'print(s.native("/c/Users/x/a.txt"), s.native("C:\\\\Users\\\\x"))', os.path.dirname(D)],
                       capture_output=True, env=dict(os.environ, MASK_HOOK_FORCE_WIN='1'), timeout=30)
    expect('C:/Users/x/a.txt C:/Users/x', 'Git Bash 경로 변환(/c/ → C:/)', p.stdout.decode().strip())

    t = time.monotonic()
    run_hook({'tool_name': 'Bash', 'cwd': os.path.expanduser('~'), 'tool_input': {'command': 'grep -rn zzqq_none_xyz src'}})
    print('참고: 일반 명령 1회 판정 소요 %.2f초' % (time.monotonic() - t))

    print('합계: OK=%d FAIL=%d' % (results['ok'], results['fail']))
    print('==> 전체 통과' if results['fail'] == 0 else '==> 실패 있음 (python run_all.py -v 로 상세 확인)')
    sys.exit(0 if results['fail'] == 0 else 1)


if __name__ == '__main__':
    main()
