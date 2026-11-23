#!/usr/bin/env bash
# Kafka Connect 커넥터 등록(이미 있으면 설정을 덮어씀).
# 사용:
#   ./apply.sh                                            # 이 폴더의 커넥터 전부
#   ./apply.sh jdbc-sink-prices-current mongo-sink-raw    # 고른 것만 (파일 이름에서 .json을 뺀 이름)
# 접속 주소: CONNECT_URL 또는 .env의 KAFKA_CONNECT_URL
# 치환: .env의 MARIADB_USER, MARIADB_PASSWORD, MONGO_URI, ES_USER, ES_PASSWORD만 바꾼다.
#       TimestampConverter$Value의 '$', TimestampRouter의 ${topic}·${timestamp}가 지워지지 않게 하려는 것이다.
# 하나가 실패해도 나머지는 계속 등록하고, 끝에 상태를 보여 준다. 실패가 있으면 종료 코드 1.
set -euo pipefail
cd "$(dirname "$0")"
command -v envsubst >/dev/null || { echo "envsubst가 없습니다: sudo dnf install -y gettext"; exit 1; }
set -a; source ../../.env; set +a
URL="${CONNECT_URL:-${KAFKA_CONNECT_URL}}"
VARS='${MARIADB_USER} ${MARIADB_PASSWORD} ${MONGO_URI} ${ES_USER} ${ES_PASSWORD}'

if [ $# -gt 0 ]; then
  files=(); for n in "$@"; do files+=("${n%.json}.json"); done
else
  files=(*.json)
fi

fail=0
names=()
for f in "${files[@]}"; do
  if [ ! -f "$f" ]; then echo "✗ $f 파일 없음"; fail=1; continue; fi
  name=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$f")
  # 이 파일이 쓰는 .env 값이 비어 있으면 등록하지 않는다 (envsubst는 빈 값으로 바꿔 버린다)
  missing=""
  for v in $(grep -o '\${[A-Z_]*}' "$f" | tr -d '${}' | sort -u); do
    [ -n "${!v:-}" ] || missing="$missing $v"
  done
  if [ -n "$missing" ]; then echo "✗ $name .env에 값이 없음:$missing"; fail=1; continue; fi
  # 설정 내용(비밀번호 포함)은 명령 인자가 아니라 표준 입력으로 넘긴다 (ps에 보이지 않게)
  if ! cfg=$(envsubst "$VARS" < "$f" | python3 -c '
import json, re, sys
c = json.load(sys.stdin)["config"]
left = [k for k, v in c.items() if re.search(r"\$\{[A-Z_]+\}", str(v))]
if left:
    sys.exit("치환되지 않은 값: " + ", ".join(left) + " (.env 확인)")
print(json.dumps({k: v for k, v in c.items() if not k.startswith("_")}))'); then
    echo "✗ $name 설정 확인 필요"; fail=1; continue
  fi
  if printf '%s' "$cfg" | curl -fsS -X PUT -H 'Content-Type: application/json' \
       "$URL/connectors/$name/config" --data-binary @- >/dev/null; then
    echo "✓ $name 등록"
    names+=("$name")
  else
    echo "✗ $name 등록 실패"; fail=1
  fi
done

sleep 5
curl -fsS "$URL/connectors?expand=status" | python3 -c '
import json, sys
for name, v in sorted(json.load(sys.stdin).items()):
    s = v["status"]
    tasks = ", ".join("%s:%s@%s" % (t["id"], t["state"], t["worker_id"]) for t in s["tasks"]) or "-"
    print("%-32s %-9s tasks %s" % (name, s["connector"]["state"], tasks))'
exit $fail
