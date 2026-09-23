"""Insight gRPC node (this repo).

Client path (document only until implemented):
  browser/CLI → web GET /insight or gRPC GetInsight on :50070
  → (later, inside this process) complete_chat HTTP to vLLM OpenAI API on :8000

Clients and web never call vLLM directly. vLLM is a separate process, not pip-installed here.
serve() starts Insight gRPC only; it does not start vLLM.
"""

from __future__ import annotations

from typing import Any, List

# Insight gRPC (this process)
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 50070

# Trading tape source (gRPC Get TRADES)
TRADING_ADDR = "localhost:50051"

# External vLLM (OpenAI-compatible HTTP) — comment/target only; not used in skeleton
INFER_BASE_URL = "http://127.0.0.1:8000/v1"
INFER_MODEL = ""


class InsightServicer:
    """gRPC servicer for proto/llm.proto service Insight."""

    def GetInsight(self, request: Any, context: Any) -> Any:
        """Client RPC: validate request, fetch tape, summarize, return GetInsightReply."""
        raise NotImplementedError


def fetch_tape(trading_stub: Any) -> List[Any]:
    """Call Trading.Get(TRADES) at TRADING_ADDR; read-only, never Post."""
    raise NotImplementedError


def complete_chat(messages: List[dict], model: str | None = None) -> str:
    """Internal only: POST to INFER_BASE_URL/chat/completions (vLLM on :8000) in a later phase."""
    raise NotImplementedError


def template_summary(tape: List[Any], query: str, context: str) -> str:
    """Fallback when vLLM is down or INFER_MODEL unset; numeric/template text from tape."""
    raise NotImplementedError


def summarize(tape: List[Any], query: str, context: str) -> str:
    """Build answer via complete_chat when vLLM is up, else template_summary."""
    raise NotImplementedError


def serve() -> None:
    """Bind DEFAULT_HOST:DEFAULT_PORT and run Insight gRPC; does not launch vLLM."""
    raise NotImplementedError


def main() -> None:
    """Entrypoint for scripts/run_llm.py — Insight gRPC server only."""
    raise NotImplementedError
