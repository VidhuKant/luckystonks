# LuckyStonks

The only 'Laxmi Chit Fund' you need !!!

<img src="https://raw.githubusercontent.com/VidhuKant/luckystonks/refs/heads/main/luckysharma.gif" width="400">

![Lucky Sharma](luckysharma.png)

## Ports

| Service | Port |
|---------|------|
| Trading gRPC | `50051` |
| Insight gRPC | `50070` |
| vLLM HTTP (external) | `8000` or ngrok `/v1` |
| Web HTTP (optional) | `8765` |

Full steps: [RUN.md](RUN.md).

## Quick setup

```bash
cd luckystonks
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x scripts/gen_proto.sh
./scripts/gen_proto.sh
pytest -q
```

Optional `.env` (loaded by server scripts): `LUCKYSTONKS_TRADING_READ_TOKEN`, `LUCKYSTONKS_VLLM_BASE_URL`, `LUCKYSTONKS_VLLM_MODEL`. See [RUN.md](RUN.md).

## Run

Terminal 1:

```bash
python scripts/run_trading_server.py
```

Terminal 2:

```bash
python scripts/run_llm.py
```

Terminal 3 — interactive client (login once, menu, **L** logout):

```bash
python -m luckystonks.client.cli
```

Accounts: `ved`/`ved`, `pratham`/`pratham`, `vidhu`/`vidhu`, `admin`/`admin`. Trading loads [data/seed_users.json](data/seed_users.json) on startup (override with `LUCKYSTONKS_SEED_FILE`).

Scripted demo:

```bash
python -m luckystonks.client.cli demo
python -m luckystonks.client.cli view ved ved PORTFOLIO
python -m luckystonks.client.cli order vidhu vidhu BUY RELIANCE 2500 5
```

# License

The MIT License (MIT)

Copyright (c) 2026 Pratham Shah, Ved Pahune, Vidhu Kant Sharma

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
