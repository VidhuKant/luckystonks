"""Command-line client for the Trading gRPC service."""

from __future__ import annotations

import argparse
import json
import uuid
from typing import Any

import grpc

from luckystonks.pb import trading_pb2, trading_pb2_grpc


def connect(host: str = "127.0.0.1", port: int = 50051) -> Any:
    """Create a Trading gRPC stub."""
    return trading_pb2_grpc.TradingStub(grpc.insecure_channel(f"{host}:{port}"))


def login(stub: Any, username: str, password: str) -> str:
    """Authenticate a user and return the session token."""
    reply = stub.Login(
        trading_pb2.LoginRequest(username=username, password=password), timeout=5
    )
    if reply.status != "OK":
        raise RuntimeError(f"login failed for {username}")
    return reply.token


def post(stub: Any, token: str, post_type: str, data: bytes) -> tuple[str, str]:
    """Submit a Trading write request and return its status."""
    reply = stub.Post(
        trading_pb2.PostRequest(token=token, type=post_type, data=data), timeout=5
    )
    if reply.status == "ERR":
        raise RuntimeError(reply.detail)
    return reply.status, reply.detail


def get(stub: Any, token: str, get_type: str, params: str = "") -> list[dict[str, Any]]:
    """Retrieve a Trading read view."""
    reply = stub.Get(
        trading_pb2.GetRequest(token=token, type=get_type, params=params), timeout=5
    )
    if reply.status != "OK":
        raise RuntimeError(f"get {get_type} failed")
    return [json.loads(item.data.decode("utf-8")) for item in reply.items]


def run_demo(stub: Any) -> list[dict[str, Any]]:
    """Place the guide's Bob sell followed by Alice buy demonstration."""
    bob_token = login(stub, "bob", "bob")
    sell_status, _ = post(
        stub,
        bob_token,
        "ORDER",
        _order_payload("SELL", "AAPL", 150, 10),
    )
    if sell_status != "RESTING":
        raise RuntimeError(f"expected Bob's sell to rest, received {sell_status}")

    alice_token = login(stub, "alice", "alice")
    buy_status, _ = post(
        stub,
        alice_token,
        "ORDER",
        _order_payload("BUY", "AAPL", 150, 10),
    )
    if buy_status != "FILLED":
        raise RuntimeError(f"expected Alice's buy to fill, received {buy_status}")

    print(f"Bob SELL AAPL: {sell_status}")
    print(f"Alice BUY AAPL: {buy_status}")
    return get(stub, alice_token, "TRADES")


def submit_order(
    stub: Any, username: str, password: str, side: str, symbol: str, price: int, qty: int
) -> tuple[str, str]:
    """Log in and place a limit order."""
    token = login(stub, username, password)
    return post(
        stub,
        token,
        "ORDER",
        _order_payload(side, symbol, price, qty),
    )


def _order_payload(side: str, symbol: str, price: int, qty: int) -> bytes:
    return json.dumps(
        {
            "client_request_id": str(uuid.uuid4()),
            "side": side.upper(),
            "symbol": symbol.upper(),
            "price": price,
            "qty": qty,
        }
    ).encode("utf-8")


def main() -> None:
    """Run the Trading demonstration or manual client commands."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=50051, type=int)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo")

    order_parser = commands.add_parser("order")
    order_parser.add_argument("username")
    order_parser.add_argument("password")
    order_parser.add_argument("side", choices=["BUY", "SELL", "buy", "sell"])
    order_parser.add_argument("symbol")
    order_parser.add_argument("price", type=int)
    order_parser.add_argument("qty", type=int)

    view_parser = commands.add_parser("view")
    view_parser.add_argument("username")
    view_parser.add_argument("password")
    view_parser.add_argument("type", choices=["TRADES", "PORTFOLIO", "BOOK", "ORDERS"])
    view_parser.add_argument("--symbol", default="")
    args = parser.parse_args()
    stub = connect(args.host, args.port)

    if args.command == "demo":
        print(json.dumps(run_demo(stub), indent=2))
    elif args.command == "order":
        status, detail = submit_order(
            stub, args.username, args.password, args.side, args.symbol, args.price, args.qty
        )
        print(json.dumps({"status": status, "detail": detail}))
    else:
        token = login(stub, args.username, args.password)
        print(json.dumps(get(stub, token, args.type, args.symbol), indent=2))


if __name__ == "__main__":
    main()
