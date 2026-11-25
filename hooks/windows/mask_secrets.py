#!/usr/bin/env python3
# [Windows용] Claude Code PreToolUse 훅 진입점 — Linux용 hooks/mask-secrets.sh와 같은 역할을 Python만으로 수행.
# ※ 판정·마스킹 규칙을 바꿀 때는 Linux용(mask-secrets.sh / scan-bash-read.py / mask-xml.py)도 같이 고칠 것.
#
# 대상 파일: *.properties, context.xml, context-datasource.xml, .env*
# - Read       : 원본 대신 비밀번호·IP를 가린 내용을 deny 사유로 전달 (properties + XML 형태)
# - Bash       : 민감 파일명이 들어간 명령 차단 + 폴더·와일드카드 읽기 명령 검사 (scan_bash_read)
# - PowerShell : 민감 파일명이 들어간 명령 차단 + Get-Content/Select-String/findstr 등 검사 (scan_powershell)
# - Grep       : 민감 파일 직접 검색 차단 + 폴더 검색(content/count)에서 민감 파일이 검색어에 걸리면 차단
#
# 차단: exit 0 + permissionDecision "deny" JSON.
# 예상치 못한 오류: exit 2 (Claude Code가 차단으로 처리) — 훅이 깨져서 보호 없이 통과되는 것(fail-open) 방지.
# 진단: 환경변수 MASK_HOOK_DEBUG=1 이면 받은 입력을 이 폴더의 debug-input.log에 남긴다.
import json
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import scan_bash_read as sb  # noqa: E402
import scan_powershell as sp  # noqa: E402
from mask_xml import mask_xml_text  # noqa: E402

CMD_RE = re.compile(r'\.properties|context(-datasource)?\.xml|(^|[\s/\\"\'=:])\.env', re.I)
SAFE_GREP_TYPES = {'js', 'ts', 'css', 'html', 'sql', 'py', 'sh', 'md'}  # java는 properties 포함, xml은 context.xml 포함

# Linux판 mask-secrets.sh의 sed 규칙과 동일
KEYS_LINE = r'(?:[Pp]assword|PASSWORD|[Pp]asswd|[Pp]wd|[Ss]ecret|SECRET|[Cc]redential)'
KEYS_ATTR = r'(?:[Pp]assword|[Pp]asswd|[Pp]wd|[Ss]ecret)'
SED_RULES = [
    (re.compile(r'^([ \t]*#?[ \t]*[^=\n]*' + KEYS_LINE + r'[^=\n]*=).*$', re.M), r'\1[MASKED]'),
    (re.compile(r'(' + KEYS_ATTR + r'[ \t]*=[ \t]*")[^"\n]*(")'), r'\1[MASKED]\2'),
    (re.compile(r"(" + KEYS_ATTR + r"[ \t]*=[ \t]*')[^'\n]*(')"), r'\1[MASKED]\2'),
    (re.compile(r'([0-9]{1,3}\.){3}[0-9]{1,3}'), '[MASKED_IP]'),
]


def out_json(obj):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=True).encode('ascii'))
    sys.stdout.flush()


def deny(reason):
    out_json({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                     'permissionDecisionReason': reason}})
    sys.exit(0)


def mask_file(path):
    text = sb.read_text(path).replace('\r\n', '\n')
    for rx, rep in SED_RULES:
        text = rx.sub(rep, text)
    return mask_xml_text(text)


def on_read(ti):
    fp = ti.get('file_path') or ''
    p = sb.native(fp)
    if fp and os.path.isfile(p) and sb.is_sensitive(p):
        try:
            masked = mask_file(p)
        except Exception:
            deny('민감 설정 파일 마스킹에 실패해 내용을 표시하지 않습니다. 사용자에게 필요한 값을 직접 확인해 달라고 요청하세요.')
        deny('[민감 설정 파일 — 원본 Read는 차단되었고, 아래는 비밀번호·IP가 로컬에서 마스킹된 내용입니다]\n' + masked)


