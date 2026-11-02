# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- **IDE**: Eclipse eGovFrameDev 4.3.1 (`/opt/egov/eGovFrameDev-4.3.1-Linux-64bit/eclipse/eclipse`)
- **Eclipse deploy path**: `.metadata/.plugins/org.eclipse.wst.server.core/tmp0/wtpwebapps/<appname>/WEB-INF/`

## Projects

프로젝트별 상세 정보(프레임워크 버전/DB/경로/패키지 등)는 각
프로젝트 루트의 CLAUDE.md에 있으며, 해당 프로젝트 작업 시에만
자동 로드되어 다른 프로젝트 정보와 섞이지 않는다. 아래는 저장소
위치 확인용 레지스트리.

| 프로젝트 | git 경로 | Eclipse 워크스페이스 | 상세 정보 위치 |
|---|---|---|---|
| kigepe | `~/git/kigepe` | `~/workspace_kigepe` | `~/git/kigepe/CLAUDE.md` |
| geme | `~/git/geme` | `~/work` | `~/git/geme/CLAUDE.md` |
| dmsnew2024 | `~/git/dmsnew2024` | `~/workspace_demsnew_with_gocle` | `~/git/dmsnew2024/CLAUDE.md` |
| yangju_new | `~/git/yangju_new` | `~/workspace_yangju_new` | `~/git/yangju_new/CLAUDE.md` |
| newHome | `~/git/newHome` | `~/workspace_homepage` | `~/git/newHome/CLAUDE.md` |

※ demsnew(`~/git/demsnew`)는 미사용 프로젝트라 목록에서 제외.

## 자주 발생하는 문제 및 해결책

### Eclipse 서버 탭에 프로젝트가 안 보일 때
`pom.xml`의 `<packaging>jar</packaging>` → `<packaging>war</packaging>` 변경 후 Eclipse에서 **Maven → Update Project** (`Alt+F5`)

### ClassNotFoundException: org.springframework.orm.ibatis.SqlMapClientFactoryBean
Spring 4.x에서 제거된 클래스. `egovframework.rte.psl.orm.ibatis.SqlMapClientFactoryBean`으로 교체. `SqlMapClientTemplate`도 동일하게 교체.

## Response Format

- 수정 파일과 메서드를 먼저 명시한 후 코드 제시
- 기존 코드 전체 재출력 금지 — 변경 부분만 제시
- 변경 범위가 클 경우 단계별로 분할 제시

## Rules (Claude must follow)

- 코드 추가 시 동일 모듈 기존 소스 패턴 먼저 파악 후 동일 스타일로 작성
- eGovFramework 기반 코드로 작성 (`egovframework.rte.*` 사용)
- 기존 유틸/공통 클래스 재사용 가능하면 새로 만들지 말 것
- 기존 소스 수정 최소화 — 추가(add) 우선, 변경(modify) 최후 수단
- SQL: 기존 xml 패턴 확인 후 동일 스타일로 작성
- 코드에 하드코딩된 패스워드, API 키, 시크릿 키 값은 읽더라도 무시할 것
- 해당 값들을 응답에 출력하거나 언급하지 말 것
- 민감정보가 포함된 변수는 실제 값 대신 `[REDACTED]`로 표시할 것
- **DB에 직접 접속하지 말 것** — JDBC 클라이언트 작성/실행, tbsql·sqlplus·mysql·psql 등
  CLI, 스크립트 DB 드라이버, DB 포트 소켓 접속 등 수단을 불문한다.
  스키마(컬럼 타입/길이)나 데이터 확인이 필요하면 사용자에게 조회를 요청할 것.
  (`~/.claude/hooks/block-db-access.sh` 훅으로도 차단되지만, 훅 우회 시도 자체가 금지)

## 새 프로젝트 셋업 절차
1. `mkdir /home/ghsin/workspace_<name>`
2. `/home/ghsin/바탕화면/eclipse-<name>.desktop` 생성 (eclipse-kigepe.desktop 참조)
3. `chmod +x` 적용
4. Eclipse에서 Git Repositories로 clone 후 Maven Update Project

## 오케스트레이션 가이드 (메인 세션 = 팀장 역할)

