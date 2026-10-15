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
    assert engine.apply(Command("ved-sell", "ved", "SELL", "RELIANCE", 2450, 10)).status == "RESTING"
    assert engine.apply(Command("pratham-buy", "pratham", "BUY", "RELIANCE", 2450, 10)).status == "FILLED"
    servicer = LuckyStonksServicer(engine, insight_read_token="insight-token")
    monkeypatch.setattr(assistant, "TRADING_READ_TOKEN", "insight-token")

    tape = assistant.fetch_tape(LocalTradingStub(servicer))
    answer = assistant.template_summary(tape, "Summarize recent trades", "")

    assert tape == [
        {
            "trade_id": 1,
            "symbol": "RELIANCE",
            "price": 2450,
            "qty": 10,
            "buy_order_id": 2,
            "sell_order_id": 1,
            "buyer_id": "pratham",
            "seller_id": "ved",
        }
    ]
    assert "No live trades" not in answer
    assert "RELIANCE: 10 shares at 2450" in answer
