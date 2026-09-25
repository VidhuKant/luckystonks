import json
from types import SimpleNamespace

from luckystonks.llm import assistant


class FakeTradingStub:
    def __init__(self, reply):
        self.reply = reply
        self.request = None

    def Get(self, request, timeout):
        self.request = request
        assert timeout == 5
        return self.reply


def test_fetch_tape_uses_read_only_trades_request():
    reply = SimpleNamespace(
        status="OK",
        items=[SimpleNamespace(id="trade-1", data=json.dumps({"symbol": "AAPL", "qty": 2}).encode())],
    )
    stub = FakeTradingStub(reply)

    assert assistant.fetch_tape(stub) == [{"symbol": "AAPL", "qty": 2}]
    assert stub.request.type == "TRADES"


def test_summarize_falls_back_when_vllm_is_unavailable(monkeypatch):
    def unavailable(_messages):
        raise RuntimeError("vLLM is offline")

    monkeypatch.setattr(assistant, "complete_chat", unavailable)

    answer = assistant.summarize([{"symbol": "AAPL", "qty": 10, "price": 150}], "What traded?", "")

    assert "AAPL: 10 shares at 150" in answer
