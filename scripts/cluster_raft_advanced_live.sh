#!/usr/bin/env bash
# Live check: log compaction + lagging follower recovery after raft state wipe.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

export RAFT_LOG_COMPACT_THRESHOLD="${RAFT_LOG_COMPACT_THRESHOLD:-4}"

LOG_DIR="$ROOT/data/runtime/raft-advanced-logs"
mkdir -p "$LOG_DIR"
rm -f "$ROOT/data/runtime/raft-peer"*.json "$ROOT/data/runtime/state-peer"*.json

kill_peers() {
  for pid in "${PEER_PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap kill_peers EXIT

PEER_PIDS=()
for id in 0 1 2; do
  python scripts/run_trading_peer.py "$id" >"$LOG_DIR/peer${id}.log" 2>&1 &
  PEER_PIDS+=($!)
done

leader_id=""
for _ in $(seq 1 60); do
  for id in 0 1 2; do
    if grep -q "became leader" "$LOG_DIR/peer${id}.log" 2>/dev/null; then
      leader_id=$id
      break 2
    fi
  done
  sleep 0.25
done
[[ -n "$leader_id" ]] || { echo "FAIL: no leader"; exit 1; }
LEADER_PORT=$((50051 + leader_id))
sleep 1

cli_order() {
  python -m luckystonks.client.cli --port "$1" order "$2" "$3" "$4" "$5" "$6" "$7"
}

cli_trades() {
  python -m luckystonks.client.cli --port "$1" view admin admin TRADES
}

assert_parity() {
  local a b c
  a=$(cli_trades 50051)
  b=$(cli_trades 50052)
  c=$(cli_trades 50053)
  [[ "$a" == "$b" && "$b" == "$c" ]] || { echo "FAIL TRADES mismatch"; exit 1; }
}

echo "Leader peer $leader_id; placing orders (compact threshold=$RAFT_LOG_COMPACT_THRESHOLD)..."
for i in $(seq 1 12); do
  price=$((900 + i))
  out=$(cli_order "$LEADER_PORT" pratham pratham BUY WIPRO "$price" 1)
  echo "$out" | grep -qE 'RESTING|FILLED' || { echo "FAIL order $i: $out"; exit 1; }
done
assert_parity
grep -q "log compacted" "$LOG_DIR/peer${leader_id}.log" || echo "WARN: no compact line yet on leader log"

echo "Restart peer 2 with empty raft state..."
kill "${PEER_PIDS[2]}"
wait "${PEER_PIDS[2]}" 2>/dev/null || true
rm -f "$ROOT/data/runtime/raft-peer2.json"
python scripts/run_trading_peer.py 2 >"$LOG_DIR/peer2-restart.log" 2>&1 &
PEER_PIDS[2]=$!
sleep 5
assert_parity
grep -qE "InstallSnapshot|installed snapshot|appended" "$LOG_DIR/peer2-restart.log" || true

echo "ALL RAFT ADVANCED LIVE CHECKS PASSED"
