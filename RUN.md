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
| Trading | 50051 | `python scripts/run_trading_server.py` |
| Insight | 50070 | `python scripts/run_llm.py` |
| vLLM | ngrok | teammate’s host |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Connection refused (CLI) | Start `run_trading_server.py` |
| GetInsight refused | Start `run_llm.py` |
| Empty insight / no trades | Run `demo` after restarting trading |
| Template-only LLM text | Check ngrok URL and vLLM in `.env` |
