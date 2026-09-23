"""Data shapes for users, orders, books, trades, and command results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

Side = Literal["BUY", "SELL"]


@dataclass
class User:
    """A trader account: cash on hand and owned shares per symbol."""

    user_id: str
    password: str
    cash: int
    shares: Dict[str, int] = field(default_factory=dict)


@dataclass
class Order:
    """A limit order resting on or moving through the book."""

    order_id: int
    user_id: str
    client_request_id: str
    side: Side
    symbol: str
    price: int
    qty: int
    remaining_qty: int
    seq: int


@dataclass
class Trade:
    """One executed fill between a buy and a sell."""

    trade_id: int
    symbol: str
    price: int
    qty: int
    buy_order_id: int
    sell_order_id: int
    buyer_id: str
    seller_id: str


@dataclass
class Book:
    """Per-symbol bid and ask queues (limit order book)."""

    symbol: str
    bids: List[Order] = field(default_factory=list)
    asks: List[Order] = field(default_factory=list)

    def add(self, order: Order) -> None:
        """Insert a resting order into bids or asks in price-time order."""
        raise NotImplementedError

    def best_bid(self) -> Optional[Order]:
        """Return the highest-priced buy still waiting, if any."""
        raise NotImplementedError

    def best_ask(self) -> Optional[Order]:
        """Return the lowest-priced sell still waiting, if any."""
        raise NotImplementedError

    def remove_if_done(self, order: Order) -> None:
        """Remove an order from the book when remaining_qty reaches zero."""
        raise NotImplementedError


@dataclass
class Command:
    """One mutating action applied to the engine (e.g. place order)."""

    client_request_id: str
    user_id: str
    side: Side
    symbol: str
    price: int
    qty: int


@dataclass
class Result:
    """Outcome returned to the caller after apply (RESTING, FILLED, PARTIAL, REJECTED)."""

    status: str
    order_id: Optional[int] = None
    filled_qty: int = 0
    message: str = ""
