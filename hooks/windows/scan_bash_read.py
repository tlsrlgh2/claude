#!/usr/bin/env python3
# [Windows용] Bash(Git Bash) 명령 검사기 — Linux용 hooks/scan-bash-read.py를 복사해 Windows에 맞게 수정한 것.
# ※ 판정 규칙을 바꿀 때는 Linux용 hooks/scan-bash-read.py도 같이 고칠 것.
#
# 폴더·와일드카드 대상 명령이 민감 설정 파일(properties / context.xml / context-datasource.xml / .env*)
# 의 "내용"을 출력할 수 있으면 Deny 예외를 던진다.
# Linux판과의 차이:
#   - 경로 정규화: 역슬래시 → 슬래시, Git Bash 형식 /c/... → C:/... (Windows에서만)
#   - 검색어 매칭: 외부 grep 대신 Python re (BRE/ERE/고정문자열/PCRE 근사, 해석 실패 시 걸린 것으로 간주)
#   - 이름 비교: 대소문자 무시, .exe 제거
#   - 중첩 셸: powershell/pwsh -Command, cmd /c 는 scan_powershell로 넘겨 검사
import fnmatch
import glob
import os
import re
import shlex
import time

WIN = os.name == 'nt' or os.environ.get('MASK_HOOK_FORCE_WIN') == '1'
T0 = time.monotonic()
BUDGET = 20  # 초. 바깥 훅 timeout(30초) 전에 스스로 차단으로 끝낸다
PRUNE = {'.git', 'node_modules'}
GUIDE = ('민감 설정 파일(properties/context.xml/.env)의 내용이 출력될 수 있는 명령입니다. '
         '검색은 --include(rg는 -g, Select-String은 -Include)로 대상 확장자를 좁히거나(예: "*.java") '
         '파일명만 출력하는 옵션(-l)으로 바꾸고, 민감 파일 내용은 Read 도구로 보세요 — 마스킹된 내용이 제공됩니다.')

GREPS = {'grep', 'egrep', 'fgrep', 'zgrep', 'rg', 'ag', 'ack', 'git-grep'}
DUMPERS = {'cat', 'tac', 'head', 'tail', 'less', 'more', 'nl', 'od', 'xxd', 'hexdump', 'strings',
           'sed', 'awk', 'gawk', 'mawk', 'cut', 'sort', 'uniq', 'paste', 'diff', 'cmp', 'base64',
           'column', 'fold', 'fmt', 'jq', 'iconv', 'vi', 'vim', 'view', 'nano', 'zcat', 'bat', 'batcat',
           'type'}
SHELLS = {'sh', 'bash', 'zsh', 'dash'}
PS_SHELLS = {'powershell', 'pwsh', 'cmd'}
WRAPPERS = {'sudo', 'env', 'command', 'builtin', 'time', 'nice', 'nohup', 'stdbuf', 'exec'}
SAFE_RG_TYPES = {'js', 'ts', 'css', 'html', 'sql', 'py', 'sh', 'md'}


class Deny(Exception):
    pass


def tick():
    if time.monotonic() - T0 > BUDGET:
        raise Deny('민감 파일 검사 시간 초과. ' + GUIDE)


def cmdname(tok):
    """명령 이름 정규화: 경로 제거, 소문자, .exe 제거"""
    b = re.split(r'[\\/]', tok)[-1].lower()
    return b[:-4] if b.endswith('.exe') else b


def native(p):
    """경로 정규화: 역슬래시 → 슬래시, (Windows) /c/x → C:/x"""
    p = p.replace('\\', '/')
    if WIN:
        m = re.match(r'^/([A-Za-z])(/|$)', p)
        if m:
            p = m.group(1).upper() + ':/' + p[3:]
    return p


def isabs(p):
    return p.startswith('/') or bool(re.match(r'^[A-Za-z]:/', p))


def is_sensitive(p):
    b = native(p).rstrip('/').split('/')[-1].lower()
    return b.endswith('.properties') or b in ('context.xml', 'context-datasource.xml') or b.startswith('.env')


def walk_sensitive(root):
    root = native(root)
    if os.path.isfile(root):
        return [root] if is_sensitive(root) else []
    out = []
    for d, dirs, files in os.walk(root):
        tick()
        dirs[:] = [x for x in dirs if x not in PRUNE]
        out += [native(os.path.join(d, f)) for f in files if is_sensitive(f)]
    return out


