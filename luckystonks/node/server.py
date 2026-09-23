"""gRPC server bootstrap for the trading node."""

from __future__ import annotations

from luckystonks.matching.engine import Engine
from luckystonks.node.servicer import TradingServicer

TRADING_HOST = "0.0.0.0"
TRADING_PORT = 50051


def serve(engine: Engine | None = None) -> None:
    """Create TradingServicer and listen on TRADING_HOST:TRADING_PORT (later)."""
    raise NotImplementedError


def main() -> None:
    """CLI entry: start trading gRPC server."""
    raise NotImplementedError
