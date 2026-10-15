from __future__ import annotations

import argparse
import getpass
import json
import uuid
from dataclasses import dataclass
from typing import Any

import grpc

from luckystonks.pb import trading_pb2, trading_pb2_grpc


@dataclass
class Session:
    token: str
    user_id: str
    role: str


def connect(host: str = "127.0.0.1", port: int = 50051) -> Any:
    return trading_pb2_grpc.TradingStub(grpc.insecure_channel(f"{host}:{port}"))


def login(stub: Any, username: str, password: str) -> Session:
    reply = stub.Login(
        trading_pb2.LoginRequest(username=username, password=password), timeout=5
    )
    if reply.status != "OK":
        raise RuntimeError(f"login failed for {username}")
    return Session(token=reply.token, user_id=username, role=reply.role or "user")


def logout(stub: Any, token: str) -> None:
    reply = stub.Logout(trading_pb2.LogoutRequest(token=token), timeout=5)
    if reply.status != "OK":
        raise RuntimeError("logout failed")


def post(stub: Any, token: str, post_type: str, data: bytes) -> tuple[str, str]:
    reply = stub.Post(
        trading_pb2.PostRequest(token=token, type=post_type, data=data), timeout=5
    )
    if reply.status == "ERR":
        raise RuntimeError(reply.detail)
    return reply.status, reply.detail


def get(stub: Any, token: str, get_type: str, params: str = "") -> list[dict[str, Any]]:
    reply = stub.Get(
        trading_pb2.GetRequest(token=token, type=get_type, params=params), timeout=5
    )
    if reply.status != "OK":
        raise RuntimeError(f"get {get_type} failed")
    return [json.loads(item.data.decode("utf-8")) for item in reply.items]


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


def run_demo(stub: Any) -> list[dict[str, Any]]:
    ved = login(stub, "ved", "ved")
    sell_status, _ = post(stub, ved.token, "ORDER", _order_payload("SELL", "RELIANCE", 2450, 10))
    if sell_status != "RESTING":
        raise RuntimeError(f"expected Ved's sell to rest, received {sell_status}")

    pratham = login(stub, "pratham", "pratham")
    buy_status, _ = post(stub, pratham.token, "ORDER", _order_payload("BUY", "RELIANCE", 2450, 10))
    if buy_status != "FILLED":
        raise RuntimeError(f"expected Pratham's buy to fill, received {buy_status}")

    print(f"Ved SELL RELIANCE: {sell_status}")
    print(f"Pratham BUY RELIANCE: {buy_status}")
    return get(stub, pratham.token, "TRADES")


def submit_order(
    stub: Any, username: str, password: str, side: str, symbol: str, price: int, qty: int
) -> tuple[str, str]:
    session = login(stub, username, password)
    return post(stub, session.token, "ORDER", _order_payload(side, symbol, price, qty))


def _prompt_int(label: str) -> int:
    while True:
        raw = input(f"{label}: ").strip()
        try:
            return int(raw)
        except ValueError:
            print("Enter a whole number.")


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def run_interactive(stub: Any) -> None:
    while True:
        print("\n=== LuckyStonks Login ===")
        username = input("Username: ").strip()
        if not username:
            print("Bye.")
            return
        password = getpass.getpass("Password: ")
        try:
            session = login(stub, username, password)
        except RuntimeError as err:
            print(err)
            continue

        print(f"Logged in as {session.user_id} ({session.role})")

        while True:
            print("\n--- Menu ---")
            print("1) My portfolio (cash + shares)")
            print("2) My open orders")
            print("3) Order book (bids/asks)")
            print("4) Market trades (tape)")
            print("5) Place limit order")
            if session.role == "admin":
                print("6) [Admin] All users' portfolios")
                print("7) [Admin] Order log")
            print("L) Logout")
            print("Q) Quit program")
            choice = input("Choice: ").strip().lower()

            try:
                if choice == "1":
                    _print_json(get(stub, session.token, "PORTFOLIO"))
                elif choice == "2":
                    _print_json(get(stub, session.token, "ORDERS"))
                elif choice == "3":
                    symbol = input("Symbol (e.g. AAPL, empty=all): ").strip().upper()
                    _print_json(get(stub, session.token, "BOOK", symbol))
                elif choice == "4":
                    _print_json(get(stub, session.token, "TRADES"))
                elif choice == "5":
                    side = input("Side BUY or SELL: ").strip().upper()
                    symbol = input("Symbol: ").strip().upper()
                    price = _prompt_int("Limit price")
                    qty = _prompt_int("Quantity")
                    status, detail = post(
                        stub, session.token, "ORDER", _order_payload(side, symbol, price, qty)
                    )
                    _print_json({"status": status, "detail": detail})
                elif choice == "6" and session.role == "admin":
                    _print_json(get(stub, session.token, "ADMIN_PORTFOLIOS"))
                elif choice == "7" and session.role == "admin":
                    _print_json(get(stub, session.token, "ORDER_LOG"))
                elif choice == "l":
                    logout(stub, session.token)
                    print("Logged out.")
                    break
                elif choice == "q":
                    logout(stub, session.token)
                    print("Bye.")
                    return
                else:
                    print("Invalid choice.")
            except RuntimeError as err:
                print(f"Error: {err}")
                if "invalid session" in str(err).lower():
                    print("Session expired. Please log in again.")
                    break


def main() -> None:
    parser = argparse.ArgumentParser(description="LuckyStonks trading client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=50051, type=int)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("demo", help="Bob/Alice scripted demo")
    commands.add_parser("shell", help="Interactive menu (same as default)")

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
    view_parser.add_argument(
        "type",
        choices=["TRADES", "PORTFOLIO", "BOOK", "ORDERS", "ADMIN_PORTFOLIOS", "ORDER_LOG"],
    )
    view_parser.add_argument("--symbol", default="")

    args = parser.parse_args()
    stub = connect(args.host, args.port)
    command = args.command or "shell"

    if command == "demo":
        print(json.dumps(run_demo(stub), indent=2))
    elif command == "order":
        status, detail = submit_order(
            stub, args.username, args.password, args.side, args.symbol, args.price, args.qty
        )
        print(json.dumps({"status": status, "detail": detail}))
    elif command == "view":
        session = login(stub, args.username, args.password)
        print(json.dumps(get(stub, session.token, args.type, args.symbol), indent=2))
    else:
        run_interactive(stub)


if __name__ == "__main__":
    main()