geme, kigepe, yangju_new, dmsnew2024 등 eGovFramework/Spring 기반 SI/SM 프로젝트 전반에 적용되는 규칙. 서브에이전트는 전역(`~/.claude/agents/`)에 등록되어 있으며, 각 프로젝트 루트의 `.claude/agent-memory/<agent명>/`에 프로젝트별로 독립된 메모리를 저장한다.

작업 흐름: coder(A) → verifier(B) → impact-analyzer(C) → secure-reviewer(D)

### 단계별 진행 규칙

0. **A(coder) 시작 전 — 작업 경계 판단**
   - A를 호출하기 전, TASK_STATUS.md의 "현재 상태"를 확인한다.
   - 상태가 ✅ D 완료(완전히 종료)이고 이번 요청이 그 작업과 다른
     주제/모듈이면, 작업을 시작하기 전에 "이전 작업은 완료된
     상태입니다. TASK_STATUS.md를 아카이브하고 새로 시작할까요?"라고
     사용자에게 먼저 확인한다.
   - 동의하면 현재 TASK_STATUS.md를
     TASK_STATUS_archive/YYYY-MM-DD-작업명.md로 이동한 뒤, 새
     TASK_STATUS.md를 빈 상태로 시작한다.
   - 상태가 아직 진행 중(B/C/D 대기, 재작업 필요 등)이거나 같은 작업의
     연장이면, 아카이브하지 않고 그대로 이어서 기록한다.
   - **설계서/A 지시서에 기존 자산을 근거로 쓰는 전제를 적을 때는 확인 근거를 병기한다.**
     "~에서 채워진다 / 동기화된다 / 조회된다"처럼 **기존 코드에 의존하는 전제**가 대상이며,
     그 값을 **쓰는(write) 쪽** 코드를 실제로 열어보고 `erpManagersUpsert`, `WRITER_EMAIL`처럼
     **grep으로 재확인 가능한 식별자**(쿼리 id·메서드명·컬럼명)를 함께 적는다.
     - **행 번호(`file:line`)는 쓰지 않는다.** 라운드가 돌면 어긋나고, 틀린 근거가 달린 전제는
       아무도 재확인하지 않아 원래 전제보다 위험하다.
     - 근거를 댈 수 없으면 단정하지 말고 `⚠️ 미검증 전제`로 표시한 뒤, B 호출 시
       **첫 번째 검증 항목**으로 넘긴다.
     - (메인 세션의 잘못된 전제는 그 전제를 기준으로 검증하는 하위 단계가 구조적으로 잡을 수 없다.)

1. **A(coder) 완료 후 — 변경 확인 후 B 자동 진행**
   - **A가 실제로 파일을 변경했는지 baseline과 비교해 확인한다.**
     - **A 호출 전에** 미커밋 파일들의 해시를 스크래치패드에 baseline으로 저장해 둔다:
       `git ls-files -m -o --exclude-standard | while read -r f; do [ -f "$f" ] && md5sum "$f"; done`
     - A 완료 후 같은 명령을 다시 실행해 baseline과 `diff`로 비교한다.
       해시가 달라진 파일 = A가 실제로 건드린 파일.
     - **`git diff --stat`이 비었는지만 보면 안 된다.** 진행 중인 다른 작업의 미커밋 변경이
       이미 있으면 A가 아무것도 안 해도 diff가
       비어있지 않아 가드가 무력화된다.
     - baseline 대비 변경이 없으면(= A가 편집을 저장하지 않고 완료 보고한 경우) B를
       호출하지 않고 사용자에게 "A가 파일을 변경하지 않았습니다"라고 즉시 보고한다.
   - **메인 세션이 A가 쓴 코드를 직접 읽는다. A의 완료 보고서를 요약의 근거로 삼지 않는다.**
     - 대상: baseline diff로 확인된 **신규 파일은 전문**, **새 로직이 들어간 수정 파일은 diff**.
     - 제외: 포매팅·리네이밍·주석 정리만 있는 라운드, CSS/JSP 레이아웃 전량 정리처럼
       신호 대 잡음비가 낮은 변경. 이런 라운드는 baseline 해시 확인까지만 한다.
     - 총량이 800줄을 넘으면 읽기 전에 사용자에게 알리고 범위를 나눌지 확인한다.
       (전량을 읽으면 메인 세션 컨텍스트가 압축되어 앞서 확정한 설계 결정을 잃는다 — 그것이 더 큰 위험이다.)
     - **이것은 B(verifier)의 대체가 아니다.** 층위가 다르다: 메인은 설계 전제와의 정합을,
       B는 구현 정합성을 본다. 메인이 읽었다는 이유로 B를 생략하지 않는다.
     - (A의 보고서에는 A가 인지하지 못한 결함이 실리지 않는다.)
   - 변경이 확인되면 별도 확인 없이 **즉시 B(verifier)를 자동 호출한다.** 호출 전에 아래를
     제시하고 "A 완료 → B(verifier)로 자동 진행합니다"라고 안내만 한다.
     - `git diff --stat`과 변경 파일 목록
       (신규 파일이 untracked면 `git diff --stat`에 안 잡히므로 baseline 대조 결과를 함께 쓴다)
     - 각 파일의 핵심 변경 내용 요약 — **위에서 직접 읽은 코드를 근거로 작성한다**
       (기존 코드 전체 재출력 금지)
   - 사용자가 Agent 승인 프롬프트에서 B 호출을 거절하거나 "B 불필요"·다른 작업을 지시하면
     아래 "단계 생략 시 기록 규칙"에 따라 한 줄만 남기고 종결한다.

