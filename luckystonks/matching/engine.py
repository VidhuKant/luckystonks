"""In-memory matching engine; all state changes go through apply() later."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from luckystonks.matching.models import Book, Command, Result, Trade, User


class Engine:
    """Owns users, books, trades, and idempotency by client_request_id."""

    def __init__(self) -> None:
        self.users: Dict[str, User] = {}
        self.books: Dict[str, Book] = {}
        self.trades: List[Trade] = []
        self._next_order_id: int = 1
        self._next_trade_id: int = 1
        self._next_seq: int = 1
        self.results_by_request: Dict[str, Result] = {}

    def seed_demo_users(self) -> None:
        """Load Bob (with AAPL) and Alice (with cash) for the CLI demo."""
        raise NotImplementedError

    def apply(self, command: Command) -> Result:
        """Apply one command: match, rest, or reject; record trades and balances."""
        raise NotImplementedError

    def snapshot(self, view_type: str, user_id: Optional[str] = None) -> Any:
        """Read-only view for Get (portfolio, book, trades, etc.)."""
        raise NotImplementedError

    def _book_for(self, symbol: str) -> Book:
        """Return (or create) the order book for a symbol."""
        raise NotImplementedError

    def _try_match(self, symbol: str) -> None:
        """Match best bid and ask while prices cross; append Trade rows."""
        raise NotImplementedError