def braces(s):
    m = re.search(r'\{([^{}]*,[^{}]*)\}', s)
    if not m:
        return [s]
    out = []
    for part in m.group(1).split(','):
        out += braces(s[:m.start()] + part + s[m.end():])
    return out


def expand(tok, cwd):
    res = []
    for v in braces(os.path.expanduser(native(tok))):
        v = native(v)
        p = v if isabs(v) else native(os.path.join(native(cwd), v))
        if any(c in v for c in '*?['):
            res += [native(x) for x in glob.glob(p, recursive=True)]  # bash보다 넓게 펼쳐 보수적으로 판정
        else:
            res.append(p)
    return res


def gmatch(pat, path, root):
    path, root = native(path), native(root) if root else root
    rel = native(os.path.relpath(path, root)) if root else path
    b = path.split('/')[-1]
    for p in braces(native(pat)):
        q = p[3:] if p.startswith('**/') else p
        if any(fnmatch.fnmatch(x.lower(), y.lower()) for x in (b, rel) for y in (p, q)):
            return True
    return False


def in_type(t, f):
    b = native(f).split('/')[-1].lower()
    if t in SAFE_RG_TYPES:
        return False
    if t == 'java':
        return b.endswith('.properties')
    if t == 'xml':
        return b.endswith('.xml')
    return True  # 알 수 없는 type → 포함으로 간주(보수적)


def type_excludes(t, f):
    b = native(f).split('/')[-1].lower()
    if t == 'java':
        return b.endswith('.properties')
    if t == 'xml':
        return b.endswith('.xml')
    return False


# ---------------------------------------------------------------- 검색어 매칭 (Python re)
POSIX_CLASSES = {'[:digit:]': '0-9', '[:alpha:]': 'a-zA-Z', '[:alnum:]': 'a-zA-Z0-9', '[:upper:]': 'A-Z',
                 '[:lower:]': 'a-z', '[:space:]': r'\s', '[:blank:]': r' \t', '[:xdigit:]': '0-9A-Fa-f',
                 '[:punct:]': r'!-/:-@\[-`{-~', '[:word:]': r'\w'}


def bre_to_ere(p):
    out, i = [], 0
    while i < len(p):
        c = p[i]
        if c == '\\' and i + 1 < len(p):
            n = p[i + 1]
            out.append(n if n in '(){}|+?' else '\\' + n)
            i += 2
            continue
        out.append('\\' + c if c in '(){}|+?' else c)
        i += 1
    return ''.join(out)


def compile_pats(pats, mode, flags):
    """mode: G(BRE) E(ERE) F(고정) P(PCRE/ripgrep/.NET 근사). 해석 실패 시 re.error"""
    parts = []
    for p in pats:
        if mode == 'F':
            q = re.escape(p)
        else:
            q = bre_to_ere(p) if mode == 'G' else p
            for k, v in POSIX_CLASSES.items():
                q = q.replace(k, v)
        if '-w' in flags:
            q = r'(?<!\w)(?:%s)(?!\w)' % q
        if '-x' in flags:
            q = r'^(?:%s)$' % q
        parts.append('(?:%s)' % q)
    return re.compile('|'.join(parts), re.M | (re.I if '-i' in flags else 0))


