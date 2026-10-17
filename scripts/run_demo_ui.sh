#!/usr/bin/env bash
# Start 3 Raft peers + Insight (optional) + Bloomberg-style web UI (one command).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r requirements.txt

RUNTIME="$ROOT/data/runtime/demo-ui"
LOG_DIR="$RUNTIME/logs"
PID_FILE="$RUNTIME/pids.json"
mkdir -p "$LOG_DIR"

# By default keep orders/portfolios across stop/start. Wipe only when requested.
if [[ "${UI_FRESH_CLUSTER:-0}" == "1" ]]; then
  echo "UI_FRESH_CLUSTER=1 — wiping Raft + trading state under data/runtime/"
  rm -f "$ROOT/data/runtime/raft-peer"*.json "$ROOT/data/runtime/state-peer"*.json
fi

UI_CLIENT_TRADING_PORT="${UI_CLIENT_TRADING_PORT:-50052}"
UI_WEB_PORT="${UI_WEB_PORT:-8765}"
export UI_CLIENT_TRADING_PORT UI_TRADING_HOST="${UI_TRADING_HOST:-127.0.0.1}"

# Stop any leftover stack from a prior run (safe if nothing is running).
bash "$ROOT/scripts/stop_demo_ui.sh" 2>/dev/null || true

kill_all() {
  if [[ -f "$PID_FILE" ]]; then
    python3 - <<PY
import json, os, signal
from pathlib import Path
p = Path("$PID_FILE")
for pid in json.loads(p.read_text()).values():
    try: os.kill(int(pid), signal.SIGTERM)
    except ProcessLookupError: pass
PY
  fi
  for pid in "${WEB_PID:-}" "${INSIGHT_PID:-}"; do
    [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true
  done
}
trap kill_all EXIT INT TERM

kill_all
echo "{}" > "$PID_FILE"

P0=""
P1=""
P2=""
python scripts/run_trading_peer.py 0 >>"$LOG_DIR/peer0.log" 2>&1 & P0=$!; disown "$P0" 2>/dev/null || true
python scripts/run_trading_peer.py 1 >>"$LOG_DIR/peer1.log" 2>&1 & P1=$!; disown "$P1" 2>/dev/null || true
python scripts/run_trading_peer.py 2 >>"$LOG_DIR/peer2.log" 2>&1 & P2=$!; disown "$P2" 2>/dev/null || true

INSIGHT_PID=""
if [[ "${UI_START_INSIGHT:-1}" == "1" ]]; then
  python scripts/run_llm.py >>"$LOG_DIR/insight.log" 2>&1 &
  INSIGHT_PID=$!
  disown "$INSIGHT_PID" 2>/dev/null || true
fi

echo "Waiting for leader..."
for _ in $(seq 1 60); do
  for id in 0 1 2; do
    if grep -q "became leader" "$LOG_DIR/peer${id}.log" 2>/dev/null; then
      echo "Leader on peer $id"
      break 2
    fi
  done
  sleep 0.25
done

export UI_BIND=0.0.0.0
export UI_WEB_PORT
python -m web.server >>"$LOG_DIR/web.log" 2>&1 &
WEB_PID=$!

python3 - <<PY
import json
from pathlib import Path
pids = {"0": int("$P0"), "1": int("$P1"), "2": int("$P2"), "web": int("$WEB_PID")}
insight = "$INSIGHT_PID"
if insight:
    pids["insight"] = int(insight)
Path("$PID_FILE").write_text(json.dumps(pids, indent=2))
PY

sleep 1
echo ""
echo "=========================================="
echo " LuckyStonks Terminal UI"
echo " Trade + Ops:  http://127.0.0.1:${UI_WEB_PORT}/"
echo " Client gRPC:   follower port ${UI_CLIENT_TRADING_PORT} (peer $((UI_CLIENT_TRADING_PORT - 50051)))"
echo " Logs:          $LOG_DIR"
echo " Stop stack:    bash scripts/stop_demo_ui.sh"
echo " Or Ctrl+C in this terminal"
if [[ "${UI_FRESH_CLUSTER:-0}" == "1" ]]; then
  echo " State:         fresh cluster (UI_FRESH_CLUSTER=1)"
else
  echo " State:         persisted in data/runtime/*-peer*.json"
  echo " Fresh wipe:    UI_FRESH_CLUSTER=1 bash scripts/run_demo_ui.sh"
fi
echo "=========================================="

wait "$WEB_PID"
