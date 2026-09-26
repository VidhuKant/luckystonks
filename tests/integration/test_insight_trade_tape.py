from luckystonks.llm import assistant
from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command
from luckystonks.node.servicer import LuckyStonksServicer


class LocalTradingStub:
    def __init__(self, servicer):
        self.servicer = servicer

    def Get(self, request, timeout):
        assert timeout == 5
        return self.servicer.Get(request, context=None)


def test_seeded_trade_is_available_to_insight(monkeypatch):
    engine = Engine()
    engine.seed_demo_users()
    assert engine.apply(Command("bob-sell", "bob", "SELL", "AAPL", 150, 10)).status == "RESTING"
    assert engine.apply(Command("alice-buy", "alice", "BUY", "AAPL", 150, 10)).status == "FILLED"
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")
    monkeypatch.setattr(assistant, "TRADING_READ_TOKEN", "insight-token")

    tape = assistant.fetch_tape(LocalTradingStub(servicer))
    answer = assistant.template_summary(tape, "Summarize recent trades", "")

    assert tape == [
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
    assert "No live trades" not in answer
    assert "AAPL: 10 shares at 150" in answer
