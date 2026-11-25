#!/usr/bin/env python3
# [Windows용] PowerShell / cmd 명령 검사기
# 폴더·와일드카드 대상 읽기 명령이 민감 설정 파일 내용을 출력할 수 있으면 scan_bash_read.Deny를 던진다.
# 판정 기준은 Bash 검사기와 같다: 범위 안 민감 파일이 검색어에 실제로 걸릴 때만 차단,
# 파일명만/참거짓만 출력(-Quiet, findstr /M)은 허용, 판정 불가는 차단.
#
# 대상:
#   Get-Content/gc/cat/type/more/Format-Hex/Import-Csv (와일드카드·파이프 입력)
#   Select-String/sls (-Path 와일드카드, 파이프 입력)
#   Get-ChildItem/gci/ls/dir [-Recurse] | Select-String / Get-Content / ForEach-Object { 읽기 }
#   findstr (/S 재귀, /M 파일명만), cmd /c, powershell|pwsh -Command / -EncodedCommand
#   그 밖의 외부 명령(rg, grep, git grep 등)은 Bash 검사기 규칙으로 판정
# 한계: 변수에 담은 경로($p), .NET 메서드 직접 호출([IO.File]::ReadAllText($x)), 스크립트 파일 실행
import base64
import os
import re

import scan_bash_read as sb
from scan_bash_read import Deny, GUIDE

GCI = {'get-childitem', 'gci', 'ls', 'dir', 'get-item', 'gi'}
GC = {'get-content', 'gc', 'cat', 'type', 'more', 'format-hex', 'fhx', 'import-csv', 'ipcsv'}
SLS = {'select-string', 'sls'}
FOREACH = {'foreach-object', '%', 'foreach'}
READ_IN_BLOCK = re.compile(r'(?i)\b(get-content|gc|cat|type|select-string|sls|format-hex|import-csv)\b'
                           r'|readall(text|lines|bytes)|\[io\.file\]|\[system\.io\.file\]|streamreader')

# 매개변수: 이름 → 값을 받는지(True) / 스위치(False). PowerShell은 접두어 축약(-Rec)을 허용한다
PARAMS = {
    'gci': {'path': True, 'literalpath': True, 'filter': True, 'include': True, 'exclude': True, 'recurse': False,
            'depth': True, 'file': False, 'directory': False, 'force': False, 'name': False, 'hidden': False,
            'attributes': True, 'followsymlink': False, 'system': False, 'readonly': False},
    'gc': {'path': True, 'literalpath': True, 'totalcount': True, 'head': True, 'tail': True, 'first': True,
           'last': True, 'readcount': True, 'raw': False, 'encoding': True, 'delimiter': True, 'wait': False,
           'filter': True, 'include': True, 'exclude': True, 'force': False, 'stream': True,
           'asbytestream': False},
    'sls': {'pattern': True, 'path': True, 'literalpath': True, 'simplematch': False, 'casesensitive': False,
            'quiet': False, 'list': False, 'notmatch': False, 'allmatches': False, 'include': True,
            'exclude': True, 'encoding': True, 'context': True, 'inputobject': True, 'noemphasis': False,
            'raw': False, 'culture': True},
}
POSITIONAL = {'gci': ['path', 'filter'], 'gc': ['path'], 'sls': ['pattern', 'path']}
# 공식 별칭(축약 접두어보다 우선): gci -r / -s 는 -Recurse
ALIASES = {'gci': {'r': 'recurse', 's': 'recurse', 'ad': 'directory', 'af': 'file', 'pspath': 'literalpath',
                   'lp': 'literalpath'},
           'gc': {'tc': 'totalcount', 'n': 'totalcount', 'pspath': 'literalpath', 'lp': 'literalpath'},
           'sls': {'cs': 'casesensitive', 'pspath': 'literalpath', 'lp': 'literalpath'}}


