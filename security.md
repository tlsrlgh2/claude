# 소스코드 취약점 진단 기준 (KISA 소프트웨어 보안약점)
# 출처: 한국인터넷진흥원(KISA) 소프트웨어 보안약점 진단가이드 (2021)
#       행정기관 및 공공기관 정보시스템 구축·운영 지침 [별표3] 49개 보안약점 기준
# 원문: https://www.kisa.or.kr/2060204/form?postSeq=9
# 적용: 공공기관 SI/SM Java(Spring MVC, eGovFrame, MyBatis, JSP) 환경 기준

---

## 1. 입력데이터 검증 및 표현 (Input Validation)

> 프로그램 입력값에 대한 적절한 검증 없이 사용할 경우 발생하는 보안약점

### 1-1. SQL 인젝션 (SQL Injection)
- **위협**: 외부 입력값이 SQL 쿼리에 그대로 삽입되어 DB 조작
- **진단**: `Statement` 직접 사용, 동적 쿼리 문자열 연결 여부
- **조치**:
  - MyBatis: `#{}` 사용 (`${}` 사용 금지 — 단, ORDER BY 등 불가피한 경우 화이트리스트 검증 후 사용)
  - `PreparedStatement` 파라미터 바인딩 사용
  - 입력값에 특수문자(`'`, `"`, `--`, `;`) 필터링
- **JSP/eGov 주의**: `${}` EL 표현식으로 쿼리 조립 패턴 체크

