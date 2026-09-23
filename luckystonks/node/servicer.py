"""gRPC Trading servicer — phone, not the brain; delegates to Engine.apply later."""

from __future__ import annotations

from typing import Any, Dict

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command


class TradingServicer:
    """Handles Login, Post, and Get RPCs for the trading service."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.sessions: Dict[str, str] = {}

    def Login(self, username: str, password: str) -> tuple[str, str]:
        """Authenticate and return (status, token)."""
        raise NotImplementedError

    def Post(self, token: str, post_type: str, data: bytes) -> tuple[str, str]:
        """Validate session, build Command, call engine.apply, return status."""
        raise NotImplementedError

    def Get(self, token: str, get_type: str, params: str) -> tuple[str, list]:
        """Validate session and return snapshot data for the requested view."""
        raise NotImplementedError

    def _user_id_for(self, token: str) -> str:
        """Map session token to user_id."""
        raise NotImplementedError

    def _command_from_post(self, user_id: str, post_type: str, data: bytes) -> Command:
        """Parse Post payload into a Command for the engine."""
        raise NotImplementedError