def read_text(f):
    data = open(f, 'rb').read()
    for enc in ('utf-8', 'cp949'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode('latin-1')


def file_hits(pats, mode, flags, files):
    """검색어에 걸리는 파일 목록. 해석 실패·읽기 실패는 걸린 것으로 간주(fail-closed)"""
    try:
        rx = compile_pats(pats, mode, flags)
    except re.error:
        return list(files)
    hits = []
    for f in files:
        tick()
        try:
            if rx.search(read_text(f)):
                hits.append(f)
        except OSError:
            hits.append(f)
    return hits


# ---------------------------------------------------------------- 명령 분해
def strip_heredocs(cmd):
    """heredoc 본문 제거 (본문은 명령이 아니라 데이터 — 따옴표 불균형으로 해석이 깨지는 것 방지)"""
    out, lines, i = [], cmd.split('\n'), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delims = re.findall(r'(?<!<)<<(?!<)-?\s*[\'"]?([A-Za-z_][A-Za-z0-9_]*)[\'"]?', line)
        i += 1
        for d in delims:
            while i < len(lines) and lines[i].strip() != d:
                i += 1
            i += 1
    return '\n'.join(out)


def tokenize(cmd):
    # 줄 연결(\+줄바꿈)은 합치고, 줄바꿈은 명령 구분자로 (따옴표 안의 줄바꿈은 토큰 내용만 바뀌어 무해)
    cmd = strip_heredocs(cmd.replace('\r\n', '\n')).replace('\\\n', ' ').replace('\n', ' ; ').replace('`', ' ; ')
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ''
        return list(lex)
    except ValueError:  # 따옴표 불균형 등 → 단순 분리로 대체 검사
        toks = []
        for w in re.split(r'\s+', cmd):
            toks += [x for x in re.split(r'([;&|()<>]+)', w.strip('\'"')) if x]
        return toks


def segments(cmd):
    """(토큰목록, 앞 연산자) 목록. 리다이렉션 대상은 제외."""
    toks = tokenize(cmd)
    segs, cur, op, i = [], [], None, 0
    while i < len(toks):
        t = toks[i]
        if t and any(c in '<>' for c in t) and set(t) <= set('<>&|'):
            i += 2  # 리다이렉션 연산자 + 대상
            continue
        if t and set(t) <= set('();&|!{}'):
            if cur:
                segs.append((cur, op))
            cur, op = [], t
        else:
            cur.append(t)
        i += 1
    if cur:
        segs.append((cur, op))
    return segs


def unwrap(seg):
    i, xargs = 0, False
    while i < len(seg):
        t = seg[i]
        b = cmdname(t)
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', t):
            i += 1
        elif b in WRAPPERS:
            i += 1
            while i < len(seg) and seg[i].startswith('-'):
                i += 1 + (seg[i] in ('-u', '-g', '-n', '-o', '-e', '-i', '-C'))
        elif b == 'timeout':
            i += 1
            while i < len(seg) and seg[i].startswith('-'):
                i += 1 + (seg[i] in ('-s', '-k'))
            i += 1  # duration
        elif b == 'xargs':
            xargs = True
            i += 1
            while i < len(seg) and seg[i].startswith('-'):
                i += 1 + (seg[i] in ('-n', '-I', '-d', '-L', '-P', '-s', '-E', '-a'))
        else:
            break
    return seg[i:], xargs


# ---------------------------------------------------------------- 검색 명령
GREP_ARG = set('efmABCdD')
RG_ARG = set('efgtTmABCMjEr')
LONG_ARG = {'--regexp', '--file', '--include', '--exclude', '--exclude-dir', '--glob', '--iglob', '--type',
            '--type-not', '--max-count', '--context', '--after-context', '--before-context', '--label',
            '--max-depth', '--type-add', '--replace', '--encoding', '--sort', '--sortr', '--colors',
            '--max-columns', '--threads', '--ignore-file', '--pre', '--pre-glob', '--engine',
            '--binary-files', '--devices', '--directories', '--max-filesize', '--path-separator'}


def parse_search(name, args):
    rgish = name in ('rg', 'ag', 'ack')
    s = dict(pats=[], mode='P' if rgish else {'egrep': 'E', 'fgrep': 'F'}.get(name, 'G'), flags=[],
             rec=rgish or name == 'git-grep', paths=[], inc=[], exc=[], tinc=[], texc=[],
             listonly=False, files_mode=False, pfile=False)

    def opt(c, v):
        if c in ('e', 'regexp'):
            s['pats'].append(v)
        elif c in ('f', 'file'):
            s['pfile'] = True
        elif c in ('i', 'S', 'ignore-case', 'smart-case'):
            s['flags'].append('-i')
        elif c in ('w', 'word-regexp'):
            s['flags'].append('-w')
        elif c in ('x', 'line-regexp'):
            s['flags'].append('-x')
        elif c in ('F', 'fixed-strings'):
            s['mode'] = 'F'
        elif c in ('P', 'perl-regexp', 'pcre2'):
            s['mode'] = 'P'
        elif c in ('E', 'extended-regexp') and not rgish:
            s['mode'] = 'E'
        elif c in ('G', 'basic-regexp') and not rgish:
            s['mode'] = 'G'
        elif c in ('l', 'q', 'files-with-matches', 'files-without-match', 'quiet', 'silent'):
            s['listonly'] = True
        elif c == 'L' and not rgish:
            s['listonly'] = True
        elif c in ('r', 'R', 'recursive', 'dereference-recursive') and not rgish:
            s['rec'] = True
        elif c == 'files':
            s['files_mode'] = True
        elif c in ('include',):
            s['inc'].append(v)
        elif c in ('exclude',):
            s['exc'].append(v)
        elif c in ('g', 'glob', 'iglob'):
            (s['exc'] if v.startswith('!') else s['inc']).append(v.lstrip('!'))
        elif c in ('t', 'type'):
            s['tinc'].append(v)
        elif c in ('T', 'type-not'):
            s['texc'].append(v)

    argset = RG_ARG if rgish else GREP_ARG
    pos, i, endopt = [], 0, False
    while i < len(args):
        a = args[i]
        i += 1
        if endopt or a == '-' or not a.startswith('-'):
            pos.append(a)
        elif a == '--':
            endopt = True
        elif a.startswith('--'):
            k, eq, v = a.partition('=')
            if k in LONG_ARG and not eq:
                v = args[i] if i < len(args) else ''
                i += 1
            opt(k[2:], v)
        else:
            j = 1
            while j < len(a):
                c = a[j]
                if c in argset:
                    v = a[j + 1:]
                    if not v:
                        v = args[i] if i < len(args) else ''
                        i += 1
                    opt(c, v)
                    break
                opt(c, None)
                j += 1
    if s['files_mode']:
        s['paths'] = pos
    elif not s['pats'] and not s['pfile']:
        s['pats'], s['paths'] = pos[:1], pos[1:]
    else:
        s['paths'] = pos
    s['paths'] = [p for p in s['paths'] if p != '{}']
    return s


def search_candidates(s, cwd):
    roots = s['paths'] or ([cwd] if s['rec'] or s['files_mode'] else [])
    cands = []
    for r in roots:
        for p in expand(r, cwd):
            if os.path.isdir(p):
                if s['rec'] or s['files_mode']:
                    cands += [(f, p) for f in walk_sensitive(p)]
            elif os.path.isfile(p) and is_sensitive(p):
                cands.append((p, native(os.path.dirname(p))))
    return cands


def search_hits(s, cands):
    kept = []
    for f, root in cands:
        if s['inc'] and not any(gmatch(g, f, root) for g in s['inc']):
            continue
        if any(gmatch(g, f, root) for g in s['exc']):
            continue
        if s['tinc'] and not any(in_type(t, f) for t in s['tinc']):
            continue
        if any(type_excludes(t, f) for t in s['texc']):
            continue
        kept.append(f)
    if not kept or s['files_mode']:
        return kept
    if s['pfile'] or not s['pats']:
        return kept  # 검색어를 알 수 없음 → 전부 걸린 것으로 간주
    return file_hits(s['pats'], s['mode'], s['flags'], kept)


# ---------------------------------------------------------------- find
def parse_find(args):
    i, dirs = 0, []
    while i < len(args) and not (args[i].startswith('-') or args[i] in ('(', '!', ')')):
        dirs.append(args[i])
        i += 1
    rest, names, paths, regex, sub = args[i:], [], [], False, None
    j = 0
    while j < len(rest):
        a = rest[j]
        if a in ('-name', '-iname') and j + 1 < len(rest):
            names.append((rest[j + 1], a == '-iname'))
            j += 2
        elif a in ('-path', '-ipath', '-wholename', '-iwholename') and j + 1 < len(rest):
            paths.append(rest[j + 1])
            j += 2
        elif a in ('-regex', '-iregex'):
            regex = True
            j += 2
        elif a in ('-exec', '-execdir', '-ok', '-okdir') and j + 1 < len(rest):
            k, sub = j + 1, []
            while k < len(rest) and rest[k] not in (';', '+'):
                sub.append(rest[k])
                k += 1
            j = k + 1
        else:
            j += 1
    return dirs or ['.'], names, paths, regex, sub


def find_scope(dirs, names, paths, regex, cwd):
    out = []
    for d in dirs:
        for p in expand(d, cwd):
            files = walk_sensitive(p) if os.path.exists(p) else []
            for f in files:
                b = f.split('/')[-1]
                disp = native(os.path.join(d, os.path.relpath(f, p))) if os.path.isdir(p) else d
                if names and not regex and not any(
                        fnmatch.fnmatch(b.lower(), n.lower()) if ic else fnmatch.fnmatch(b, n) for n, ic in names):
                    continue
                if paths and not regex and not any(fnmatch.fnmatch(disp, pp) or fnmatch.fnmatch(f, pp) for pp in paths):
                    continue
                out.append(f)
    return out


# ---------------------------------------------------------------- 내용 출력 명령
def in_place(name, args):
    return name == 'sed' and any(a == '-i' or a.startswith('-i') or a.startswith('--in-place') for a in args)


def dumper_hits(name, args, cwd):
    toks = [a for a in args if not a.startswith('-')]
    if name in ('sed', 'awk', 'gawk', 'mawk', 'jq') and toks and not any(
            a in ('-e', '-f') or a.startswith('--expression') or a.startswith('--file') for a in args):
        toks = toks[1:]  # 첫 위치 인자는 스크립트/필터
    recursive = name == 'diff' and any(re.match(r'^-[A-Za-z]*r', a) or a == '--recursive' for a in args)
    hits = []
    for t in toks:
        for p in expand(t, cwd):
            if os.path.isfile(p) and is_sensitive(p):
                hits.append(p)
            elif recursive and os.path.isdir(p):
                hits += walk_sensitive(p)
    return hits


def nested_ps(name, args, cwd):
    """bash 안에서 부른 powershell -Command / cmd /c → PowerShell 검사기로"""
    import scan_powershell
    inner = scan_powershell.inner_command(name, args)
    if inner is not None:
        scan_powershell.check(inner, cwd)


def check_tool(name, args, cwd, given):
    """given: xargs/find -exec로 전달되는 파일 목록(None이면 인자에서 계산). 반환: 다음 파이프로 넘길 범위."""
    if name in GREPS:
        s = parse_search(name, args)
        cands = [(f, native(os.path.dirname(f))) for f in given] if given is not None else search_candidates(s, cwd)
        hits = search_hits(s, cands)
        if hits and not s['listonly'] and not s['files_mode']:
            raise Deny(GUIDE)
        return hits
    if name in DUMPERS:
        if in_place(name, args):
            return None
        hits = list(given) if given is not None else dumper_hits(name, args, cwd)
        if hits:
            raise Deny(GUIDE)
        return None
    if name in SHELLS:
        if given:
            raise Deny(GUIDE)  # xargs sh -c / find -exec sh -c: 내용 판단 불가
        if '-c' in args and args.index('-c') + 1 < len(args):
            check(args[args.index('-c') + 1], cwd)  # bash -c "..." 안쪽도 검사
        return None
    if name in PS_SHELLS:
        if given:
            raise Deny(GUIDE)
        nested_ps(name, args, cwd)
    return None


def check(cmd, cwd):
    cwd = native(cwd)
    last = None
    for seg, op in segments(cmd):
        tick()
        seg, xargs = unwrap(seg)
        if not seg:
            continue
        name, args = cmdname(seg[0]), seg[1:]
        prev, last = (last if op == '|' else None), None
        if name == 'cd':
            if not args:
                cwd = native(os.path.expanduser('~'))
            else:
                d = expand(args[0], cwd)
                if d and os.path.isdir(d[0]):
                    cwd = d[0]
            continue
        if name == 'git' and args[:1] == ['grep']:
            name, args = 'git-grep', args[1:]
        if xargs:
            given = prev if prev is not None else walk_sensitive(cwd)
            check_tool(name, args, cwd, given)
            continue
        if name == 'find':
            dirs, names, paths, regex, sub = parse_find(args)
            scope = find_scope(dirs, names, paths, regex, cwd)
            if sub:
                sname = cmdname(sub[0])
                if sname == 'git' and sub[1:2] == ['grep']:
                    sname, sub = 'git-grep', sub[1:]
                r = check_tool(sname, sub[1:], cwd, scope)
                last = r if r is not None else scope
            else:
                last = scope
            continue
        last = check_tool(name, args, cwd, None)
