# LuckyStonks — Run guide

## Bloomberg-style web UI (one command)

```bash
bash scripts/run_demo_ui.sh
```

Open **http://127.0.0.1:8765/** — **Trade** (login, orders on **follower** port 50052 by default), **Operations** (cluster health, leader, logs, stop/start peers, parity check), and **Admin** (visible only when logged in as seed user `admin` / `admin`: all portfolios, order log, market reset, cluster membership).

Verify APIs (stack must be running):

```bash
bash scripts/verify_ui.sh
```

Env: `UI_CLIENT_TRADING_PORT=50052`, `UI_WEB_PORT=8765`, `UI_START_INSIGHT=1`.

**Stop** (from another terminal, or before re-running):

```bash
bash scripts/stop_demo_ui.sh
```

Or **Ctrl+C** in the terminal where `run_demo_ui.sh` is running. Re-running `run_demo_ui.sh` without stopping first also calls `stop_demo_ui.sh` automatically.

**Persistence:** `run_demo_ui.sh` **does not** wipe cluster data on restart. Orders and portfolios are stored in `data/runtime/state-peer*.json` and `data/runtime/raft-peer*.json` and reload when peers start again.

To reset the market to seed (empty trades, fresh users from seed file):

```bash
bash scripts/reset_demo_state.sh
# or: UI_FRESH_CLUSTER=1 bash scripts/run_demo_ui.sh
```

Use **Admin → Reset market to seed** in the UI for a replicated reset without deleting local files manually.

---

## One-time setup

```bash
cd luckystonks
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x scripts/gen_proto.sh
./scripts/gen_proto.sh
```

Optional `.env` (Insight / LLM only):

```env
LUCKYSTONKS_TRADING_READ_TOKEN=local-insight-read-token
LUCKYSTONKS_TRADING_ADDR=127.0.0.1:50051
LUCKYSTONKS_VLLM_BASE_URL=https://YOUR-SUBDOMAIN.ngrok-free.dev/v1
LUCKYSTONKS_VLLM_MODEL=Qwen/Qwen3-0.6B
```

## Accounts

| Username | Password | Notes |
|----------|----------|--------|
| `ved` | `ved` | RELIANCE, TCS, HDFCBANK |
| `pratham` | `pratham` | INFY, WIPRO, TATAMOTORS |
| `vidhu` | `vidhu` | BHARTIARTL, ITC, SBIN |
| `admin` | `admin` | Menu 6–8 |

Every terminal below: `cd luckystonks && source .venv/bin/activate`

---

## 1. Automated tests (pytest)

```bash
pytest -q
```

Expect: `47 passed` (or current count), exit code 0.

---

## 2. Live cluster verification (run in order)

One-time:

```bash
chmod +x scripts/cluster_live_verify.sh scripts/cluster_stress_live.sh scripts/cluster_advanced_stress_live.sh
```

Full regression (same as CI-style local check; ~1–2 minutes):

```bash
pytest -q
./scripts/cluster_live_verify.sh
./scripts/cluster_stress_live.sh
./scripts/cluster_advanced_stress_live.sh
```

| Script | Last line on success | What it runs |
|--------|----------------------|--------------|
| `cluster_live_verify.sh` | `ALL LIVE CHECKS PASSED` | 3 peers → 2 trades → TRADES match on 50051/52/53 → kill leader → 2 trades on survivors → restart dead peer → parity |
| `cluster_stress_live.sh` | `ALL STRESS + EDGE LIVE CHECKS PASSED` | 50 sequential orders → kill follower → write → restart → kill leader → write → admin reset → solo peer (no quorum) |
| `cluster_advanced_stress_live.sh` | `ALL ADVANCED STRESS CHECKS PASSED` | Explicit `127.0.0.1` peer addrs → **200 parallel** CLI orders (40 workers) → kill peer 2 (majority still writes) → only peer 2 up (write fails) → restart all 3 → persisted TRADES parity |
| `cluster_raft_advanced_live.sh` | `ALL RAFT ADVANCED LIVE CHECKS PASSED` | Low `RAFT_LOG_COMPACT_THRESHOLD` → many orders → log compaction → wipe peer 2 raft JSON + restart → TRADES parity (InstallSnapshot / catch-up) |

Each script wipes `data/runtime/raft-peer*.json` and `state-peer*.json`, starts its own peer processes, and stops them when done.

Concurrent-only (peers must already be running; pick leader port 50051/52/53):

```bash
python scripts/run_concurrent_orders.py --port 50051 --count 200 --workers 40
```

Expect: `"failed": 0` in JSON output.

Logs if a script fails:

- `data/runtime/live-verify-logs/peer*.log`
- `data/runtime/stress-live-logs/peer*.log`
- `data/runtime/advanced-stress-logs/peer*.log`

Optional env: `RAFT_LOG_LEVEL=DEBUG`, `RAFT_LOG_COMPACT_THRESHOLD=8` (default; lower = compact sooner).

