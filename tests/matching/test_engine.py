from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command, Result
import json

def test_resting_sell_then_buy_trade()-> None:
    engine = Engine()
    engine.seed_demo_users()

    test1 = engine.apply(Command("r1", "ved", "SELL", "RELIANCE", 2450, 10))
    assert test1.status == "RESTING"
    assert len(engine.trades) == 0
    assert engine.users["ved"].shares["RELIANCE"] == 15

    test2 = engine.apply(Command("r2", "pratham", "BUY", "RELIANCE", 2450, 10))
    assert test2.status == "FILLED"
    assert len(engine.trades) == 1
    assert engine.users["ved"].shares.get("RELIANCE", 0) == 5
    assert engine.users["pratham"].shares["RELIANCE"] == 10
    assert engine.users["pratham"].cash == 500_000 - 2450 * 10


def test_reject_sell_without_shares() -> None:
    engine = Engine()
    engine.seed_demo_users()

    r = engine.apply(Command("x", "pratham", "SELL", "RELIANCE", 2450, 1))
    assert r.status == "REJECTED"
    assert len(engine.trades) == 0

def test_idempotent_client_request_id() -> None:
    engine = Engine()
    engine.seed_demo_users()
    cmd = Command("same-id", "ved", "SELL", "RELIANCE", 2450, 10)
    engine.apply(cmd)
    engine.apply(cmd)
    assert len(engine.books["RELIANCE"].asks) == 1
    assert len(engine.trades) == 0


def test_reject_second_resting_sell_when_shares_already_listed() -> None:
    engine = Engine()
    engine.seed_demo_users()

    first = engine.apply(Command("sell-1", "ved", "SELL", "RELIANCE", 2450, 10))
    assert first.status == "RESTING"
    assert len(engine.books["RELIANCE"].asks) == 1

    second = engine.apply(Command("sell-2", "ved", "SELL", "RELIANCE", 2450, 10))
    assert second.status == "REJECTED"
    assert len(engine.books["RELIANCE"].asks) == 1
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
