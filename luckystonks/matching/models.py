from dataclasses import dataclass, field
from typing import Literal

Side = Literal["BUY", "SELL"]


@dataclass
class User:
    user_id: str = ""
    password: str = ""
    cash: int = 0
    shares: dict[str, int] = field(default_factory=dict)


@dataclass
class Order:
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
    symbol: str
    bids: list[Order] = field(default_factory=list)
    asks: list[Order] = field(default_factory=list)

    def add(self, order: Order) -> None:
        if order.side == "BUY":
            self.bids.append(order)
            self.bids.sort(key=lambda o: (-o.price, o.seq))
        elif order.side == "SELL":
            self.asks.append(order)
            self.asks.sort(key=lambda o: (o.price, o.seq))

    def best_bid(self) -> Order | None:
        return self.bids[0] if self.bids else None

    def best_ask(self) -> Order | None:
        return self.asks[0] if self.asks else None

    def remove_if_done(self, order: Order) -> None:
        if order.remaining_qty != 0:
            return
        if order.side == "BUY":
            self.bids = [
                curr_orders
                for curr_orders in self.bids
                if curr_orders.order_id != order.order_id
            ]
        elif order.side == "SELL":
            self.asks = [
                curr_orders
                for curr_orders in self.asks
                if curr_orders.order_id != order.order_id
            ]


@dataclass
class Command:
    client_request_id: str
    user_id: str
    side: Side
    symbol: str
    price: int
    qty: int


@dataclass
class Result:
    status: str
    order_id: int | None = None
    filled_qty: int = 0
    message: str = ""
