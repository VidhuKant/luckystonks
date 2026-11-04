#!/usr/bin/env bash
# Stop demo UI stack: peers, web, insight (by saved PIDs and known ports).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/data/runtime/demo-ui/pids.json"

if [[ -f "$PID_FILE" ]]; then
  python3 - <<PY
import json, os, signal
from pathlib import Path
p = Path("$PID_FILE")
for pid in json.loads(p.read_text()).values():
    try:
        os.kill(int(pid), signal.SIGTERM)
    except (ProcessLookupError, ValueError, TypeError):
        pass
PY
  sleep 0.5
fi

# Always clear web/insight + up to 5-peer trading/raft ports (covers CLUSTER_SIZE 3 or 5).
for port in 8765 50070 \
  50051 50052 50053 50054 50055 \
  60051 60052 60053 60054 60055; do
  pids=$(lsof -ti ":$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "Stopping process(es) on port $port: $pids"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
  fi
done

sleep 0.5
# Force-clear anything that ignored SIGTERM (common cause of "address already in use").
for port in 8765 50070 \
  50051 50052 50053 50054 50055 \
  60051 60052 60053 60054 60055; do
  pids=$(lsof -ti ":$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "Force-killing process(es) on port $port: $pids"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
done

sleep 0.3
echo "Demo stack stopped. You can run: bash scripts/run_demo_ui.sh"
