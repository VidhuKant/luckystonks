"""Insight gRPC service — reads trade tape only; never Post."""

from __future__ import annotations

from typing import Any, List

LLM_HOST = "0.0.0.0"
LLM_PORT = 50070


def fetch_tape(trading_stub: Any) -> List[Any]:
    """Call Get(TRADES) on the trading server to read recent fills."""
    raise NotImplementedError


def summarize(tape: List[Any], query: str, context: str) -> str:
    """Turn tape + query into text (LLM or template if no API key)."""
    raise NotImplementedError


def GetInsight(request_id: str, query: str, context: str) -> tuple[str, str]:
    """Handle GetInsight RPC: return (request_id, answer)."""
    raise NotImplementedError


def serve() -> None:
    """Listen on LLM_HOST:LLM_PORT for Insight gRPC (later)."""
    raise NotImplementedError


def main() -> None:
    """CLI entry for the insight server."""
    raise NotImplementedError
