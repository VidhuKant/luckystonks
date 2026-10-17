#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

PORT="${UI_WEB_PORT:-8765}"
BASE="http://127.0.0.1:${PORT}"

echo "UI verify: ${BASE}"

curl -sf "${BASE}/" | grep -qi "luckystonks" || { echo "FAIL: index"; exit 1; }

curl -sf "${BASE}/api/ops/cluster" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'peers' in d and len(d['peers'])==3
print('cluster ok leader', d.get('leader_peer_id'))
"

COOKIE_JAR=$(mktemp)
trap 'rm -f "$COOKIE_JAR"' EXIT

curl -sf -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST "${BASE}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"pratham","password":"pratham"}' | grep -q pratham

curl -sf -b "$COOKIE_JAR" "${BASE}/api/trade/portfolio" | grep -q cash

curl -sf -b "$COOKIE_JAR" -X POST "${BASE}/api/trade/order" \
  -H 'Content-Type: application/json' \
  -d '{"side":"BUY","symbol":"WIPRO","price":910,"qty":1}' | grep -q status

curl -sf "${BASE}/api/ops/parity" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('parity', d.get('parity'))
"

# Admin tab APIs (403 for normal user, OK for admin)
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$COOKIE_JAR" "${BASE}/api/admin/portfolios")
[[ "$code" == "403" ]] || { echo "FAIL: non-admin should get 403 on admin portfolios, got $code"; exit 1; }

curl -sf -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST "${BASE}/api/auth/logout" >/dev/null

curl -sf -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST "${BASE}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | grep -q '"role":"admin"'

curl -sf -b "$COOKIE_JAR" "${BASE}/api/admin/portfolios" | grep -q user_id
curl -sf -b "$COOKIE_JAR" "${BASE}/api/admin/order-log" | python3 -c "import json,sys; json.load(sys.stdin)"

echo "ALL UI API CHECKS PASSED"