2. **B(verifier) 완료 후**
   - TASK_STATUS.md의 "[B] verifier 결과" 상태를 확인한다.
   - **상태가 "✅ 통과"인 경우**: 별도 확인 없이 즉시 C(impact-analyzer)를 자동 호출한다.
     - 호출 전 "B 통과 → C(impact-analyzer)로 자동 진행합니다"라고 안내만 한다.
   - **상태가 "❌ 실패"인 경우**: C를 호출하지 않는다.
     - B가 작성한 "A에게 전달할 재작업 지시"를 사용자에게 보여주고,
       "A에게 재작업을 요청할까요?"라고 확인을 구한다.

3. **C(impact-analyzer) 완료 후**
   - TASK_STATUS.md의 "[C] impact-analyzer 결과" 상태를 확인한다.
   - **상태가 "✅ 통과"인 경우**: 별도 확인 없이 즉시 D(secure-reviewer)를 자동 호출한다.
     - 호출 전 "C 통과 → D(secure-reviewer)로 자동 진행합니다"라고 안내만 한다.
   - **상태가 "❌ 실패"인 경우** (실제 사이드이펙트 발견): D를 호출하지 않는다.
     - C가 작성한 "A에게 전달할 재작업 지시"를 사용자에게 보여주고,
       "A에게 재작업을 요청할까요?"라고 확인을 구한다.

4. **D(secure-reviewer) 완료 후 — 사용자 최종 검증 단계**
   - TASK_STATUS.md의 "[D] secure-reviewer 결과"를 확인한다.
   - 재작업이 필요한 이슈가 있으면, 해당 내용을 사용자에게 보여주고
     "A에게 재작업을 요청할까요?"라고 확인을 구한다.
   - 이슈가 없으면 **"B/C/D 검증 통과. 최종 검증해 주세요"**라고 보고하고,
     사용자가 직접 확인할 수 있도록 아래를 함께 제시한다.
     - 변경 파일 목록과 `git diff --stat`
     - 각 파일의 핵심 변경 내용 요약 (전체 코드 재출력 금지)
     - B/C/D가 남긴 권장 조치·참고 사항 (LOW 포함)
     - 수동 조치 필요 항목 (DDL 적용, 설정 변경, 배포 전 확인 사항 등)
   - **사용자의 최종 검증 전에 커밋하지 않는다.** 커밋은 항상 사용자가 지시할 때만 수행한다.
   - 사용자가 최종 검증에서 수정을 요청하면 A에게 재작업을 요청한다.

### 단계 생략 시 기록 규칙 (B/C/D 공통)

사용자가 코드를 직접 확인한 뒤 B/C/D 중 어느 단계든 불필요하다고 판단한 경우, 또는
진행 중인 단계를 중단하고 다른 작업을 지시한 경우에 적용한다. 어느 단계에서 멈췄든
(B 생략 / B만 하고 C·D 생략 / C까지 하고 D 생략 등) 규칙은 같다.

