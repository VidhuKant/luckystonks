from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command, Result
import json

def test_resting_sell_then_buy_trade()-> None:
    engine = Engine()
    engine.seed_demo_users()

    test1 = engine.apply(Command("r1", "bob", "SELL", "AAPL", 150, 10))
    assert test1.status == "RESTING"
    assert len(engine.trades) == 0
    assert engine.users["bob"].shares["AAPL"] == 10

    test2 = engine.apply(Command("r2", "alice", "BUY", "AAPL", 150, 10))
    assert test2.status == "FILLED"
    assert len(engine.trades) == 1
    assert engine.users["bob"].shares.get("AAPL", 0) == 0
    assert engine.users["alice"].shares["AAPL"] == 10
    assert engine.users["alice"].cash == 10_000 - 150 * 10


def test_reject_sell_without_shares() -> None:
    engine = Engine()
    engine.seed_demo_users()

    r = engine.apply(Command("x", "alice", "SELL", "AAPL", 150, 1))
    assert r.status == "REJECTED"
    assert len(engine.trades) == 0

def test_idempotent_client_request_id() -> None:
    engine = Engine()
    engine.seed_demo_users()
    cmd = Command("same-id", "bob", "SELL", "AAPL", 150, 10)
    engine.apply(cmd)
    engine.apply(cmd)
    assert len(engine.books["AAPL"].asks) == 1
    assert len(engine.trades) == 0


def test_load_seed_data_and_read_views(tmp_path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(
        json.dumps(
            {"users": [{"user_id": "carol", "password": "secret", "cash": 5000, "shares": {"TSLA": 20}}]}
        ),
        encoding="utf-8",
    )
    engine = Engine()
    engine.load_seed_data(seed_file)

    result = engine.apply(Command("carol-sell", "carol", "SELL", "TSLA", 250, 5))

    assert result.status == "RESTING"
    assert engine.snapshot("PORTFOLIO", "carol") == {"cash": 5000, "shares": {"TSLA": 20}}
    assert engine.snapshot("BOOK", "carol", "TSLA") == {
        "TSLA": {"bids": [], "asks": [{"order_id": 1, "side": "SELL", "symbol": "TSLA", "price": 250, "qty": 5, "remaining_qty": 5}]}
    }
    assert engine.snapshot("ORDERS", "carol") == [
        {"order_id": 1, "side": "SELL", "symbol": "TSLA", "price": 250, "qty": 5, "remaining_qty": 5}
    ]
