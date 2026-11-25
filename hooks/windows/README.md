# Claude Code 민감정보 유출 방지 훅 — Windows용

민감 설정 파일(`*.properties`, `context.xml`, `context-datasource.xml`, `.env*`)의 비밀번호·IP가
Claude의 컨텍스트(= 외부 API 전송)로 들어가는 것을 막는 PreToolUse 훅입니다.
Linux용(`hooks/mask-secrets.sh`)과 같은 규칙을 **Python만으로** 구현했습니다 (jq·sed·grep 불필요).

| 도구 | 동작 |
|---|---|
| Read | 원본 대신 비밀번호·IP를 가린 내용을 보여줌 (properties + XML 형태) |
| Bash (Git Bash) | 민감 파일명이 들어간 명령 차단 + `grep -r`, `rg`, `cat *`, `find -exec`, `xargs` 등이 민감 파일 내용을 출력할 수 있으면 차단 |
| PowerShell | 민감 파일명이 들어간 명령 차단 + `Get-Content`, `Select-String`, `gci -r \| sls`, `findstr /s`, `cmd /c`, `powershell -Command` 등 검사 |
| Grep | 민감 파일 직접 검색 차단 + 폴더 검색(content/count)에서 민감 파일이 검색어에 걸리면 차단 |

- 일반 코드 검색은 그대로 동작합니다 (민감 파일이 검색어에 **실제로 걸릴 때만** 차단).
- 파일명만 출력(`grep -l`, `findstr /m`, `sls -Quiet`)과 범위를 좁힌 검색(`--include="*.java"`, `-Filter *.java`)은 허용.
- 판정할 수 없으면 차단 (정규식 오류, 시간 초과, 훅 내부 오류 → exit 2).

## 필요 환경

- Python 3.8 이상 — **Git Bash에서 `python --version`이 동작해야 합니다**
  (Microsoft Store 바로가기만 있는 경우 실제 Python을 설치)
- Git for Windows (Git Bash)
- Claude Code — 2.1.295 이상 권장 (아래 "업데이트 후 추가 설정" 참고)

## 설치

PowerShell 기준입니다.

1. **zip 압축 풀기** — zip은 아무 위치에 저장해도 됩니다 (예: `다운로드`)
   ```powershell
   cd $env:USERPROFILE\Downloads
   Expand-Archive claude-secret-guard-windows.zip -DestinationPath .
   cd claude-secret-guard-windows          # 이후 명령은 이 폴더에서 실행
   ```
2. **훅 폴더 복사** — `%USERPROFILE%\.claude\hooks\windows\`에 넣습니다
   ```powershell
   New-Item -ItemType Directory -Force $env:USERPROFILE\.claude\hooks | Out-Null
   Copy-Item -Recurse -Force .\hooks\windows $env:USERPROFILE\.claude\hooks\
   ```
   복사 후 위치:
   ```
   %USERPROFILE%\.claude\hooks\windows\
   ├── mask_secrets.py      ← settings.json에 등록하는 훅 (진입점)
   ├── scan_bash_read.py    ← Bash 명령 검사
   ├── scan_powershell.py   ← PowerShell/cmd 명령 검사
   ├── mask_xml.py          ← XML 마스킹
   └── tests\               ← 확인용 테스트 (가짜 값만 포함)
   ```
   ※ 네 파일은 반드시 같은 폴더에 있어야 합니다.
3. **자동 테스트** — 등록 전에 먼저 확인
   ```powershell
   python $env:USERPROFILE\.claude\hooks\windows\tests\run_all.py
   ```
   마지막 줄이 `==> 전체 통과`면 정상. 실패하면 `-v`를 붙여 다시 실행하고 출력 전체를 공유해 주세요.
4. **훅 등록** — `settings-hooks-windows.json`의 내용을 `%USERPROFILE%\.claude\settings.json`에 추가
   - `<사용자>`를 본인 계정 폴더명으로 변경 (`echo $env:USERNAME`으로 확인). 경로는 **슬래시(/)** 그대로 둡니다
   - `settings.json`이 없으면 `settings-hooks-windows.json`을 그대로 복사해 만들면 됩니다
   - 이미 `hooks` 설정이 있으면 덮어쓰지 말고 `hooks.PreToolUse` 배열에 항목만 추가
5. **Claude Code 재시작**

설치가 끝나면 압축을 푼 폴더는 지워도 됩니다.

## 실제 동작 확인 (Claude Code에서)

`%USERPROFILE%\.claude\hooks\windows\tests` 폴더(가짜 값만 있음)를 대상으로 Claude에게 요청하고 화면을 확인합니다.

| Claude에게 요청 | 정상이면 보이는 것 |
|---|---|
| "tests 폴더의 globals.properties 읽어줘" | `Password=[MASKED]`, IP는 `[MASKED_IP]` |
| "tests\xml\context-datasource.xml 읽어줘" | `value="[MASKED]"`. `FAKE_SECRET`이 하나도 안 보임 |
| "tests 폴더 전체에서 Password 검색해줘" | 차단 메시지("민감 설정 파일 ... 내용이 출력될 수 있는 명령입니다") |
| "PowerShell로 tests 폴더에서 Password 검색해줘" | 차단 메시지 |
| "tests 폴더에서 .java 파일만 Password 검색해줘" | `A.java` 한 줄만 결과로 나옴 |

`FAKE_`로 시작하는 값이 화면에 보이면 그 항목은 **실패**입니다.

⚠️ **실제 프로젝트의 민감 파일로는 테스트하지 마세요.** 훅에 구멍이 있으면 진짜 값이 출력됩니다.

### 진단 로그 (처음 한 번)

Windows에서 훅이 받는 경로 형식을 확인하기 위한 것입니다.
```powershell
$env:MASK_HOOK_DEBUG = "1"
claude
```
위 확인 요청을 2~3개 해 본 뒤 Claude Code를 종료하고,
`%USERPROFILE%\.claude\hooks\windows\debug-input.log`를 공유해 주세요. (도구 이름·경로·명령만 기록됨)
확인 후에는 `Remove-Item Env:MASK_HOOK_DEBUG`로 끄고 로그 파일은 지워도 됩니다.

## 업데이트 후 추가 설정 (권장)

현재 Claude Code 버전에서는 **훅 자체가 실행되지 못하면(python 경로 오류 등) 차단되지 않고 그대로 진행됩니다.**
`claude update`로 2.1.295 이상이 되면 settings.json의 훅 항목에 아래 한 줄을 추가하세요.
실행 실패·시간 초과도 차단으로 처리됩니다.
```json
"onFailure": "block",
```
(2.1.295 미만에서는 넣지 마세요 — 모르는 필드로 설정이 무시될 수 있습니다.)

## 알려진 한계

- JDBC URL의 호스트명(IP가 아닌 이름)은 가리지 않음
- 마스킹 키워드: password / passwd / pwd / secret / credential (token, apikey 등은 대상 아님)
- 민감 파일을 수정한 상태에서 `git diff` 출력에는 값이 보일 수 있음
- 변수에 담은 경로(`$p = ...; gc $p`), .NET 메서드 직접 호출, python 스크립트 내부 읽기 등 의도적 우회는 막지 않음

## 유지보수

Linux용(`hooks/mask-secrets.sh`, `scan-bash-read.py`, `mask-xml.py`)과 규칙이 같도록 유지해야 합니다.
한쪽 규칙을 바꾸면 다른 쪽도 같이 고치고 양쪽 테스트를 모두 돌리세요.
