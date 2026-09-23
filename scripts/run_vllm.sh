#!/usr/bin/env bash
# Example only — vLLM runs outside this repo (not in requirements.txt).
#
# Typical manual start (install vllm in another venv/machine):
#   vllm serve <model> --host 0.0.0.0 --port 8000
#
# Insight on :50070 will call http://127.0.0.1:8000/v1 later via complete_chat().
# Clients must never talk to :8000.

echo "This script does not start vLLM. Run vllm serve manually on port 8000 if needed." >&2
exit 1