# ---------------------------------------------------------------- 분해
def split_ps(cmd):
    """문장 목록 → 각 문장은 파이프라인 단계 목록 → 각 단계는 토큰 목록.
    따옴표·중괄호·괄호 안은 한 덩어리로 유지. 백틱은 이스케이프."""
    stmts, stages, toks, cur = [], [], [], ''
    depth, quote, i = 0, None, 0

    def end_tok():
        nonlocal cur
        if cur != '':
            toks.append(cur)
        cur = ''

    def end_stage():
        nonlocal toks
        end_tok()
        if toks:
            stages.append(toks)
        toks = []

    def end_stmt():
        nonlocal stages
        end_stage()
        if stages:
            stmts.append(stages)
        stages = []

    cmd = cmd.replace('\r\n', '\n')
    while i < len(cmd):
        c = cmd[i]
        if quote:
            if c == '`' and quote == '"' and i + 1 < len(cmd):
                cur += cmd[i + 1]
                i += 2
                continue
            if c == quote:
                if i + 1 < len(cmd) and cmd[i + 1] == quote:  # '' 또는 "" 는 이스케이프된 따옴표
                    cur += c
                    i += 2
                    continue
                quote = None
                if depth:
                    cur += c
            else:
                cur += c
            i += 1
            continue
        if c in '\'"':
            quote = c
            if depth:
                cur += c
        elif c in '{(':
            depth += 1
            cur += c
        elif c in '})':
            depth = max(0, depth - 1)
            cur += c
        elif depth:
            cur += c
        elif c == '`' and i + 1 < len(cmd):
            if cmd[i + 1] == '\n':
                i += 2
                continue
            cur += cmd[i + 1]
            i += 2
            continue
        elif c in ' \t':
            end_tok()
        elif c == '|':
            if i + 1 < len(cmd) and cmd[i + 1] == '|':
                end_stmt()
                i += 2
                continue
            end_stage()
        elif c in ';\n':
            end_stmt()
        elif c == '&' and i + 1 < len(cmd) and cmd[i + 1] == '&':
            end_stmt()
            i += 2
            continue
        elif c == '#' and cur == '':
            while i < len(cmd) and cmd[i] != '\n':  # 주석
                i += 1
            continue
        else:
            cur += c
        i += 1
    end_stmt()
    return stmts


def subexprs(tok):
    """토큰 안의 (…) / $(…) / {…} 내부 문자열들 (중첩 명령 검사용)"""
    out, depth, start = [], 0, None
    for i, c in enumerate(tok):
        if c in '({':
            if depth == 0:
                start = i + 1
            depth += 1
        elif c in ')}':
            depth -= 1
            if depth == 0 and start is not None:
                out.append(tok[start:i])
    return out


def expand_vars(v):
    v = re.sub(r'(?i)\$env:([A-Za-z_][A-Za-z0-9_]*)', lambda m: os.environ.get(m.group(1), m.group(0)), v)
    v = re.sub(r'(?i)\$(home|pwd)\b', lambda m: os.path.expanduser('~') if m.group(1).lower() == 'home' else '.', v)
    return v


def parse_params(kind, toks):
    """→ (값 dict(이름 → 값 목록), 스위치 set, 위치 인자 목록)"""
    spec = PARAMS[kind]
    vals, sw, pos, i = {}, set(), [], 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if t.startswith('-') and len(t) > 1 and not re.match(r'^-\d', t):
            name, colon, inline = t[1:].partition(':')
            name = name.lower()
            cands = [k for k in spec if k.startswith(name)]
            full = ALIASES[kind].get(name) or (name if name in spec else (cands[0] if len(cands) == 1 else None))
            if full is None:
                # 모르는 매개변수: 값이 따라올 수 있으므로 다음 토큰이 '-'로 시작하지 않으면 값으로 소비
                if not colon and i < len(toks) and not toks[i].startswith('-'):
                    i += 1
                continue
            if spec[full]:
                v = inline if colon else (toks[i] if i < len(toks) else '')
                if not colon:
                    i += 1
                vals.setdefault(full, []).extend(x for x in v.split(',') if x != '')
            else:
                if not (colon and inline.lower() in ('$false', 'false', '0')):
                    sw.add(full)
        else:
            pos.append(t)
    for name, v in zip(POSITIONAL[kind], pos):
        if name not in vals:
            vals[name] = [x for x in v.split(',') if x != '']
    return vals, sw, pos[len(POSITIONAL[kind]):]


def unquote(v):
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in '\'"' else v


def resolve(v, cwd):
    v = unquote(expand_vars(v))
    if '$' in v:  # 해석할 수 없는 변수 → 범위 불명
        return None
    return sb.expand(v, cwd)


