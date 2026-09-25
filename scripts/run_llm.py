#!/usr/bin/env python3
"""Start the Insight gRPC server on :50070 (luckystonks LLM node in this repo).

Does not start vLLM. For a local inference server, use scripts/run_vllm.sh as a reminder only.
"""

from __future__ import annotations


def main() -> None:
    """Start Insight gRPC via luckystonks.llm.assistant.main (stub)."""
    from luckystonks.llm.assistant import main as serve_insight

    serve_insight()


if __name__ == "__main__":
    main()
