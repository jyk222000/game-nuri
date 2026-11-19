#!/usr/bin/env bash
# 사용: CONNECT_URL=http://kafka1:8083 ./apply.sh   (.env 값으로 ${...} 치환 후 등록)
set -euo pipefail
cd "$(dirname "$0")"
set -a; source ../../.env; set +a
URL="${CONNECT_URL:-${KAFKA_CONNECT_URL}}"
for f in *.json; do
  name=$(python3 -c "import json,sys;print(json.load(open('$f'))['name'])")
  cfg=$(envsubst < "$f" | python3 -c "import json,sys;print(json.dumps(json.load(sys.stdin)['config']))")
  echo "→ $name"
  curl -fsS -X PUT -H 'Content-Type: application/json' "$URL/connectors/$name/config" -d "$cfg" >/dev/null
done
curl -fsS "$URL/connectors?expand=status" | python3 -m json.tool | head -50
