#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:?Usage: ./scripts/run_vllm.sh <HuggingFace-model-id-or-local-model-path>}"
exec vllm serve "$MODEL" --host 127.0.0.1 --port 8000
