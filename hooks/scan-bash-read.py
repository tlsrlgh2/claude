#!/usr/bin/env python3
# mask-secrets.sh 보조 검사기 (Bash 명령용)
# 폴더·와일드카드 대상 명령이 민감 설정 파일(properties / context.xml / context-datasource.xml / .env*)
# 의 "내용"을 출력할 수 있으면 차단 사유를 stdout에 출력한다. 아무것도 출력하지 않으면 통과.
#
# - 대상: grep/egrep/fgrep/zgrep/rg/ag/ack/git grep (재귀·와일드카드),
#         cat/head/tail/sed/awk 등 내용 출력 명령 (와일드카드), find -exec <읽기 명령>, ... | xargs <읽기 명령>
# - 검색 명령은 범위 안 민감 파일이 검색어에 실제로 걸릴 때만 차단 (Grep 도구 검사와 같은 기준)
#   파일명만 출력(-l/-L/-q, rg --files)은 허용, 개수(-c)는 차단
# - 판정 불가(정규식 오류, -f 패턴 파일, 시간 초과, 해석 오류)는 차단 (fail-closed)
# - 한계(의도적 우회까지는 막지 않음): python/perl 등 인터프리터 내부 읽기, 변수로 감춘 경로,
#   git diff/show/log -p 출력
import fnmatch
import glob
import json
import os
import re
import shlex
import subprocess
import sys
import time

T0 = time.monotonic()
BUDGET = 20  # 초. 바깥 훅 timeout(settings.json 30초) 전에 스스로 차단으로 끝낸다
PRUNE = {'.git', 'node_modules'}
GUIDE = ('민감 설정 파일(properties/context.xml/.env)의 내용이 출력될 수 있는 명령입니다. '
         '검색은 --include(rg는 -g)로 대상 확장자를 좁히거나(예: --include="*.java") -l(파일명만)로 바꾸고, '
         '민감 파일 내용은 Read 도구로 보세요 — 마스킹된 내용이 제공됩니다.')

GREPS = {'grep', 'egrep', 'fgrep', 'zgrep', 'rg', 'ag', 'ack', 'git-grep'}
DUMPERS = {'cat', 'tac', 'head', 'tail', 'less', 'more', 'nl', 'od', 'xxd', 'hexdump', 'strings',
           'sed', 'awk', 'gawk', 'mawk', 'cut', 'sort', 'uniq', 'paste', 'diff', 'cmp', 'base64',
           'column', 'fold', 'fmt', 'jq', 'iconv', 'vi', 'vim', 'view', 'nano', 'zcat', 'bat', 'batcat'}
SHELLS = {'sh', 'bash', 'zsh', 'dash'}
WRAPPERS = {'sudo', 'env', 'command', 'builtin', 'time', 'nice', 'nohup', 'stdbuf', 'exec'}
# ripgrep 타입 중 민감 파일 패턴을 포함하지 않는 것 (rg --type-list로 확인. java는 properties, xml은 context.xml 포함)
SAFE_RG_TYPES = {'js', 'ts', 'css', 'html', 'sql', 'py', 'sh', 'md'}


class Deny(Exception):
    pass


def tick():
    if time.monotonic() - T0 > BUDGET:
        raise Deny('민감 파일 검사 시간 초과. ' + GUIDE)


def is_sensitive(p):
    b = os.path.basename(p)
    return b.endswith('.properties') or b in ('context.xml', 'context-datasource.xml') or b.startswith('.env')


def walk_sensitive(root):
    if os.path.isfile(root):
        return [root] if is_sensitive(root) else []
    out = []
    for d, dirs, files in os.walk(root):
        tick()
        dirs[:] = [x for x in dirs if x not in PRUNE]
        out += [os.path.join(d, f) for f in files if is_sensitive(f)]
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
    for v in braces(os.path.expanduser(tok)):
        p = v if os.path.isabs(v) else os.path.join(cwd, v)
        if any(c in v for c in '*?['):
            res += glob.glob(p, recursive=True)  # bash보다 넓게(** 재귀) 펼쳐 보수적으로 판정
        else:
            res.append(p)
    return res


def gmatch(pat, path, root):
    rel = os.path.relpath(path, root) if root else path
    b = os.path.basename(path)
    for p in braces(pat):
        q = p[3:] if p.startswith('**/') else p
        if any(fnmatch.fnmatch(x, y) for x in (b, rel) for y in (p, q)):
            return True
    return False


def in_type(t, f):
    b = os.path.basename(f)
    if t in SAFE_RG_TYPES:
        return False
    if t == 'java':
        return b.endswith('.properties')
    if t == 'xml':
        return b.endswith('.xml')
    return True  # 알 수 없는 type → 포함으로 간주(보수적)


def type_excludes(t, f):
    b = os.path.basename(f)
    if t == 'java':
        return b.endswith('.properties')
    if t == 'xml':
        return b.endswith('.xml')
    return False


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
    cmd = strip_heredocs(cmd).replace('\\\n', ' ').replace('\n', ' ; ').replace('`', ' ; ')
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
        b = os.path.basename(t)
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
                cands.append((p, os.path.dirname(p)))
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
    hits = []
    for f in kept:
        tick()
        cmd = ['grep', '-q', '-' + s['mode']] + s['flags']
        for p in s['pats']:
            cmd += ['-e', p]
        rc = subprocess.run(cmd + ['--', f], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=5).returncode
        if rc != 1:  # 0=매칭, 2=정규식 해석 실패 → 걸린 것으로
            hits.append(f)
    return hits


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
                b = os.path.basename(f)
                disp = os.path.join(d, os.path.relpath(f, p)) if os.path.isdir(p) else d
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


def check_tool(name, args, cwd, given):
    """given: xargs/find -exec로 전달되는 파일 목록(None이면 인자에서 계산). 반환: 다음 파이프로 넘길 범위."""
    if name in GREPS:
        s = parse_search(name, args)
        cands = [(f, os.path.dirname(f)) for f in given] if given is not None else search_candidates(s, cwd)
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
    if name in SHELLS and given:
        raise Deny(GUIDE)  # xargs sh -c / find -exec sh -c: 내용 판단 불가
    return None


def check(cmd, cwd):
    last = None
    for seg, op in segments(cmd):
        tick()
        seg, xargs = unwrap(seg)
        if not seg:
            continue
        name, args = os.path.basename(seg[0]), seg[1:]
        prev, last = (last if op == '|' else None), None
        if name == 'cd':
            if not args:
                cwd = os.path.expanduser('~')
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
                sname = os.path.basename(sub[0])
                if sname == 'git' and sub[1:2] == ['grep']:
                    sname, sub = 'git-grep', sub[1:]
                r = check_tool(sname, sub[1:], cwd, scope)
                last = r if r is not None else scope
            else:
                last = scope
            continue
        last = check_tool(name, args, cwd, None)


def main():
    data = json.load(sys.stdin)
    cmd = (data.get('tool_input') or {}).get('command') or ''
    cwd = data.get('cwd') or os.getcwd()
    try:
        check(cmd, cwd)
    except Deny as e:
        print(str(e))
    except Exception as e:  # 해석 실패 → 차단 (fail-closed)
        print('민감 파일 검사 중 명령 해석 실패(%s). 명령을 단순하게 나눠 다시 시도하세요. %s' % (type(e).__name__, GUIDE))


if __name__ == '__main__':
    main()
