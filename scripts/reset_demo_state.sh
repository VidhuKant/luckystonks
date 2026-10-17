#!/usr/bin/env bash
# Wipe local demo cluster state (orders, portfolios, Raft log) — peers must be stopped.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/scripts/stop_demo_ui.sh" 2>/dev/null || true
rm -f "$ROOT/data/runtime/raft-peer"*.json "$ROOT/data/runtime/state-peer"*.json
echo "Cleared data/runtime/raft-peer*.json and state-peer*.json"
echo "Start again: bash scripts/run_demo_ui.sh"
