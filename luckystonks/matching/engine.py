from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from luckystonks.matching.models import Book, Command, Result, Trade, User, Order

from copy import deepcopy

class Engine:
    """Owns the users, books, trades, and idempotency of the client by usning client's req id """

    def __init__(self) -> None:
        self.users: Dict[str, User] = {}
        self.books: Dict[str, Book] = {}
        self.trades: List[Trade] = []
        self._next_order_id: int = 1
        self._next_trade_id: int = 1
        self._next_seq: int = 1
        self.results_by_request: Dict[str, Result] = {}

    def seed_demo_users(self) -> None:
        self.users["bob"] = User("bob", "bob", cash=0, shares={"AAPL": 10})
        self.users["alice"] = User("alice", "alice", cash=10_000, shares={})

    def load_seed_data(self, path: str | Path) -> None:
        """Load initial user accounts from a JSON seed file."""
        with Path(path).open(encoding="utf-8") as seed_file:
            payload = json.load(seed_file)
        users = payload.get("users")
        if not isinstance(users, list) or not users:
            raise ValueError("seed data must contain a non-empty users list")

        loaded_users: Dict[str, User] = {}
        for record in users:
            if not isinstance(record, dict):
                raise ValueError("each seed user must be an object")
            user_id = record.get("user_id")
            password = record.get("password")
            cash = record.get("cash", 0)
            shares = record.get("shares", {})
            if not isinstance(user_id, str) or not user_id or not isinstance(password, str):
                raise ValueError("each seed user requires user_id and password")
            if user_id in loaded_users or not isinstance(cash, int) or cash < 0:
                raise ValueError("seed users must have unique ids and non-negative cash")
            if not isinstance(shares, dict) or any(
                not isinstance(symbol, str) or not isinstance(qty, int) or qty < 0
                for symbol, qty in shares.items()
            ):
                raise ValueError("seed shares must map symbols to non-negative integers")
            loaded_users[user_id] = User(user_id, password, cash, dict(shares))
        self.users = loaded_users

    def apply(self, command: Command) -> Result:
        """validate order and then send for further processing """
        if command.client_request_id in self.results_by_request:
            return deepcopy(self.results_by_request[command.client_request_id])

        if command.price <= 0 or command.qty <= 0 or not command.symbol:
            result = Result(status="REJECTED", message="price, quantity, and symbol must be valid")
            self.results_by_request[command.client_request_id] = result
            return deepcopy(result)

        user = self.users.get(command.user_id)
        if user is None:
            result = Result(status="REJECTED", message="User not found")
            self.results_by_request[command.client_request_id] = result
            return deepcopy(result)

        # if user is a seller
        if command.side == "SELL":

            if user.shares.get(command.symbol,0)< command.qty:
                result = Result(status="REJECTED",message="You don't have enough shares to sell")
                self.results_by_request[command.client_request_id] = result
                return deepcopy(result)
        elif command.side == "BUY":
            if user.cash < command.price*command.qty:
                result = Result(status="REJECTED", message="You don't have enough cash to buy")
                self.results_by_request[command.client_request_id] = result
                return deepcopy(result)
        else:
            result = Result(status="REJECTED", message="Invalid side")
            self.results_by_request[command.client_request_id] = result
            return deepcopy(result)

        order = Order(
            order_id=self._next_order_id,
            user_id=command.user_id,
            client_request_id=command.client_request_id,
            side=command.side,
            symbol=command.symbol,
            price=command.price,
            qty=command.qty,
            remaining_qty=command.qty,
            seq=self._next_seq,
        )
        self._next_order_id += 1
        self._next_seq += 1

        book = self._book_for(command.symbol)


        if command.side == "BUY":
            while order.remaining_qty > 0:
                ask = book.best_ask()
                if ask is None or ask.price > order.price:
                    break
                real_qty = min(order.remaining_qty, ask.remaining_qty)
                self._execute_fill(
                    symbol=command.symbol,
                    price=ask.price,
                    qty=real_qty,
                    buy_order=order,
                    sell_order=ask,
                )
        elif command.side == "SELL":
            while order.remaining_qty > 0:
                bid = book.best_bid()
                if bid is None or bid.price < order.price:
                    break
                real_qty = min(order.remaining_qty, bid.remaining_qty)
                self._execute_fill(
                    symbol=command.symbol,
                    price=bid.price,
                    qty=real_qty,
                    buy_order=bid,
                    sell_order=order,
                )

        filled_qty = order.qty - order.remaining_qty
        if order.remaining_qty > 0:
            book.add(order)

        msg = ""
        if filled_qty == 0:
            status = "RESTING"
            msg = "Order is resting not filled"
        elif order.remaining_qty == 0:
            status = "FILLED"
            msg = "Order is fully filled"
        else:
            status = "PARTIAL"
            msg = "Order is partially filled"

        result = Result(
            status=status,
            order_id=order.order_id,
            filled_qty=filled_qty,
            message=msg,
        )

        self.results_by_request[command.client_request_id] = result
        return deepcopy(result)

    def snapshot(self, view_type: str, user_id: Optional[str] = None, params: str = "") -> Any:
        """ read only view of engine's state"""
        if view_type == "TRADES":
            return list(self.trades)
        elif view_type == "PORTFOLIO":
            user = self.users.get(user_id or "")
            if user is None:
                return None
            return {"cash": user.cash, "shares": dict(user.shares)}
        elif view_type == "BOOK":
            books = [params] if params else sorted(self.books)
            return {
                symbol: {
                    "bids": [self._order_view(order) for order in self.books.get(symbol, Book(symbol)).bids],
                    "asks": [self._order_view(order) for order in self.books.get(symbol, Book(symbol)).asks],
                }
                for symbol in books
            }
        elif view_type == "ORDERS":
            return [
                self._order_view(order)
                for book in self.books.values()
                for order in [*book.bids, *book.asks]
                if order.user_id == user_id
            ]
        return None

    @staticmethod
    def _order_view(order: Order) -> dict[str, Any]:
        return {
            "order_id": order.order_id,
            "side": order.side,
            "symbol": order.symbol,
            "price": order.price,
            "qty": order.qty,
            "remaining_qty": order.remaining_qty,
        }

    def _book_for(self, symbol: str) -> Book:
        """to get the symbol of company/firm ."""
        if symbol not in self.books:
            self.books[symbol] = Book(symbol)
        return self.books[symbol]

    def _execute_fill(self,*,symbol:str,price:int, qty:int,
                      buy_order:Order, sell_order:Order,) -> None:
        """ execute trade"""
        buyer = self.users[buy_order.user_id]
        seller = self.users[sell_order.user_id]
        cost = price*qty

        buyer.cash -= cost
        buyer.shares[symbol] = buyer.shares.get(symbol,0)+qty

        seller.cash += cost
        seller.shares[symbol] = seller.shares.get(symbol,0)-qty

        buy_order.remaining_qty -= qty
        sell_order.remaining_qty -= qty

        self.trades.append(
            Trade(
                trade_id=self._next_trade_id,
                symbol=symbol,
                price=price,
                qty=qty,
                buy_order_id=buy_order.order_id,
                sell_order_id=sell_order.order_id,
                buyer_id=buyer.user_id,
                seller_id=seller.user_id,
            )
        )
        self._next_trade_id += 1

        book = self._book_for(symbol)
        book.remove_if_done(buy_order)
        book.remove_if_done(sell_order)