def ps_filter(files, filt, inc, exc, apply_inc):
    out = []
    for f in files:
        b = sb.native(f).split('/')[-1].lower()
        if filt and not any(sb.fnmatch.fnmatch(b, x.lower()) for x in filt):
            continue
        if apply_inc and inc and not any(sb.fnmatch.fnmatch(b, x.lower()) for x in inc):
            continue
        if apply_inc and exc and any(sb.fnmatch.fnmatch(b, x.lower()) for x in exc):
            continue
        out.append(f)
    return out


# ---------------------------------------------------------------- cmdlet별 판정
def gci_scope(toks, cwd):
    vals, sw, _ = parse_params('gci', toks)
    if 'directory' in sw:
        return []
    paths = vals.get('path', []) + vals.get('literalpath', []) or ['.']
    rec = 'recurse' in sw or 'depth' in vals
    files, wild = [], False
    for p in paths:
        wild = wild or any(c in p for c in '*?[')
        items = resolve(p, cwd)
        if items is None:
            return None
        for it in items:
            if os.path.isdir(it):
                if rec:
                    files += sb.walk_sensitive(it)
                else:  # 바로 아래 파일만
                    try:
                        files += [sb.native(os.path.join(it, x)) for x in os.listdir(it)
                                  if os.path.isfile(os.path.join(it, x)) and sb.is_sensitive(x)]
                    except OSError:
                        pass
            elif os.path.isfile(it) and sb.is_sensitive(it):
                files.append(it)
    # -Include/-Exclude는 -Recurse나 와일드카드 경로가 있을 때만 적용됨 (아니면 전부 포함 = 보수적)
    return ps_filter(files, vals.get('filter', []), vals.get('include', []), vals.get('exclude', []), rec or wild)


def sls_check(toks, cwd, prev):
    vals, sw, _ = parse_params('sls', toks)
    if 'quiet' in sw:
        return
    pats = [unquote(p) for p in vals.get('pattern', [])]
    if 'path' in vals or 'literalpath' in vals:
        files = []
        for p in vals.get('path', []) + vals.get('literalpath', []):
            items = resolve(p, cwd)
            if items is None:
                raise Deny(GUIDE)  # 경로를 알 수 없음
            files += [x for x in items if os.path.isfile(x) and sb.is_sensitive(x)]
        files = ps_filter(files, [], vals.get('include', []), vals.get('exclude', []), True)
    elif prev is not None:
        files = list(prev)
    else:
        return  # 문자열 입력 등
    if not files:
        return
    if not pats or 'notmatch' in sw:
        raise Deny(GUIDE)  # 검색어 불명 / 일치하지 않는 줄 출력 → 사실상 전체 출력
    mode = 'F' if 'simplematch' in sw else 'P'
    flags = [] if 'casesensitive' in sw else ['-i']  # Select-String 기본은 대소문자 무시
    if sb.file_hits(pats, mode, flags, files):
        raise Deny(GUIDE)


def gc_check(toks, cwd, prev):
    vals, sw, _ = parse_params('gc', toks)
    paths = vals.get('path', []) + vals.get('literalpath', [])
    if not paths:
        if prev:
            raise Deny(GUIDE)
        return
    for p in paths:
        items = resolve(p, cwd)
        if items is None:
            continue  # 변수 경로: 한계(의도적 우회 범주)
        if any(os.path.isfile(x) and sb.is_sensitive(x) for x in items):
            raise Deny(GUIDE)


def findstr_check(toks, cwd):
    rec = icase = listonly = invert = False
    pats, specs, literal_c = [], [], []
    for t in toks:
        u = unquote(t)
        if re.match(r'^/[A-Za-z]', u):
            o = u[1:].lower()
            if o.startswith('c:'):
                literal_c.append(unquote(u[3:]))
            elif o.startswith('g:') or o.startswith('f:'):
                raise Deny(GUIDE)  # 검색어/파일 목록을 파일에서 읽음 → 판정 불가
            else:
                for ch in o:
                    rec |= ch == 's'
                    icase |= ch == 'i'
                    listonly |= ch == 'm'
                    invert |= ch == 'v'
        elif not literal_c and not pats:
            pats = u.split()  # 공백으로 구분된 단어는 OR
        else:
            specs.append(u)
    pats = literal_c or pats
    if listonly or not specs:
        return
    files = []
    for s in specs:
        s = sb.native(s)
        if rec:
            d, _, pat = s.rpartition('/')
            root = sb.expand(d, cwd)[0] if d else cwd
            files += [f for f in sb.walk_sensitive(root) if sb.fnmatch.fnmatch(f.split('/')[-1].lower(), pat.lower())]
        else:
            files += [x for x in sb.expand(s, cwd) if os.path.isfile(x) and sb.is_sensitive(x)]
    if not files:
        return
    if invert or not pats:
        raise Deny(GUIDE)
    flags = ['-i'] if icase else []
    # findstr은 리터럴/정규식 해석이 상황마다 달라 둘 다 시도 (어느 쪽이든 걸리면 차단)
    if sb.file_hits(pats, 'F', flags, files) or sb.file_hits(pats, 'E', flags, files):
        raise Deny(GUIDE)