### 1-2. 경로 조작 및 자원 삽입 (Path Traversal)
- **위협**: 외부 입력으로 서버 파일 경로 조작 (`../` 등)
- **진단**: 파일명/경로에 사용자 입력 직접 사용 여부
- **조치**:
  - 파일명에서 `..`, `/`, `\`, `:` 등 제거 또는 거부
  - 허용된 디렉토리 외 접근 차단 (Canonical Path 비교)
  - `eGovFileMngUtil` 사용 시 업로드 경로 고정 처리

### 1-3. 크로스사이트 스크립팅, XSS (Cross-Site Scripting)
- **위협**: 사용자 입력이 HTML에 그대로 출력되어 스크립트 실행
- **진단**: JSP에서 `<%= %>`, `${param.xxx}` 미인코딩 출력
- **조치**:
  - 출력 시 HTML 엔티티 인코딩: `<c:out value="${...}"/>` 사용
  - JSTL `fn:escapeXml()` 적용
  - Lucy XSS Filter 또는 NAVER AntiXSS 적용
  - eGov: `XssFilter` 서블릿 필터 설정 확인

### 1-4. 운영체제 명령어 삽입 (OS Command Injection)
- **위협**: 외부 입력이 OS 명령어에 포함되어 시스템 명령 실행
- **진단**: `Runtime.exec()`, `ProcessBuilder` 사용 시 입력값 포함 여부
- **조치**:
  - 가능한 OS 명령어 실행 자체를 회피
  - 불가피한 경우 입력값 화이트리스트 검증

### 1-5. 위험한 형식 파일 업로드 (Unrestricted File Upload)
- **위협**: 실행 가능한 파일(jsp, php, exe 등) 업로드 후 실행
- **진단**: 파일 업로드 시 확장자/MIME 타입 검증 여부
- **조치**:
  - 허용 확장자 화이트리스트 검증 (블랙리스트만은 부족)
  - MIME 타입 + 파일 시그니처(Magic Byte) 이중 검증
  - 업로드 파일 저장 경로를 웹 루트 외부로 설정
  - 파일명 서버측 랜덤 재생성 (원본명 그대로 저장 금지)

### 1-6. 신뢰되지 않는 URL 주소로 자동 접속 연결 (Open Redirect)
- **위협**: 외부 입력 URL로 무조건 리다이렉트하여 피싱에 악용
- **진단**: `response.sendRedirect(request.getParameter("url"))` 패턴
- **조치**:
  - 리다이렉트 URL을 화이트리스트로 제한
  - 도메인 검증 로직 적용

### 1-7. 크로스사이트 요청 위조, CSRF (Cross-Site Request Forgery)
- **위협**: 피해자 권한으로 의도치 않은 요청 실행
- **진단**: 상태 변경 요청에 CSRF 토큰 미사용 여부
- **조치**:
  - CSRF 토큰 생성 및 검증 (세션 기반)
  - Spring Security CSRF 설정 활성화
  - eGov: `EgovSessionCsrfRequestMatcher` 또는 커스텀 필터 적용

### 1-8. HTTP 응답 분할 (HTTP Response Splitting)
- **위협**: 헤더에 CRLF(`\r\n`) 포함 시 응답 위조
- **진단**: 사용자 입력을 HTTP 헤더에 직접 설정하는 코드
- **조치**:
  - 헤더 설정 전 입력값에서 `\r`, `\n` 제거

### 1-9. 정수 오버플로우 (Integer Overflow)
- **위협**: 정수 연산 결과가 범위를 초과하여 예상치 못한 동작
- **조치**: `Math.addExact()` 사용 또는 범위 사전 검증

### 1-10. 포맷 스트링 삽입 (Format String Injection)
- **위협**: 외부 입력이 `printf` 계열 포맷 문자열로 사용되어 메모리 노출
- **조치**: 포맷 문자열에 외부 입력 직접 사용 금지

---

## 2. 보안 기능 (Security Features)

> 인증, 접근제어, 암호화, 권한 관리 관련 보안약점

### 2-1. 적절한 인증 없는 중요 기능 허용
- **위협**: 인증 우회로 관리자 기능 또는 중요 API 접근
- **진단**: 인증 체크 없이 중요 URL 접근 가능 여부
- **조치**:
  - Spring Security 또는 인터셉터로 모든 중요 경로 인증 강제
  - eGov: `EgovLoginSessionInterceptor` 설정 확인

### 2-2. 부적절한 인가 (Improper Authorization)
- **위협**: 다른 사용자 데이터에 권한 없이 접근
- **진단**: `userId`를 파라미터로 받아 세션 검증 없이 조회하는 패턴
- **조치**:
  - 세션의 사용자 정보로 데이터 소유권 검증
  - `esntlId` 기반 본인 데이터 여부 확인

### 2-3. 중요한 자원에 대한 잘못된 권한 설정
- **위협**: 설정 파일, 업로드 디렉토리 등 권한 과다 부여
- **조치**:
  - 업로드 폴더 실행 권한 제거
  - 설정 파일(`.properties`, `context.xml`) 읽기 전용 설정

### 2-4. 취약한 암호화 알고리즘 사용
- **위협**: DES, MD5, SHA-1 등 취약 알고리즘 사용으로 데이터 노출
- **진단**: `DESede`, `MD5`, `SHA1` 사용 코드
- **조치**:
  - 암호화: AES-256 (CBC 또는 GCM 모드)
  - 해시: SHA-256 이상
  - 패스워드 해시: BCrypt, PBKDF2 사용
  - 현재 `AES/ECB/NoPadding` 사용 중인 경우 CBC 또는 GCM으로 전환 검토

### 2-5. 하드코드된 암호화 키 (Hardcoded Cryptographic Key)
- **위협**: 소스코드에 키/패스워드 직접 삽입 시 유출 위험
- **진단**: `.java`, `.jsp`, `.xml` 파일 내 패스워드/키 문자열 리터럴
- **조치**:
  - 키를 외부 설정 파일 또는 환경변수로 분리
  - `.properties` → 암호화하여 저장

### 2-6. 충분하지 않은 키 길이 사용
- **조치**: RSA 2048bit 이상, AES 128bit 이상 사용

### 2-7. 적절하지 않은 난수 사용 (Insecure Randomness)
- **위협**: `Math.random()`, `java.util.Random` 사용 시 예측 가능
- **조치**: 보안 목적 난수는 `SecureRandom` 사용

### 2-8. 취약한 패스워드 허용 (Weak Password Policy)
- **조치**: 최소 8자, 대소문자+숫자+특수문자 조합 강제

### 2-9. 사용자 중요정보 평문 저장/전송
- **위협**: 주민번호, 카드번호, 패스워드 평문 저장
- **조치**:
  - DB 저장 시 단방향 해시(패스워드) 또는 AES 암호화(복호화 필요 정보)
  - 전송 시 HTTPS 강제

### 2-10. 세션 고정 (Session Fixation)
- **위협**: 로그인 후 세션ID가 변경되지 않아 하이재킹 가능
- **조치**: 로그인 성공 후 `session.invalidate()` + 새 세션 생성

---

## 3. 시간 및 상태 (Time and State)

> 병렬 처리나 공유 자원 관련 보안약점

### 3-1. 경쟁 조건 (Race Condition) - TOCTOU
- **위협**: 검사 시점과 사용 시점 사이 상태 변경으로 보안 우회
- **진단**: 파일 존재 확인 후 열기 패턴, 잔액 확인 후 차감 패턴
- **조치**: DB 트랜잭션 + `SELECT FOR UPDATE` 또는 동기화 블록 사용

### 3-2. 종료되지 않는 반복문 또는 재귀함수
- **조치**: 반복 횟수/깊이 제한, `timeout` 설정

---

## 4. 에러 처리 (Error Handling)

> 에러를 부적절하게 처리하여 정보 노출

### 4-1. 오류 메시지를 통한 정보 노출
- **위협**: 스택트레이스, DB 오류, 서버 경로가 사용자에게 노출
- **진단**: `e.printStackTrace()`, 예외를 JSP에 직접 출력하는 패턴
- **조치**:
  - 사용자에게는 일반 오류 메시지만 표시
  - 상세 오류는 서버 로그에만 기록 (log4j/slf4j 사용)
  - `web.xml`에 `<error-page>` 설정으로 커스텀 오류 페이지 적용

### 4-2. 적절하지 않은 예외 처리
- **위협**: 예외 무시(`catch {}` 빈 블록)로 비정상 흐름 은폐
- **조치**: 모든 예외는 최소한 로깅 처리, 빈 catch 블록 금지

---

## 5. 코드 품질 (Code Quality)

> 코드 구현 오류로 인한 보안약점

### 5-1. 널 포인터 역참조 (Null Pointer Dereference)
- **진단**: 리턴값 null 체크 없이 바로 메서드 호출
- **조치**: null 체크 후 사용, Optional 활용

### 5-2. 부적절한 자원 해제 (Resource Leak)
- **위협**: Connection, Stream, Statement 미해제로 자원 고갈
- **진단**: `finally` 블록 없이 DB 연결/파일 사용
- **조치**: try-with-resources 사용, `finally`에서 `close()` 보장
- **SpotBugs**: `HttpsURLConnection` 리소스 누수 패턴 주의

### 5-3. 사용되지 않는 변수 (Dead Code)
- **조치**: 불필요한 코드/변수 제거

---

## 6. 캡슐화 (Encapsulation)

> 중요 데이터/기능이 적절히 보호되지 않는 보안약점

### 6-1. 잘못된 세션에 의한 데이터 정보 노출
- **위협**: 세션에 저장된 타 사용자 정보 접근
- **조치**: 세션 분리, 사용자별 세션 독립성 보장

### 6-2. 제거되지 않고 남은 디버그 코드
- **진단**: 운영 배포 코드에 `System.out.println`, 테스트용 계정/URL 포함
- **조치**: 운영 빌드 시 디버그 코드 제거, 로그 레벨 설정

### 6-3. 민감한 데이터를 가진 클래스의 직렬화 허용
- **위협**: 직렬화 가능 객체에 패스워드 등 민감 정보 포함
- **조치**: 민감 필드에 `transient` 선언

---

## 7. API 오용 (API Misuse)

### 7-1. DNS Lookup에 의존한 보안 결정
- **조치**: IP 기반 검증 대신 인증서/토큰 방식 사용

### 7-2. 취약한 API 사용
- **진단**: Deprecated된 암호화 API, 안전하지 않은 HTTP 클라이언트
- **조치**: 최신 보안 API 사용, TLS 1.2 이상 강제

---

## eGovFrame / Spring MVC / JSP 환경 특화 체크리스트

### MyBatis XML
- [ ] `${}` → `#{}` 로 교체 (동적 ORDER BY/테이블명 제외)
- [ ] 동적 쿼리 조립 시 화이트리스트 검증 코드 존재 여부

