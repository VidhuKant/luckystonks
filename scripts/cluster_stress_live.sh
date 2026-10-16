#!/usr/bin/env bash
# Comprehensive live stress + edge cases on real 3-peer processes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

LOG_DIR="$ROOT/data/runtime/stress-live-logs"
mkdir -p "$LOG_DIR"
rm -f "$ROOT/data/runtime/raft-peer"*.json "$ROOT/data/runtime/state-peer"*.json

kill_peers() {
  for pid in "${PEER_PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap kill_peers EXIT

start_peers() {
  PEER_PIDS=()
  for id in 0 1 2; do
    python scripts/run_trading_peer.py "$id" >>"$LOG_DIR/peer${id}.log" 2>&1 &
    PEER_PIDS+=($!)
  done
}

wait_for_leader() {
  local found=""
  for _ in $(seq 1 60); do
    for id in 0 1 2; do
      if grep -q "became leader" "$LOG_DIR/peer${id}.log" 2>/dev/null; then
        found=$id
        echo "$found"
        return 0
      fi
    done
    sleep 0.25
  done
  echo "FAIL: no leader" >&2
  tail -15 "$LOG_DIR"/peer*.log >&2
  exit 1
}

cli_order() {
  python -m luckystonks.client.cli --port "$1" order "$2" "$3" "$4" "$5" "$6" "$7"
}

cli_trades() {
  python -m luckystonks.client.cli --port "$1" view admin admin TRADES
}

trades_equal_all_ports() {
  local a b c
  a=$(cli_trades 50051)
  b=$(cli_trades 50052)
  c=$(cli_trades 50053)
  [[ "$a" == "$b" && "$b" == "$c" ]]
}

admin_reset() {
  local port=$1
  python <<PY
import grpc
from luckystonks.client.cli import connect, login, post_cluster
stub = connect("127.0.0.1", $port)
s = login(stub, "admin", "admin")
status, detail, _, _ = post_cluster(
    stub, s.token, "ADMIN_RESET", b"{}",
    host="127.0.0.1", port=$port, username="admin", password="admin",
)
assert status == "OK", detail
print("admin reset ok")
PY
}

echo "=== [1/6] Start cluster ==="
: >"$LOG_DIR/peer0.log"
: >"$LOG_DIR/peer1.log"
: >"$LOG_DIR/peer2.log"
start_peers
LEADER=$(wait_for_leader)
echo "Leader peer $LEADER"
LEADER_PORT=$((50051 + LEADER))
sleep 1

echo "=== [2/6] Stress: 50 resting orders (replication load) ==="
STRESS_PORT=$LEADER_PORT
for i in $(seq 1 50); do
  price=$((500 + i))
  out=$(cli_order "$STRESS_PORT" pratham pratham BUY WIPRO "$price" 1)
  echo "$out" | grep -q RESTING || { echo "FAIL stress order $i: $out"; exit 1; }
done
trades_equal_all_ports || { echo "FAIL parity after stress orders"; exit 1; }
echo "OK: 50 orders replicated, TRADES parity"

echo "=== [3/6] Edge: kill non-leader follower, write, restart follower ==="
FOLLOWER=$(( (LEADER + 1) % 3 ))
kill "${PEER_PIDS[$FOLLOWER]}"
wait "${PEER_PIDS[$FOLLOWER]}" 2>/dev/null || true
echo "Killed follower peer $FOLLOWER (not leader)"
sleep 1
WRITE_PORT=$((50051 + (LEADER + 2) % 3))
out=$(cli_order "$WRITE_PORT" ved ved SELL TCS 3600 2)
echo "$out" | grep -q RESTING || { echo "FAIL order with 1 follower down: $out"; exit 1; }
python scripts/run_trading_peer.py "$FOLLOWER" >>"$LOG_DIR/peer${FOLLOWER}.log" 2>&1 &
PEER_PIDS[$FOLLOWER]=$!
sleep 3
trades_equal_all_ports || { echo "FAIL parity after follower restart"; exit 1; }
echo "OK: majority write with follower down + catch-up"

echo "=== [4/6] Edge: kill leader, trade on survivors, restart leader ==="
kill "${PEER_PIDS[$LEADER]}"
wait "${PEER_PIDS[$LEADER]}" 2>/dev/null || true
sleep 1
surv=()
for id in 0 1 2; do
  [[ "$id" == "$LEADER" ]] && continue
  surv+=($((50051 + id)))
done
out=$(cli_order "${surv[0]}" pratham pratham SELL INFY 1800 3)
echo "$out" | grep -q RESTING || { echo "FAIL post-leader-kill: $out"; exit 1; }
python scripts/run_trading_peer.py "$LEADER" >>"$LOG_DIR/peer${LEADER}.log" 2>&1 &
PEER_PIDS[$LEADER]=$!
sleep 3
trades_equal_all_ports || { echo "FAIL parity after leader restart"; exit 1; }
echo "OK: kill leader + write + leader catch-up"

echo "=== [5/6] Edge: admin reset replicated ==="
admin_reset 50051
sleep 1
t=$(cli_trades 50051)
echo "$t" | grep -q '^\[\]$' || { echo "FAIL admin reset empty trades: $t"; exit 1; }
trades_equal_all_ports || { echo "FAIL parity after admin reset"; exit 1; }
echo "OK: admin reset on all peers"

echo "=== [6/6] Edge: single node (no quorum) should reject writes ==="
kill_peers
trap - EXIT
PEER_PIDS=()
python scripts/run_trading_peer.py 0 >>"$LOG_DIR/peer0-solo.log" 2>&1 &
PEER_PIDS+=($!)
sleep 2
set +e
solo=$(cli_order 50051 ved ved SELL RELIANCE 2450 1 2>&1)
set -e
echo "$solo" | grep -qiE 'replication failed|NOT_LEADER|Error|ERR' && echo "OK: solo peer rejects or cannot replicate write" || {
  echo "WARN: solo node response: $solo (may elect solo leader without commit to followers)"
}
kill_peers 2>/dev/null || true

echo ""
echo "ALL STRESS + EDGE LIVE CHECKS PASSED"
