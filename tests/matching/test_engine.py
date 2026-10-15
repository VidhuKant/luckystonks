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



def test_save_and_load_state_preserves_trades(tmp_path):
    state_file = tmp_path / "state.json"
    engine = Engine()
    engine.seed_demo_users()
    engine.apply(Command("r1", "ved", "SELL", "RELIANCE", 2450, 10))
    engine.apply(Command("r2", "pratham", "BUY", "RELIANCE", 2450, 10))
    engine.set_state_path(state_file)
    engine.save_state(state_file)

    restored = Engine()
    restored.load_state(state_file)
    assert len(restored.trades) == 1
    assert restored.users["pratham"].shares.get("RELIANCE") == 10
    assert restored.users["ved"].shares.get("RELIANCE") == 5


def test_order_log_records_each_new_apply() -> None:
    engine = Engine()
    engine.seed_demo_users()
    engine.apply(Command("r1", "ved", "SELL", "RELIANCE", 2450, 10))
    engine.apply(Command("r2", "pratham", "BUY", "RELIANCE", 2450, 10))
    assert len(engine.order_log) == 2
    assert engine.order_log[0]["status"] == "RESTING"
    assert engine.order_log[1]["status"] == "FILLED"
    assert engine.order_log[1]["filled_qty"] == 10
    engine.apply(Command("r1", "ved", "SELL", "RELIANCE", 2450, 10))
    assert len(engine.order_log) == 2


def test_order_log_survives_save_and_load(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    engine = Engine()
    engine.seed_demo_users()
    engine.apply(Command("r1", "ved", "SELL", "RELIANCE", 2450, 10))
    engine.set_state_path(state_file)
    engine.save_state(state_file)
    restored = Engine()
    restored.load_state(state_file)
    assert len(restored.order_log) == 1
    assert restored.order_log[0]["user_id"] == "ved"


def test_reset_from_seed_clears_market(tmp_path) -> None:
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(
        json.dumps(
            {
                "users": [
                    {"user_id": "u1", "password": "p", "cash": 1000, "shares": {"X": 5}},
                ]
            }
        ),
        encoding="utf-8",
    )
    engine = Engine()
    engine.load_seed_data(seed_file)
    engine.apply(Command("s1", "u1", "SELL", "X", 100, 2))
    assert not engine.trades
    assert engine.books["X"].asks
    assert engine.order_log

    engine.reset_from_seed(seed_file)
    assert engine.trades == []
    assert engine.books == {}
    assert engine.order_log == []
    assert engine.results_by_request == {}
    assert engine.users["u1"].shares["X"] == 5
    assert engine._next_order_id == 1