"""HTTP front-end stubs — forwards to trading (:50051) and insight (:50070) later."""

from __future__ import annotations

from typing import Any

WEB_HOST = "0.0.0.0"
WEB_PORT = 8765


def login_http(username: str, password: str) -> Any:
    """HTTP login handler; will forward to gRPC Login."""
    raise NotImplementedError


def post_order_http(token: str, body: bytes) -> Any:
    """HTTP order post; will forward to gRPC Post."""
    raise NotImplementedError


def get_view_http(token: str, view_type: str, params: str = "") -> Any:
    """HTTP read; will forward to gRPC Get."""
    raise NotImplementedError


def get_insight_http(query: str, context: str = "") -> Any:
    """HTTP insight; will forward to gRPC GetInsight on :50070."""
    raise NotImplementedError


def main() -> None:
    """Run a simple HTTP server on WEB_HOST:WEB_PORT (later)."""
    raise NotImplementedError
