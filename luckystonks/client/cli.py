"""Command-line client stub (gRPC wiring added later)."""

from __future__ import annotations

from typing import Any, Optional


def connect(host: str = "127.0.0.1", port: int = 50051) -> Any:
    """Open a gRPC channel to the trading server."""
    raise NotImplementedError


def login(stub: Any, username: str, password: str) -> str:
    """Call Login and return session token."""
    raise NotImplementedError


def post(stub: Any, token: str, post_type: str, data: bytes) -> str:
    """Call Post (place order, etc.) and return status."""
    raise NotImplementedError


def get(stub: Any, token: str, get_type: str, params: str = "") -> Any:
    """Call Get and return retrieved items."""
    raise NotImplementedError


def main() -> None:
    """Parse argv and run an interactive or one-shot CLI session."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
