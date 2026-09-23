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
echo "Generated luckystonks/pb/*_pb2.py"
