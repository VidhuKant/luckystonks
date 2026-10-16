# LuckyStonks — Run guide (faculty / evaluator)

**Model:** `Qwen/Qwen3-0.6B` on a teammate’s machine via **ngrok**. Your machine runs **Trading**, **Insight**, and the **CLI** only.

---

## Before you start (team)

vLLM + ngrok must be running. You need the ngrok **`/v1`** base URL and model id `Qwen/Qwen3-0.6B` in `.env` (see below).

---

## Accounts

| Username | Password | Role / notes |
|----------|----------|----------------|
| `ved` | `ved` | ₹500000 + RELIANCE/TCS/HDFCBANK |
| `pratham` | `pratham` | ₹500000 + INFY/WIPRO/TATAMOTORS |
| `vidhu` | `vidhu` | ₹500000 + BHARTIARTL/ITC/SBIN |
| `admin` | `admin` | admin; menu item 6 = all portfolios |

**Interactive CLI:** `python -m luckystonks.client.cli` → login once → menu (portfolio, orders, book, trades, place order). **L** = logout (gRPC `Logout`), **Q** = quit.

**Script CLI:** `demo`, `view`, and `order` still login per command (`view ved ved PORTFOLIO`).

---

## One-time setup

```bash
git clone https://github.com/VidhuKant/luckystonks.git
cd luckystonks
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x scripts/gen_proto.sh
./scripts/gen_proto.sh
```

`.env` in repo root:

```env
LUCKYSTONKS_TRADING_READ_TOKEN=local-insight-read-token
LUCKYSTONKS_TRADING_ADDR=127.0.0.1:50051
LUCKYSTONKS_VLLM_BASE_URL=https://YOUR-SUBDOMAIN.ngrok-free.dev/v1
LUCKYSTONKS_VLLM_MODEL=Qwen/Qwen3-0.6B
```

```bash
pytest -q
```

---

## Run order (three terminals)

Each terminal:

```bash
cd luckystonks
source .venv/bin/activate
```

**Terminal 1 — Trading**

```bash
python scripts/run_trading_server.py
```

**Terminal 2 — Insight**

```bash
python scripts/run_llm.py
```

**Terminal 3 — Client**

Interactive:

```bash
python -m luckystonks.client.cli
```

Or scripted demo:

```bash
python -m luckystonks.client.cli demo
python -m luckystonks.client.cli view pratham pratham TRADES
```

**GetInsight** (after demo, terminals 1–2 up):

```bash
python <<'PY'
import grpc
from luckystonks.pb import llm_pb2, llm_pb2_grpc
stub = llm_pb2_grpc.InsightStub(grpc.insecure_channel("127.0.0.1:50070"))
print(stub.GetInsight(
    llm_pb2.GetInsightRequest(request_id="1", query="Summarize recent market activity.", context=""),
    timeout=120,
).answer)
PY
```

---

## Ports

| Service | Port | Command |
|---------|------|---------|
| Trading (single node) | 50051 | `python scripts/run_trading_server.py` |
| Trading peers | 50051 / 50052 / 50053 | `python scripts/run_trading_peer.py 0|1|2` |
| Raft peers | 60051 / 60052 / 60053 | same peer processes |
| Insight | 50070 | `python scripts/run_llm.py` |
| vLLM | ngrok | teammate’s host |

---

## Raft cluster (M2)

**Three peers:** run `run_trading_peer.py` with `0`, `1`, and `2` in separate terminals. Each peer stores:

- `data/runtime/state-peer{N}.json` — market engine snapshot  
- `data/runtime/raft-peer{N}.json` — Raft term + log  

**Writes (orders, admin reset)** go through the **Raft leader**. Followers return `NOT_LEADER;trading=host:port`. The interactive CLI re-logins on the leader and retries.

**Reads** (`Get` portfolio, book, trades, admin views) work on any peer once it has applied committed entries.

**Kill-leader demo:** see [scripts/demo_raft_kill_leader.md](scripts/demo_raft_kill_leader.md).

Single-node dev (no Raft): `run_trading_server.py` (`RAFT_ENABLED=0` default).

**Sessions:** Login is per trading peer. After `NOT_LEADER`, the CLI re-logins on the leader automatically for orders/admin reset.

**Insight:** Set `LUCKYSTONKS_TRADING_ADDR` to any peer that has applied trades (e.g. `127.0.0.1:50051`). The read token only allows `Get TRADES`.

**Leader replication:** Uses Raft-style `nextIndex` backtracking and same-term commit before applying orders.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Connection refused (CLI) | Start `run_trading_server.py` or peers 0–2 |
| `NOT_LEADER;trading=...` | CLI retries on leader; or connect to that port and log in |
| GetInsight refused | Start `run_llm.py` |
| Empty insight / no trades | Run trades on cluster; point Insight addr at a peer |
| Template-only LLM text | Check ngrok URL and vLLM in `.env` |
