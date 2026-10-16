#!/usr/bin/env bash
# Advanced live stress: concurrent CLI clients, partition (isolated/minority nodes), explicit host peer wiring.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
# shellcheck source=scripts/cluster_lib.sh
source "$ROOT/scripts/cluster_lib.sh"

LOG_DIR="$ROOT/data/runtime/advanced-stress-logs"
mkdir -p "$LOG_DIR"
PEER_PIDS=()
trap kill_peers EXIT

echo "=== Advanced stress (concurrent + partition + multihost-style wiring) ==="
wipe_runtime_state
: >"$LOG_DIR/peer0.log"
: >"$LOG_DIR/peer1.log"
: >"$LOG_DIR/peer2.log"

echo "--- [1/5] Multihost-style config (explicit 127.0.0.1 in RAFT_PEERS / TRADING_PEERS) ---"
export RAFT_HOST=127.0.0.1
export TRADING_HOST=127.0.0.1
export RAFT_PEERS="0=127.0.0.1:60051,1=127.0.0.1:60052,2=127.0.0.1:60053"
export TRADING_PEERS="0=127.0.0.1:50051,1=127.0.0.1:50052,2=127.0.0.1:50053"
start_peers
LEADER=$(wait_for_leader)
LEADER_PORT=$((50051 + LEADER))
echo "Leader peer $LEADER (port $LEADER_PORT)"
sleep 1

echo "--- [2/5] Concurrent CLI stress (200 parallel orders, 40 workers) ---"
python scripts/run_concurrent_orders.py --port "$LEADER_PORT" --count 200 --workers 40
trades_equal_all_ports || { echo "FAIL: TRADES mismatch after concurrent orders"; exit 1; }
echo "OK: 200 concurrent orders + TRADES parity"

echo "--- [3/5] Partition: isolate minority (peer 2 down), majority must still write ---"
kill "${PEER_PIDS[2]}" 2>/dev/null || true
wait "${PEER_PIDS[2]}" 2>/dev/null || true
sleep 1
python -m luckystonks.client.cli --port 50051 order ved ved SELL TCS 3600 2 | grep -q RESTING
python -m luckystonks.client.cli --port 50051 order pratham pratham BUY TCS 3600 2 | grep -q FILLED
python -m luckystonks.client.cli --port 50051 view admin admin TRADES | grep -q TCS
python -m luckystonks.client.cli --port 50052 view admin admin TRADES | grep -q TCS
start_peer 2
sleep 3
trades_equal_all_ports || { echo "FAIL: peer 2 catch-up after isolation"; exit 1; }
echo "OK: majority partition (peer 2 isolated) still replicates"

echo "--- [4/5] Partition: minority alone (only peer 2 up) must not commit new writes ---"
kill "${PEER_PIDS[0]}" "${PEER_PIDS[1]}" 2>/dev/null || true
wait "${PEER_PIDS[0]}" 2>/dev/null || true
wait "${PEER_PIDS[1]}" 2>/dev/null || true
sleep 2
set +e
solo=$(python -m luckystonks.client.cli --port 50053 order ved ved SELL RELIANCE 2400 1 2>&1)
set -e
echo "$solo" | grep -qiE 'replication failed|NOT_LEADER|Error|ERR|RuntimeError' \
  && echo "OK: solo/minority partition rejects or cannot replicate" \
  || { echo "FAIL: solo node unexpectedly accepted write: $solo"; exit 1; }

echo "--- [5/5] Heal partition: restart all peers, TRADES parity ---"
kill_peers
trap - EXIT
PEER_PIDS=()
sleep 1
start_peers
sleep 4
trades_equal_all_ports || { echo "FAIL: parity after full cluster restart (persistence)"; exit 1; }
echo "OK: cluster healed; persisted TRADES match on all ports"

echo ""
echo "ALL ADVANCED STRESS CHECKS PASSED"
