#!/usr/bin/env bash
# Live 3-peer verification: trades, parity, kill-leader + write on 2 nodes, restart survivor.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

LOG_DIR="$ROOT/data/runtime/live-verify-logs"
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

echo "Waiting for leader election..."
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
if [[ -z "$leader_id" ]]; then
  echo "FAIL: no leader within 15s"
  tail -20 "$LOG_DIR"/peer*.log
  exit 1
fi
echo "Leader is peer $leader_id"
LEADER_PORT=$((50051 + leader_id))
sleep 1

cli_order() {
  python -m luckystonks.client.cli --port "$1" order "$2" "$3" "$4" "$5" "$6" "$7"
}

cli_trades() {
  python -m luckystonks.client.cli --port "$1" view admin admin TRADES
}

out1=$(cli_order "$LEADER_PORT" ved ved SELL RELIANCE 2450 10)
echo "$out1" | grep -q RESTING || { echo "FAIL sell: $out1"; exit 1; }
out2=$(cli_order "$LEADER_PORT" pratham pratham BUY RELIANCE 2450 10)
echo "$out2" | grep -q FILLED || { echo "FAIL buy: $out2"; exit 1; }

t51=$(cli_trades 50051)
t52=$(cli_trades 50052)
t53=$(cli_trades 50053)
[[ "$t51" == "$t52" && "$t52" == "$t53" ]] || { echo "FAIL TRADES mismatch"; exit 1; }
echo "OK: 3-peer trades + parity"

kill "${PEER_PIDS[$leader_id]}"
wait "${PEER_PIDS[$leader_id]}" 2>/dev/null || true
unset 'PEER_PIDS[$leader_id]'
echo "Killed leader peer $leader_id"

new_leader=""
for _ in $(seq 1 40); do
  for id in 0 1 2; do
    [[ "$id" == "$leader_id" ]] && continue
    if tail -5 "$LOG_DIR/peer${id}.log" | grep -q "became leader"; then
      new_leader=$id
      break 2
    fi
  done
  sleep 0.25
done
if [[ -z "$new_leader" ]]; then
  echo "WARN: no new became leader line yet; trying order anyway"
else
  echo "New leader peer $new_leader"
fi

sleep 1
surv_ports=()
for id in 0 1 2; do
  [[ "$id" == "$leader_id" ]] && continue
  surv_ports+=($((50051 + id)))
done
cli_port="${surv_ports[0]}"
out3=$(cli_order "$cli_port" ved ved SELL TCS 3500 5)
echo "$out3" | grep -q RESTING || { echo "FAIL post-kill sell: $out3"; tail -30 "$LOG_DIR"/peer*.log; exit 1; }
out4=$(cli_order "$cli_port" pratham pratham BUY TCS 3500 5)
echo "$out4" | grep -q FILLED || { echo "FAIL post-kill buy: $out4"; tail -30 "$LOG_DIR"/peer*.log; exit 1; }
for port in "${surv_ports[@]}"; do
  cli_trades "$port" | grep -q TCS || { echo "FAIL no TCS on $port"; exit 1; }
done
echo "OK: kill-leader + orders on surviving peers"

python scripts/run_trading_peer.py "$leader_id" >>"$LOG_DIR/peer${leader_id}.log" 2>&1 &
PEER_PIDS+=($!)
sleep 3
t51=$(cli_trades 50051)
t52=$(cli_trades 50052)
t53=$(cli_trades 50053)
[[ "$t51" == "$t52" && "$t52" == "$t53" ]] || { echo "FAIL after restart parity"; exit 1; }
echo "OK: restarted peer caught up"

echo "ALL LIVE CHECKS PASSED"