### JSP
- [ ] `<%= %>`, `${param.xxx}` 미인코딩 출력 → `<c:out>` 또는 `fn:escapeXml()` 교체
- [ ] 파일 업로드: 확장자 화이트리스트 + 저장경로 웹루트 외부
- [ ] `target="_blank"` 링크에 `rel="noopener noreferrer"` 추가

### Controller / Service
- [ ] 모든 `@RequestParam`/`@PathVariable` 입력값 서버측 검증
- [ ] 세션에서 사용자 ID 취득 (파라미터 `userId` 직접 사용 금지)
- [ ] 파일 다운로드: 경로 조작 방지, 허용 경로 검증

### 설정 파일
- [ ] DB 패스워드 암호화 저장 여부 (`jasypt` 등 적용)
- [ ] `web.xml` 커스텀 에러 페이지 설정
- [ ] HTTPS 강제 리다이렉트 설정
- [ ] 디렉토리 리스팅 비활성화 (`DefaultServlet listings=false`)

### 세션/인증
- [ ] 로그인 성공 후 세션 재생성
- [ ] 세션 타임아웃 적절히 설정 (30분 이내 권장)
- [ ] 로그아웃 시 세션 완전 무효화 (`session.invalidate()`)

---

## 주요 취약점 우선순위 (공공SI 기준)
| 우선순위 | 항목 | 빈도 |
|--------|------|------|
| 🔴 HIGH | SQL 인젝션, XSS, 파일 업로드 | 매우 높음 |
| 🔴 HIGH | 취약한 암호화 (AES/ECB, MD5) | 높음 |
| 🟠 MED  | CSRF, 인증/인가 부재 | 높음 |
| 🟠 MED  | 오류 메시지 정보 노출 | 높음 |
| 🟡 LOW  | 자원 해제, 하드코드 키 | 중간 |

---

## 참고 도구
- **정적분석**: SpotBugs + FindSecBugs 플러그인 (Eclipse/Jenkins)
- **KISA 원문**: https://www.kisa.or.kr/2060204/form?postSeq=9
- **공공기관 기준 49개 항목**: 행정기관 및 공공기관 정보시스템 구축·운영 지침 [별표3]
