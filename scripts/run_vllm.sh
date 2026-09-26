#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:?Usage: ./scripts/run_vllm.sh <HuggingFace-model-id-or-local-model-path>}"
MAX_MODEL_LEN="${LUCKYSTONKS_VLLM_MAX_MODEL_LEN:-8192}"
exec vllm serve "$MODEL" --host 127.0.0.1 --port 8000 --max-model-len "$MAX_MODEL_LEN"