def inner_command(name, args):
    """powershell/pwsh -Command …, -EncodedCommand …, cmd /c … → 안쪽 명령 문자열 (없으면 None)"""
    args = [unquote(a) for a in args]
    if name == 'cmd':
        for k, a in enumerate(args):
            if a.lower() in ('/c', '/k', '//c', '//k'):  # Git Bash에서는 //c 로 씀
                return ' '.join(args[k + 1:])
        return None
    for k, a in enumerate(args):
        al = a.lower()
        if al in ('-command', '-c', '-com', '-comm', '-comma', '-comman'):
            return ' '.join(args[k + 1:])
        if al in ('-encodedcommand', '-enc', '-e', '-ec'):
            try:
                return base64.b64decode(args[k + 1]).decode('utf-16-le')
            except Exception:
                raise Deny(GUIDE)  # 해석 불가 → 차단
        if al in ('-file', '-f'):
            return None  # 스크립트 파일: 한계
    # 옵션 없이 바로 명령을 준 경우
    rest = [a for a in args if not a.startswith('-')]
    return ' '.join(rest) if rest else None


def check_stage(toks, cwd, prev):
    """한 파이프라인 단계 판정. 반환: 다음 단계로 넘길 파일 범위(None = 파일 아님)"""
    name = sb.cmdname(unquote(toks[0]))
    args = toks[1:]
    for t in toks:  # (…)/$(…)/{…} 안의 중첩 명령도 검사
        for inner in subexprs(t):
            check(inner, cwd)
    if name in ('&', '.') and args:  # & 'C:\x\rg.exe' … 호출 연산자
        return check_stage(args, cwd, prev)
    if name in GCI:
        return gci_scope(args, cwd)
    if name in SLS:
        sls_check(args, cwd, prev)
        return None
    if name in GC:
        gc_check(args, cwd, prev)
        return None
    if name in FOREACH:
        if prev and any(READ_IN_BLOCK.search(t) for t in args):
            raise Deny(GUIDE)
        return None
    if name == 'findstr':
        findstr_check(args, cwd)
        return None
    if name in ('powershell', 'pwsh', 'cmd'):
        inner = inner_command(name, args)
        if inner is not None:
            check(inner, cwd)
        return None
    if name in ('bash', 'sh'):
        if '-c' in args and args.index('-c') + 1 < len(args):
            sb.check(unquote(args[args.index('-c') + 1]), cwd)
        return None
    if name == 'cd' or name in ('set-location', 'sl', 'chdir', 'pushd'):
        return None
    # 외부 명령(rg, grep, git grep 등)은 Bash 검사기 규칙 적용
    if name == 'git' and args[:1] == ['grep']:
        return sb.check_tool('git-grep', [unquote(a) for a in args[1:]], cwd, None)
    if name in sb.GREPS or name in sb.DUMPERS:
        return sb.check_tool(name, [unquote(a) for a in args], cwd, prev if prev else None)
    return None


def check(cmd, cwd):
    cwd = sb.native(cwd)
    for stmt in split_ps(cmd):
        prev = None
        for stage in stmt:
            sb.tick()
            name = sb.cmdname(unquote(stage[0]))
            if name in ('cd', 'set-location', 'sl', 'chdir', 'pushd') and len(stage) > 1:
                d = resolve(stage[-1], cwd)
                if d and os.path.isdir(d[0]):
                    cwd = d[0]
                prev = None
                continue
            prev = check_stage(stage, cwd, prev)
