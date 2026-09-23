# LuckyStonks

The only 'Laxmi Chit Fund' you need !!!

<img src="https://raw.githubusercontent.com/VidhuKant/luckystonks/refs/heads/main/luckysharma.gif" width="400">

![Lucky Sharma](luckysharma.png)

## Project layout (skeleton)

## Ports

| Service | Port |
|---------|------|
| Trading gRPC | `50051` |
| LLM Insight gRPC | `50070` |
| Web HTTP (optional, last) | `8765` |

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
