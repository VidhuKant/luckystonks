"""Data shapes for users, orders, books, trades, and command results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

Side = Literal["BUY", "SELL"]

@dataclass
class User:
    """A trader's account """

    user_id: str = ""
    password: str = ""
    cash: int = 0
    shares: Dict[str, int] = field(default_factory=dict)


@dataclass
class Order:
    """Order book's orders"""

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
    """Trade structure """

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
    """Actual order book """

    symbol: str
    bids: List[Order] = field(default_factory=list)
    asks: List[Order] = field(default_factory=list)

    def add(self, order: Order) -> None:
        if order.side == "BUY":
            self.bids.append(order);
            self.bids.sort(key=lambda o: (-o.price, o.seq));
        elif order.side == "SELL":
            self.asks.append(order);
            self.asks.sort(key=lambda o: (o.price, o.seq));

    def best_bid(self) -> Optional[Order]:
        return self.bids[0] if self.bids else None


    def best_ask(self) -> Optional[Order]:
        return self.asks[0] if self.asks else None

    def remove_if_done(self, order: Order) -> None:
        if order.remaining_qty !=0:
            return
        if order.side == "BUY":
            self.bids = [curr_orders for curr_orders in self.bids if curr_orders.order_id != order.order_id]
        elif order.side == "SELL":
            self.asks = [curr_orders for curr_orders in self.asks if curr_orders.order_id != order.order_id]

@dataclass
class Command:
    """class to send req to matching engine """

    client_request_id: str
    user_id: str
    side: Side
    symbol: str
    price: int
    qty: int


@dataclass
class Result:
    """ output of matching engine"""

    status: str
    order_id: Optional[int] = None
    filled_qty: int = 0
    message: str = ""
