#!/usr/bin/env bash
# Start N Raft peers (CLUSTER_SIZE=3|5, default 5) + Insight (optional) + web UI.
#
# Processes are started in a new session (daemonized) so they survive when this
# launcher shell exits (Cursor/agent terminals otherwise SIGHUP the whole stack).
# Stop with: bash scripts/stop_demo_ui.sh
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

CLUSTER_SIZE="${CLUSTER_SIZE:-5}"
if [[ "$CLUSTER_SIZE" != "3" && "$CLUSTER_SIZE" != "5" ]]; then
  echo "CLUSTER_SIZE must be 3 or 5 (got $CLUSTER_SIZE)" >&2
  exit 2
fi
export CLUSTER_SIZE

# By default keep orders/portfolios across stop/start. Wipe only when requested.
if [[ "${UI_FRESH_CLUSTER:-0}" == "1" ]]; then
  echo "UI_FRESH_CLUSTER=1 — wiping Raft + trading state under data/runtime/"
  rm -f "$ROOT/data/runtime/raft-peer"*.json \
        "$ROOT/data/runtime/raft-status-peer"*.json \
        "$ROOT/data/runtime/state-peer"*.json
fi

UI_CLIENT_TRADING_PORT="${UI_CLIENT_TRADING_PORT:-50052}"
UI_WEB_PORT="${UI_WEB_PORT:-8765}"
export UI_CLIENT_TRADING_PORT UI_TRADING_HOST="${UI_TRADING_HOST:-127.0.0.1}"

# Stop any leftover stack from a prior run (safe if nothing is running).
bash "$ROOT/scripts/stop_demo_ui.sh" 2>/dev/null || true

echo "{}" > "$PID_FILE"

PY_BIN="$(command -v python)"

# Launch argv in a new session; print child PID. Survives launcher shell exit.
detach_python() {
  local log_file="$1"
  shift
  "$PY_BIN" - "$ROOT" "$log_file" "$@" <<'PY'
import os, subprocess, sys
root, log_file, *argv = sys.argv[1:]
log = open(log_file, "a", encoding="utf-8")
proc = subprocess.Popen(
    argv,
    stdout=log,
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    cwd=root,
    env=os.environ.copy(),
    start_new_session=True,
    close_fds=True,
)
print(proc.pid)
PY
}

declare -a PEER_PIDS=()
for ((id = 0; id < CLUSTER_SIZE; id++)); do
  : >"$LOG_DIR/peer${id}.log"
  peer_pid="$(detach_python "$LOG_DIR/peer${id}.log" "$PY_BIN" scripts/run_trading_peer.py "$id")"
  PEER_PIDS+=("$peer_pid")
done

INSIGHT_PID=""
if [[ "${UI_START_INSIGHT:-1}" == "1" ]]; then
  : >"$LOG_DIR/insight.log"
  INSIGHT_PID="$(detach_python "$LOG_DIR/insight.log" "$PY_BIN" scripts/run_llm.py)"
fi

echo "Waiting for leader (CLUSTER_SIZE=${CLUSTER_SIZE}, quorum=$((CLUSTER_SIZE / 2 + 1)))..."
leader_found=0
for _ in $(seq 1 120); do
  for ((id = 0; id < CLUSTER_SIZE; id++)); do
    if grep -q "became leader" "$LOG_DIR/peer${id}.log" 2>/dev/null; then
      echo "Leader on peer $id"
      leader_found=1
      break 2
    fi
  done
  sleep 0.25
done
if [[ "$leader_found" -ne 1 ]]; then
  echo "WARNING: no leader elected yet — check $LOG_DIR/peer*.log for RequestVote errors" >&2
fi

export UI_BIND=0.0.0.0
export UI_WEB_PORT
: >"$LOG_DIR/web.log"
WEB_PID="$(detach_python "$LOG_DIR/web.log" "$PY_BIN" -m web.server)"

python3 - "$PID_FILE" "$WEB_PID" "$INSIGHT_PID" "${PEER_PIDS[@]}" <<'PY'
import json, sys
from pathlib import Path
pid_file, web_pid, insight_pid, *peer_pids = sys.argv[1:]
pids = {str(i): int(p) for i, p in enumerate(peer_pids)}
pids["web"] = int(web_pid)
if insight_pid:
    pids["insight"] = int(insight_pid)
Path(pid_file).write_text(json.dumps(pids, indent=2))
PY

ready=0
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${UI_WEB_PORT}/api/ops/cluster" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.25
done

QUORUM=$((CLUSTER_SIZE / 2 + 1))
echo ""
echo "=========================================="
echo " LuckyStonks Terminal UI"
echo " Trade + Ops:  http://127.0.0.1:${UI_WEB_PORT}/"
echo " Cluster:       ${CLUSTER_SIZE} peers (quorum ${QUORUM})  CLUSTER_SIZE=${CLUSTER_SIZE}"
echo " Client gRPC:   follower port ${UI_CLIENT_TRADING_PORT} (peer $((UI_CLIENT_TRADING_PORT - 50051)))"
echo " Logs:          $LOG_DIR"
echo " Stop stack:    bash scripts/stop_demo_ui.sh"
echo " Switch size:   CLUSTER_SIZE=3 bash scripts/run_demo_ui.sh"
if [[ "${UI_FRESH_CLUSTER:-0}" == "1" ]]; then
  echo " State:         fresh cluster (UI_FRESH_CLUSTER=1)"
else
  echo " State:         persisted in data/runtime/*-peer*.json"
  echo " Fresh wipe:    UI_FRESH_CLUSTER=1 bash scripts/run_demo_ui.sh"
fi
if [[ "$ready" -eq 1 ]]; then
  echo " Status:        web ready (detached sessions — survives launcher exit)"
else
  echo " Status:        web not responding yet — check $LOG_DIR/web.log" >&2
fi
echo "=========================================="
