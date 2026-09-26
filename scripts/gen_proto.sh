#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p luckystonks/pb
python -m grpc_tools.protoc \
  -I proto \
  --python_out=luckystonks/pb \
  --grpc_python_out=luckystonks/pb \
  proto/trading.proto \
  proto/llm.proto \
  proto/raft.proto
sed -i.bak -E 's/^import (trading_pb2|llm_pb2|raft_pb2) as /from luckystonks.pb import \1 as /' luckystonks/pb/*_pb2_grpc.py
rm -f luckystonks/pb/*_pb2_grpc.py.bak
echo "Generated luckystonks/pb/*_pb2.py"