Admin **cluster membership** (leader only, replicated): `Post` type `CLUSTER_CHANGE` with JSON
`{"action":"add|remove","peer_id":N,"raft_addr":"host:port","trading_addr":"host:port"}` (addrs may be empty for remove).

---

## 3. Single-server demo (no Raft)

**Terminal A — server**

```bash
python scripts/run_trading_server.py
```

**Terminal B — client (pick one)**

Scripted:

```bash
python -m luckystonks.client.cli demo
python -m luckystonks.client.cli view pratham pratham TRADES
```

Interactive login + menu:

```bash
python -m luckystonks.client.cli --port 50051
```

**Stop server:** Terminal A → `Ctrl+C`

---

## 4. Multi-peer cluster demo (Raft, M2)

### 4.1 Start cluster

**Terminal A**

```bash
python scripts/run_trading_peer.py 0
```

**Terminal B**

```bash
python scripts/run_trading_peer.py 1
```

**Terminal C**

```bash
python scripts/run_trading_peer.py 2
```

Start all three within ~10 seconds. In logs, find **`became leader`** on exactly one terminal (peer 0 → port **50051**, peer 1 → **50052**, peer 2 → **50053**).

Optional clean state before start:

```bash
rm -f data/runtime/raft-peer*.json data/runtime/state-peer*.json
```

### 4.2 Client on a non-leader (recommended for demo)

You may use **any** trading port. Connect to a **follower** on purpose; orders (menu **5**) and admin reset (menu **8**) redirect to the leader and re-login automatically.

**Terminal D**

```bash
python -m luckystonks.client.cli --port 50052
```

(Use `50051` or `50053` instead if you prefer.)

Do **not** use `cli demo` on the cluster — it does not follow leader redirect. Use interactive menu **5** or `order` subcommand.

### 4.3 Interactive login and menu

1. Username / password (e.g. `ved` / `ved`).
2. Menu:

| Key | Action |
|-----|--------|
| 1 | Portfolio |
| 2 | Open orders |
| 3 | Order book |
| 4 | Trades |
| 5 | Place limit order |
| 6 | Admin: all portfolios |
| 7 | Admin: order log |
| 8 | Admin: reset market (type `YES`) |
| L | Logout |
| Q | Quit |

Example trade: login `ved` → **5** → SELL RELIANCE 2450 qty 10 → **L** → login `pratham` → **5** → BUY RELIANCE 2450 qty 10 → **4** to view trades.

Scripted (same cluster, any port):

```bash
python -m luckystonks.client.cli --port 50052 order ved ved SELL RELIANCE 2450 10
python -m luckystonks.client.cli --port 50052 order pratham pratham BUY RELIANCE 2450 10
python -m luckystonks.client.cli --port 50051 view admin admin TRADES
python -m luckystonks.client.cli --port 50052 view admin admin TRADES
python -m luckystonks.client.cli --port 50053 view admin admin TRADES
```

All three `TRADES` outputs must match.

### 4.4 Kill-leader demo (manual)

1. Note which terminal logged **`became leader`** (that peer is the leader).
2. **Ctrl+C** only that terminal (leader). Leave the other two running.
3. Wait ~2 seconds; another peer should log **`became leader`**.
4. Terminal D — use a **survivor** port (not the dead peer’s port):

```bash
python -m luckystonks.client.cli --port 50051 order ved ved SELL TCS 3500 5
python -m luckystonks.client.cli --port 50051 order pratham pratham BUY TCS 3500 5
```

5. Check `view admin admin TRADES` on survivor ports.
6. Restart killed peer in its terminal:

```bash
python scripts/run_trading_peer.py N
```

(`N` = 0, 1, or 2). Wait a few seconds; TRADES on all three ports should match again.

### 4.5 Stop cluster

**Ctrl+C** in each peer terminal (A, B, C). Or from repo root:

```bash
lsof -i :50051 -i :50052 -i :50053 -i :60051 -i :60052 -i :60053
```

Kill any leftover `python` peer processes if ports stay bound.

---

## 5. Insight (optional)

**Terminal — Insight**

```bash
python scripts/run_llm.py
```

Requires `.env` with `LUCKYSTONKS_TRADING_ADDR` pointing at a peer that has trades (e.g. `127.0.0.1:50051`). vLLM/ngrok optional for non-template answers.

---

## Ports

| Service | Port |
|---------|------|
| Trading single / peer 0 | 50051 |
| Trading peer 1 | 50052 |
| Trading peer 2 | 50053 |
| Raft peer 0 / 1 / 2 | 60051 / 60052 / 60053 |
| Insight | 50070 |

Persistence: `data/runtime/state-peer{N}.json`, `data/runtime/raft-peer{N}.json`

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Connection refused | Start server or all three peers |
| `cli demo` fails on cluster | Use menu **5** or `order` |
| `replication failed` | Need 2 of 3 peers up; restart missing peer |
| `NOT_LEADER;trading=...` | CLI should retry; or use port in hint |
| After admin reset | Log in again |
| Dead peer port | Do not use that `--port` until peer is restarted |