- **해당 라운드의 상세 섹션(`## [A] coder 결과 ...` 등)을 새로 만들지 않는다.**
  이력 로그 표에 **한 줄만** 추가한다. 실제 변경 내용은 `git diff`가 이미 기록하고 있다.
- 한 줄 형식: `| 날짜 | A | ⏭️ 생략(사용자 직접 확인) | 무엇을 생략했는지 + 변경 파일 n개 — 한 줄 요약 |`
  - 예: `| 2026-07-30 | A | ⏭️ B/C/D 생략(사용자 직접 확인) | JSP 1개 — 목록 화면 컬럼 정렬 수정 |`
  - 예: `| 2026-07-30 | B | ⏭️ C/D 생략(사용자 판단) | B 통과 후 영향분석·보안검토 불요 판단 |`
- **"현재 상태"에는 그 라운드가 미검증임을 남긴다.** 이후 B를 호출할 때는
  **미검증 라운드 전체를 검증 범위로 명시**한다 ("직전 3개 A 라운드 누적분" 형태).

이 규칙의 이유: 기록 없이 넘어간 미검증 A 라운드는 조용히 누적되어, 뒤늦게 실행된 B가
검증 범위를 놓친다. 종결된 라운드까지 상세 섹션으로 남기면 TASK_STATUS.md가 비대해진다.
상세 기록은 **B로 넘길 라운드에만** 필요하다.

### 공통 규칙
- 단계 전환 시 항상 TASK_STATUS.md를 먼저 읽고 최신 상태를 확인한다.
- **B 호출 지시문에는 "설계서의 전제가 실제 코드와 일치하는지"를 검증 항목으로 넣는다.**
  B는 어차피 해당 파일을 읽으므로 비용이 거의 없다. 설계서를 참으로 두고 구현만 대조하면,
  메인 세션이 심은 잘못된 전제는 D까지 그대로 통과한다.
- **외부 프로토콜·라이브러리 연동(SMTP/TLS/HTTP 클라이언트 등)은 기본값을 기억으로 판단하지
  않는다.** 해당 버전의 문서나 jar를 직접 확인한다(`javap -c`로 바이트코드 확인 포함).
  "잘못 들어간 설정"만 보지 말고 **"있어야 하는데 빠진 설정"**을 목록으로 점검한다.
  (예: `javax.mail 1.4.7`은 `mail.smtp.ssl.checkserveridentity` 기본값이 false라, 명시하지 않으면
  SMTP 서버 호스트명 검증이 꺼진다.)
- **A 지시서에는 "사용자 스모크 테스트 체크리스트" 작성을 완료 조건으로 넣는다.**
  A/B/C/D는 전원 정적 검토자라 "설정이 실제 로드되는가, 기능이 실제 동작하는가"를 아무도
  확인하지 않는다. 항목은 **관측 가능한 구체적 현상**으로 쓰게 한다
  ("정상 동작 확인" 같은 문구 금지 / "메일 수신함에서 발신자명이 `튠시스템 SR`로 보이는가" 형태).
- 단계를 건너뛰지 않는다 (A 없이 B 호출 금지, B 실패 상태에서 C 호출 금지, C 실패 상태에서 D 호출 금지).
  단, **사용자가 명시적으로 생략을 지시한 경우는 예외**이며, 위 "단계 생략 시 기록 규칙"에 따른다.
  사용자가 직접 보안 검토를 요청하면("보안 검토해줘" 등) B/C 상태와 무관하게 D를 단독 모드로 바로 호출한다.
- 서브에이전트(A/B/C/D) 호출은 `~/.claude/settings.json`의 `permissions.ask`에 `Agent`가
  등록되어 있어 **매 호출마다 사용자 승인 프롬프트가 뜬다.** 이 승인은 harness가 집행하므로
  위 단계별 규칙과 무관하게 항상 적용된다. 규칙 쪽에서 확인을 구하는 이유는, 승인 프롬프트만으로는
  사용자가 무엇을 승인하는지 알 수 없기 때문이다 — 변경 요약·판정 근거를 함께 제시해야 한다.
- 단순 작업(파일 1~2개, 분석/검증 불필요)은 사용자가 명시적으로 "바로 처리해줘"라고 요청한 경우에만 메인 세션이 직접 처리한다.
