import json

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command
from luckystonks.node.servicer import LuckyStonksServicer
from luckystonks.pb import trading_pb2


def test_insight_token_can_read_seeded_trade_tape():
    engine = Engine()
    engine.seed_demo_users()
    engine.apply(Command("bob-sell", "bob", "SELL", "AAPL", 150, 10))
    engine.apply(Command("alice-buy", "alice", "BUY", "AAPL", 150, 10))
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")

    reply = servicer.Get(
        trading_pb2.GetRequest(token="insight-token", type="TRADES"),
        context=None,
    )

    assert reply.status == "OK"
    assert len(reply.items) == 1
    assert json.loads(reply.items[0].data) == {
        "trade_id": 1,
        "symbol": "AAPL",
        "price": 150,
        "qty": 10,
        "buy_order_id": 2,
        "sell_order_id": 1,
        "buyer_id": "alice",
        "seller_id": "bob",
    }


def test_authenticated_user_can_read_portfolio_and_orders():
    engine = Engine()
    engine.seed_demo_users()
    engine.apply(Command("bob-sell", "bob", "SELL", "AAPL", 150, 10))
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")
    login = servicer.Login(trading_pb2.LoginRequest(username="bob", password="bob"), context=None)

    portfolio = servicer.Get(trading_pb2.GetRequest(token=login.token, type="PORTFOLIO"), context=None)
    orders = servicer.Get(trading_pb2.GetRequest(token=login.token, type="ORDERS"), context=None)

    assert json.loads(portfolio.items[0].data) == {"cash": 0, "shares": {"AAPL": 10}}
    assert json.loads(orders.items[0].data)["symbol"] == "AAPL"
