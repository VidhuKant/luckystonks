"""Engine tests — names and docstrings only until matching is implemented."""

from __future__ import annotations

import pytest

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command


def test_apply_not_implemented_yet() -> None:
    """Smoke: Engine.apply exists but raises until step 2 of DOCS."""
    engine = Engine()
    cmd = Command(
        client_request_id="req-1",
        user_id="alice",
        side="BUY",
        symbol="AAPL",
        price=150,
        qty=10,
    )
    with pytest.raises(NotImplementedError):
        engine.apply(cmd)


@pytest.mark.skip(reason="skeleton: implement with Engine.apply in step 2")
def test_resting_sell_then_buy_trade() -> None:
    """Future: Bob sell 10 AAPL @ 150 rests; Alice buy 10 @ 150 produces one trade."""
    raise NotImplementedError


@pytest.mark.skip(reason="skeleton: implement with Engine.apply in step 2")
def test_reject_sell_without_shares() -> None:
    """Future: selling more shares than the user owns is rejected."""
    raise NotImplementedError


@pytest.mark.skip(reason="skeleton: implement with Engine.apply in step 2")
def test_idempotent_client_request_id() -> None:
    """Future: duplicate client_request_id returns the same Result without double apply."""
    raise NotImplementedError
