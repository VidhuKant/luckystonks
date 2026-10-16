import json
from pathlib import Path

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command
from luckystonks.node.servicer import LuckyStonksServicer
from luckystonks.pb import trading_pb2


def test_insight_token_can_read_seeded_trade_tape():
    engine = Engine()
    engine.seed_demo_users()
    engine.apply(Command("ved-sell", "ved", "SELL", "RELIANCE", 2450, 10))
    engine.apply(Command("pratham-buy", "pratham", "BUY", "RELIANCE", 2450, 10))
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")

    reply = servicer.Get(
        trading_pb2.GetRequest(token="insight-token", type="TRADES"),
        context=None,
    )

    assert reply.status == "OK"
    assert len(reply.items) == 1
    assert json.loads(reply.items[0].data) == {
        "trade_id": 1,
        "symbol": "RELIANCE",
        "price": 2450,
        "qty": 10,
        "buy_order_id": 2,
        "sell_order_id": 1,
        "buyer_id": "pratham",
        "seller_id": "ved",
    }


def test_authenticated_user_can_read_portfolio_and_orders():
    engine = Engine()
    engine.seed_demo_users()
    engine.apply(Command("ved-sell", "ved", "SELL", "RELIANCE", 2450, 10))
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")
    login = servicer.Login(trading_pb2.LoginRequest(username="ved", password="ved"), context=None)

    portfolio = servicer.Get(trading_pb2.GetRequest(token=login.token, type="PORTFOLIO"), context=None)
    orders = servicer.Get(trading_pb2.GetRequest(token=login.token, type="ORDERS"), context=None)

    assert json.loads(portfolio.items[0].data)["shares"]["RELIANCE"] == 15
    assert json.loads(orders.items[0].data)["symbol"] == "RELIANCE"

def test_logout_invalidates_session():
    engine = Engine()
    engine.seed_demo_users()
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")
    login = servicer.Login(trading_pb2.LoginRequest(username="ved", password="ved"), context=None)
    assert login.status == "OK"

    out = servicer.Logout(trading_pb2.LogoutRequest(token=login.token), context=None)
    assert out.status == "OK"

    denied = servicer.Get(trading_pb2.GetRequest(token=login.token, type="PORTFOLIO"), context=None)
    assert denied.status == "ERR"


def test_admin_portfolios_requires_admin_role():
    engine = Engine()
    engine.seed_demo_users()
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")

    ved = servicer.Login(trading_pb2.LoginRequest(username="ved", password="ved"), context=None)
    denied = servicer.Get(trading_pb2.GetRequest(token=ved.token, type="ADMIN_PORTFOLIOS"), context=None)
    assert denied.status == "ERR"

    admin = servicer.Login(trading_pb2.LoginRequest(username="admin", password="admin"), context=None)
    assert admin.role == "admin"
    ok = servicer.Get(trading_pb2.GetRequest(token=admin.token, type="ADMIN_PORTFOLIOS"), context=None)
    assert ok.status == "OK"
    assert len(ok.items) >= 4


def test_admin_can_read_order_log_non_admin_denied():
    engine = Engine()
    engine.seed_demo_users()
    engine.apply(Command("ved-sell", "ved", "SELL", "RELIANCE", 2450, 10))
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")

    ved = servicer.Login(trading_pb2.LoginRequest(username="ved", password="ved"), context=None)
    denied = servicer.Get(trading_pb2.GetRequest(token=ved.token, type="ORDER_LOG"), context=None)
    assert denied.status == "ERR"

    admin = servicer.Login(trading_pb2.LoginRequest(username="admin", password="admin"), context=None)
    ok = servicer.Get(trading_pb2.GetRequest(token=admin.token, type="ORDER_LOG"), context=None)
    assert ok.status == "OK"
    assert len(ok.items) == 1
    assert json.loads(ok.items[0].data)["status"] == "RESTING"


_SEED = Path(__file__).resolve().parents[2] / "data" / "seed_users.json"


def test_admin_reset_clears_trades_and_sessions():
    engine = Engine()
    engine.seed_demo_users()
    engine.apply(Command("ved-sell", "ved", "SELL", "RELIANCE", 2450, 10))
    engine.apply(Command("pratham-buy", "pratham", "BUY", "RELIANCE", 2450, 10))
    assert len(engine.trades) == 1

    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token", seed_file=str(_SEED))
    admin = servicer.Login(trading_pb2.LoginRequest(username="admin", password="admin"), context=None)
    ved = servicer.Login(trading_pb2.LoginRequest(username="ved", password="ved"), context=None)

    reply = servicer.Post(
        trading_pb2.PostRequest(token=admin.token, type="ADMIN_RESET", data=b"{}"),
        context=None,
    )
    assert reply.status == "OK"
    assert len(engine.trades) == 0
    assert engine.order_log == []
    assert ved.token not in servicer.sessions

    denied = servicer.Get(trading_pb2.GetRequest(token=ved.token, type="PORTFOLIO"), context=None)
    assert denied.status == "ERR"


def test_admin_reset_denied_for_non_admin():
    engine = Engine()
    engine.seed_demo_users()
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token", seed_file=str(_SEED))
    ved = servicer.Login(trading_pb2.LoginRequest(username="ved", password="ved"), context=None)

    reply = servicer.Post(
        trading_pb2.PostRequest(token=ved.token, type="ADMIN_RESET", data=b"{}"),
        context=None,
    )
    assert reply.status == "ERR"
    assert reply.detail == "admin only"


def test_login_rejects_bad_password():
    engine = Engine()
    engine.seed_demo_users()
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")
    reply = servicer.Login(
        trading_pb2.LoginRequest(username="ved", password="wrong"), context=None
    )
    assert reply.status == "ERR"
    assert reply.token == ""


def test_get_requires_valid_session():
    engine = Engine()
    engine.seed_demo_users()
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")
    denied = servicer.Get(trading_pb2.GetRequest(token="fake", type="PORTFOLIO"), context=None)
    assert denied.status == "ERR"


def test_insight_token_cannot_read_portfolio():
    engine = Engine()
    engine.seed_demo_users()
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")
    denied = servicer.Get(
        trading_pb2.GetRequest(token="insight-token", type="PORTFOLIO"), context=None
    )
    assert denied.status == "ERR"
