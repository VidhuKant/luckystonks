# LuckyStonks

The only 'Laxmi Chit Fund' you need !!!

<img src="https://raw.githubusercontent.com/VidhuKant/luckystonks/refs/heads/main/luckysharma.gif" width="400">

![Lucky Sharma](luckysharma.png)

## Project layout (skeleton)

## Ports

| Service | Port |
|---------|------|
| Trading gRPC | `50051` |
| Insight gRPC (this repo’s LLM node) | `50070` |
| vLLM HTTP (external; not pip-installed here) | `8000` |
| Web HTTP (optional, last) | `8765` |

Insight path: client → `GetInsight` on `:50070` → (later) HTTP to vLLM on `:8000`. See [INIT.md](INIT.md).

## Local LLM setup (vLLM only on this laptop)

The repository does **not** install vLLM. Keep it in its own environment: this
keeps large ML packages separate from the normal project dependencies. The
Insight server only connects to `http://127.0.0.1:8000/v1`; no client or web
page connects to vLLM directly.

This computer is Apple Silicon. The supported local route is the vLLM-Metal
plugin, which needs native arm64 Python 3.12 and macOS 15 or newer. Follow the
[official vLLM-Metal installation instructions](https://docs.vllm.ai/projects/vllm-metal/en/stable/installation/), then run:

```bash
source ~/.venv-vllm-metal/bin/activate
cd "/Users/vedpahune/Downloads/luckystonks-main 2"
./scripts/run_vllm.sh Qwen/Qwen3-0.6B
```

Leave that terminal running. In a second terminal, start the Trading service
with the guide's seeded Alice and Bob accounts:

```bash
cd "/Users/vedpahune/Downloads/luckystonks-main 2"
source .venv/bin/activate
export PYTHONPATH=.
export LUCKYSTONKS_TRADING_READ_TOKEN="local-insight-read-token"
python scripts/run_single.py
```

In a third terminal, run the guide's Bob-sell then Alice-buy demo. It prints
`RESTING`, then `FILLED`, and creates one AAPL trade:

```bash
cd "/Users/vedpahune/Downloads/luckystonks-main 2"
source .venv/bin/activate
export PYTHONPATH=.
python -m luckystonks.client.cli
```

You can also place your own order or inspect the current state:

```bash
python -m luckystonks.client.cli order carol carol SELL TSLA 250 5
python -m luckystonks.client.cli view alice alice PORTFOLIO
python -m luckystonks.client.cli view alice alice BOOK --symbol AAPL
python -m luckystonks.client.cli view alice alice TRADES
```

To use your own starting accounts, set `LUCKYSTONKS_SEED_FILE` before starting
Trading. The provided [data/seed_users.json](data/seed_users.json) is an example.
It loads users, cash, and share ownership only; all trades must still be made
through the matching engine.

```bash
export LUCKYSTONKS_SEED_FILE="$(pwd)/data/seed_users.json"
python scripts/run_single.py
```

In a fourth terminal, start Insight with the same model identifier and read-only
Trading token:

```bash
cd "/Users/vedpahune/Downloads/luckystonks-main 2"
source .venv/bin/activate
export PYTHONPATH=.
export LUCKYSTONKS_VLLM_MODEL="Qwen/Qwen3-0.6B"
export LUCKYSTONKS_TRADING_READ_TOKEN="local-insight-read-token"
python scripts/run_llm.py
```

`LUCKYSTONKS_VLLM_MODEL` must exactly match the model supplied to `vllm serve`.
If the model, vLLM, or Trading service is unavailable, Insight stays up and
returns a deterministic fallback. Set `LUCKYSTONKS_TRADING_READ_TOKEN` to a
different shared value in both services before starting them if needed.

The launcher uses an 8,192-token context limit, suitable for this laptop's
available memory. Override it only when sufficient memory is available:

```bash
export LUCKYSTONKS_VLLM_MAX_MODEL_LEN=4096
```

## Quick setup

```bash
cd /Users/prathamshah/BITS/AOS/Project/luckystonks
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x scripts/gen_proto.sh
./scripts/gen_proto.sh
export PYTHONPATH=.
python -c "from luckystonks.matching.engine import Engine; print('ok')"
pytest -q
```

# License

The MIT License (MIT)

Copyright (c) 2026 Pratham Shah, Ved Pahune, Vidhu Kant Sharma

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
