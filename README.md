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

Leave that terminal running. In a second terminal, start Insight with the same
model identifier and then start the repo's gRPC server:

```bash
cd "/Users/vedpahune/Downloads/luckystonks-main 2"
source .venv/bin/activate
export PYTHONPATH=.
export LUCKYSTONKS_VLLM_MODEL="Qwen/Qwen3-0.6B"
python scripts/run_llm.py
```

`LUCKYSTONKS_VLLM_MODEL` must exactly match the model supplied to `vllm serve`.
If the model, vLLM, or trading server is unavailable, Insight stays up and
returns a clearly labelled deterministic trade-tape fallback. If your Trading
server requires authentication for `Get TRADES`, also set
`LUCKYSTONKS_TRADING_READ_TOKEN` to its read-only service token before starting
Insight.

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
```

# License

The MIT License (MIT)

Copyright (c) 2026 Pratham Shah, Ved Pahune, Vidhu Kant Sharma

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
