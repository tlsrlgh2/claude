#!/usr/bin/env python3
# [Windows용 복사본] Linux용 hooks/mask-xml.py와 규칙 동일. mask_xml_text() 함수로 분리만 함.
# ※ 규칙을 바꿀 때는 Linux용 hooks/mask-xml.py도 같이 고칠 것.
# mask-secrets.sh 보조: sed 마스킹 결과(stdin)에 XML 형태 비밀값 마스킹을 추가 적용해 stdout으로 출력
# sed 규칙은 key=value 형태만 처리하므로 아래 형태를 보완한다 (키 이름은 대소문자 무시):
#   <property name="password" value="..."/>        같은 줄의 value 속성 / 텍스트 내용
#   <entry key="db.password" value="..."/>         name/key/id 속성 값에 키워드 포함
#   <property name="password">\n<value>...</value>  다음 줄(들)의 <value> 내용
#   <prop key="...password">...</prop>             같은 줄 텍스트 내용
#   <password>...</password>, <jdbc.pwd>...</...>   키워드를 포함한 요소의 텍스트
#   dbPassword="..." / PASSWORD='...'               키워드를 포함한 속성 이름의 값
import re
import sys

KEY = r'(?:password|passwd|pwd|secret|credential)'
NAMING = re.compile(r'\b(?:name|key|id)\s*=\s*(["\'])[^"\']*' + KEY + r'[^"\']*\1', re.I)
VALUE_ATTR = re.compile(r'(\bvalue\s*=\s*)(["\'])(.*?)\2', re.I)
TEXT = re.compile(r'>([^<]+)<')
VALUE_OPEN = re.compile(r'(<value\b[^>]*>)(.*)$', re.I)
VALUE_FULL = re.compile(r'(<value\b[^>]*>)([^<]*)(</value>)', re.I)
ELEM = re.compile(r'(<([\w.:-]*' + KEY + r'[\w.:-]*)\b[^>]*>)([^<]*)(</\2>)', re.I)
ATTR = re.compile(r'(\b[\w.:-]*' + KEY + r'[\w.:-]*\s*=\s*)(["\'])(.*?)\2', re.I)
PENDING_END = re.compile(r'</(?:property|entry|constructor-arg|prop)>|/>', re.I)

M = '[MASKED]'


def mask_line(line):
    line = ELEM.sub(lambda m: m.group(1) + M + m.group(4), line)
    line = ATTR.sub(lambda m: m.group(1) + m.group(2) + M + m.group(2), line)
    return line


def mask_xml_text(text):
    """[Windows판] 문자열을 받아 XML 형태 비밀값을 가린 문자열을 반환 (mask_secrets.py에서 import)"""
    pending = False   # 키워드 이름을 가진 요소의 값이 다음 줄에 올 수 있음
    in_value = False  # 여러 줄에 걸친 <value> 내용 마스킹 중
    out = []
    for line in text.split('\n'):
        if in_value:
            if '</value>' in line.lower():
                idx = line.lower().index('</value>')
                line = M + line[idx:]
                in_value = False
            else:
                line = M
            out.append(line)
            continue
        line = mask_line(line)
        if NAMING.search(line):
            line = VALUE_ATTR.sub(lambda m: m.group(1) + m.group(2) + M + m.group(2), line)
            line = TEXT.sub(lambda m: '>' + (M if m.group(1).strip() else m.group(1)) + '<', line)
            if not VALUE_ATTR.search(line) and not PENDING_END.search(line):
                pending = True
            out.append(line)
            continue
        if pending:
            if VALUE_FULL.search(line):
                line = VALUE_FULL.sub(lambda m: m.group(1) + M + m.group(3), line)
                pending = False
            elif VALUE_OPEN.search(line):
                line = VALUE_OPEN.sub(lambda m: m.group(1) + M, line)
                pending, in_value = False, True
            elif PENDING_END.search(line):
                pending = False
        out.append(line)
    return '\n'.join(out)


def main():
    # EUC-KR 등 비 UTF-8 파일도 바이트 그대로 보존 (디코딩 실패로 차단되지 않게)
    text = sys.stdin.buffer.read().decode('utf-8', 'surrogateescape')
    sys.stdout.buffer.write(mask_xml_text(text).encode('utf-8', 'surrogateescape'))


if __name__ == '__main__':
    main()
