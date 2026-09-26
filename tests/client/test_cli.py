from luckystonks.client.cli import run_demo
from luckystonks.matching.engine import Engine
from luckystonks.node.servicer import LuckyStonksServicer


class LocalTradingStub:
    def __init__(self, servicer):
        self.servicer = servicer

    def Login(self, request, timeout):
        assert timeout == 5
        return self.servicer.Login(request, context=None)

    def Post(self, request, timeout):
        assert timeout == 5
        return self.servicer.Post(request, context=None)

    def Get(self, request, timeout):
        assert timeout == 5
        return self.servicer.Get(request, context=None)


def test_run_demo_shows_resting_then_filled_trade():
    engine = Engine()
    engine.seed_demo_users()
    stub = LocalTradingStub(LuckyStonksServicer(engine, insight_read_token="insight-token"))

    trades = run_demo(stub)

    assert trades == [
        {
            "trade_id": 1,
            "symbol": "AAPL",
            "price": 150,
            "qty": 10,
            "buy_order_id": 2,
            "sell_order_id": 1,
            "buyer_id": "alice",
            "seller_id": "bob",
        }
    ]
