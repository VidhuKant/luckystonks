#!/usr/bin/env bash
# Stop demo UI stack: peers, web, insight (by saved PIDs and known ports).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/data/runtime/demo-ui/pids.json"

kill_pid() {
  local pid=$1
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

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

for port in 8765 50070 50051 50052 50053 60051 60052 60053; do
  pids=$(lsof -ti ":$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "Stopping process(es) on port $port: $pids"
    kill $pids 2>/dev/null || true
  fi
done

sleep 0.5
echo "Demo stack stopped. You can run: bash scripts/run_demo_ui.sh"
