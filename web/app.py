"""HTTP front-end stubs (optional, phase 1 last).

Trading routes forward to gRPC Trading on localhost:50051.

GET /insight must call gRPC GetInsight on localhost:50070 (Insight node).
Never proxy browsers or CLI to vLLM HTTP on :8000.

Documented path:
  client → GET /insight (:8765) → gRPC GetInsight (:50070)
  → (later, inside Insight process) HTTP vLLM (:8000)
"""

from __future__ import annotations

from typing import Any

WEB_HOST = "0.0.0.0"
WEB_PORT = 8765
INSIGHT_GRPC_ADDR = "localhost:50070"
TRADING_GRPC_ADDR = "localhost:50051"
# vLLM is external; web must not use this URL.
VLLM_HTTP_ADDR = "127.0.0.1:8000"


def login_http(username: str, password: str) -> Any:
    """HTTP login; forwards to gRPC Login on TRADING_GRPC_ADDR."""
    raise NotImplementedError


def post_order_http(token: str, body: bytes) -> Any:
    """HTTP order post; forwards to gRPC Post on TRADING_GRPC_ADDR."""
    raise NotImplementedError


def get_view_http(token: str, view_type: str, params: str = "") -> Any:
    """HTTP read; forwards to gRPC Get on TRADING_GRPC_ADDR."""
    raise NotImplementedError


def get_insight_http(query: str, context: str = "") -> Any:
    """GET /insight handler: gRPC GetInsight on INSIGHT_GRPC_ADDR only, never VLLM_HTTP_ADDR."""
    raise NotImplementedError


def main() -> None:
    """Run HTTP server on WEB_HOST:WEB_PORT (later)."""
    raise NotImplementedError
