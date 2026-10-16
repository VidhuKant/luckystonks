#!/usr/bin/env bash
# Shared helpers for live cluster scripts.
set -euo pipefail

cluster_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

cluster_activate() {
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
}

kill_peers() {
  for pid in "${PEER_PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}

start_peers() {
  PEER_PIDS=()
  local id
  for id in 0 1 2; do
    python scripts/run_trading_peer.py "$id" >>"$LOG_DIR/peer${id}.log" 2>&1 &
    PEER_PIDS+=($!)
  done
}

start_peer() {
  local id=$1
  python scripts/run_trading_peer.py "$id" >>"$LOG_DIR/peer${id}.log" 2>&1 &
  PEER_PIDS[$id]=$!
}

wait_for_leader() {
  local found=""
  local _ id
  for _ in $(seq 1 60); do
    for id in 0 1 2; do
      if grep -q "became leader" "$LOG_DIR/peer${id}.log" 2>/dev/null; then
        echo "$id"
        return 0
      fi
    done
    sleep 0.25
  done
  echo "FAIL: no leader within 15s" >&2
  tail -20 "$LOG_DIR"/peer*.log >&2
  return 1
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

wipe_runtime_state() {
  rm -f "$ROOT/data/runtime/raft-peer"*.json "$ROOT/data/runtime/state-peer"*.json
}