def on_command(tool, ti, cwd):
    cmd = ti.get('command')
    if not isinstance(cmd, str):  # 필드 이름이 다르면 문자열 값 전체를 대상으로 (보수적)
        cmd = ' '.join(v for v in ti.values() if isinstance(v, str))
    if CMD_RE.search(cmd):
        deny('민감 설정 파일(*.properties/context.xml/.env)은 %s로 접근할 수 없습니다. '
             'Read 도구를 사용하세요 — 비밀번호·IP가 마스킹된 내용이 제공됩니다.' % tool)
    try:
        if tool == 'PowerShell':
            sp.check(cmd, cwd)
        else:
            sb.check(cmd, cwd)
    except sb.Deny as e:
        deny(str(e))


def on_grep(ti, cwd):
    gp = ti.get('path') or ''
    if gp and sb.is_sensitive(gp):
        deny('민감 설정 파일은 Grep으로 직접 검색할 수 없습니다. Read 도구를 사용하세요 — 마스킹된 내용이 제공됩니다.')
    if (ti.get('output_mode') or 'files_with_matches') == 'files_with_matches':
        return
    if (ti.get('type') or '') in SAFE_GREP_TYPES:
        return
    root = sb.native(gp) if gp else cwd
    if gp and not sb.isabs(root):
        root = sb.native(os.path.join(cwd, root))
    if not os.path.isdir(root):
        return
    guide = ('검색 범위에 민감 설정 파일(*.properties/context.xml/.env)이 포함되어 줄 내용이 노출될 수 있습니다. '
             'glob으로 대상 확장자를 좁히거나(예: "*.java"), output_mode를 files_with_matches로 바꾸세요. '
             '민감 파일 내용은 Read 도구로 보세요 — 마스킹된 내용이 제공됩니다.')
    try:
        files = sb.walk_sensitive(root)
    except sb.Deny:
        deny('민감 파일 검사 시간 초과. ' + guide)
    glob_ = ti.get('glob') or ''
    if glob_ and not any(c in glob_ for c in '{}'):  # 중괄호 등 해석 불확실한 glob은 매칭으로 간주(보수적)
        files = [f for f in files if sb.gmatch(glob_, f, root)]
    if not files:
        return
    if ti.get('multiline'):
        deny(guide)
    flags = ['-i'] if ti.get('-i') else []
    try:
        if sb.file_hits([ti.get('pattern') or ''], 'P', flags, files):
            deny(guide)
    except sb.Deny:
        deny('민감 파일 검사 시간 초과. ' + guide)


def debug_log(data):
    if os.environ.get('MASK_HOOK_DEBUG') != '1':
        return
    keep = {k: data.get(k) for k in ('tool_name', 'cwd', 'hook_event_name')}
    ti = data.get('tool_input') or {}
    keep['tool_input'] = {k: ti.get(k) for k in ('file_path', 'command', 'path', 'pattern', 'glob',
                                                 'output_mode', 'type') if k in ti}
    keep['tool_input_keys'] = sorted(ti.keys())
    keep['python'] = sys.version.split()[0]
    keep['os.name'] = os.name
    with open(os.path.join(HERE, 'debug-input.log'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(keep, ensure_ascii=False) + '\n')


def main():
    data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    debug_log(data)
    tool = data.get('tool_name') or ''
    ti = data.get('tool_input') or {}
    cwd = sb.native(data.get('cwd') or os.getcwd())
    if tool == 'Read':
        on_read(ti)
    elif tool in ('Bash', 'PowerShell'):
        on_command(tool, ti, cwd)
    elif tool == 'Grep':
        on_grep(ti, cwd)
    sys.exit(0)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # 예상치 못한 오류 → exit 2(차단). 사유는 stderr로 Claude에게 전달됨
        msg = '민감정보 훅 내부 오류로 안전을 위해 차단했습니다. 사용자에게 알려 주세요.\n' + traceback.format_exc(limit=3)
        sys.stderr.buffer.write(msg.encode('utf-8'))
        sys.exit(2)
