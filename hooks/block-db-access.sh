#!/bin/bash
# Bash 명령이 DB에 직접 접속하려는 시도인지 검사해 차단한다.
# 스키마/데이터 확인이 필요하면 사용자에게 조회를 요청할 것.

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$cmd" ] && exit 0

deny() {
  jq -n --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

GUIDE="DB 직접 접속은 차단되어 있습니다. 스키마(컬럼 타입/길이)나 데이터 확인이 필요하면 사용자에게 조회를 요청하세요."

# 1) JDBC 접속 문자열
if printf '%s' "$cmd" | grep -qiE 'jdbc:[a-z0-9]+:'; then
  deny "JDBC 접속 문자열이 포함되어 있습니다. $GUIDE"
fi

# 2) DB 클라이언트 CLI 실행 (명령 위치에서만 매칭 — 파일명 검색 오탐 방지)
DBCLI='tbsql|tbexport|tbimport|tbboot|sqlplus|sqlldr|expdp|impdp|mysql|mysqladmin|mysqldump|mysqlsh|psql|pg_dump|sqlcmd|osql|isql|iusql|mongo|mongosh|redis-cli'
if printf '%s' "$cmd" | grep -qE "(^|[;&|(]|&&|\|\||\\\$\()[[:space:]]*(sudo[[:space:]]+)?([A-Za-z0-9_/.~-]*/)?($DBCLI)([[:space:]]|$)"; then
  deny "DB 클라이언트 실행이 감지되었습니다. $GUIDE"
fi

# 3) JDBC 드라이버 jar를 실행·복사하는 시도 (검색/조회만 하는 명령은 통과)
DRIVER='(tibero[0-9]*|ojdbc|mysql-connector|mariadb-java-client|postgresql-[0-9.]+|mssql-jdbc|jtds)[^[:space:]]*\.jar'
RUNNER='java|javac|jshell|groovy|kotlin|kotlinc|scala|jruby|cp|mv|ln|install|rsync|scp'
if printf '%s' "$cmd" | grep -qiE "$DRIVER" \
   && printf '%s' "$cmd" | grep -qE "(^|[;&|(]|&&|\|\||\\\$\()[[:space:]]*(sudo[[:space:]]+)?([A-Za-z0-9_/.~-]*/)?($RUNNER)([[:space:]])"; then
  deny "JDBC 드라이버를 사용한 접속 시도가 감지되었습니다. $GUIDE"
fi

# 4) 스크립트 언어 DB 드라이버 / ORM 사용
if printf '%s' "$cmd" | grep -qiE '\b(jaydebeapi|pymysql|MySQLdb|mysql\.connector|psycopg2|cx_Oracle|oracledb|pyodbc|sqlalchemy|create_engine|DriverManager|getConnection|sequelize|mysql2|knex)\b'; then
  deny "DB 드라이버/커넥션 API 사용이 감지되었습니다. $GUIDE"
fi

# 5) DB 포트로의 직접 소켓 접속 (nc/telnet/socat, /dev/tcp)
DBPORT='1521|1526|8629|8790|8791|3306|33060|5432|1433|1434|27017|6379'
if printf '%s' "$cmd" | grep -qE "/dev/tcp/[^[:space:]]+/($DBPORT)\b"; then
  deny "DB 포트로의 직접 소켓 접속이 감지되었습니다. $GUIDE"
fi
if printf '%s' "$cmd" | grep -qE "(^|[;&|(]|&&|\|\||\\\$\()[[:space:]]*(sudo[[:space:]]+)?([A-Za-z0-9_/.~-]*/)?(nc|ncat|netcat|telnet|socat)([[:space:]])" \
   && printf '%s' "$cmd" | grep -qE "\b($DBPORT)\b"; then
  deny "DB 포트로의 직접 소켓 접속이 감지되었습니다. $GUIDE"
fi

exit 0
