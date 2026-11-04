"""Insight template fallback: own portfolio, deny others, admin all-portfolios."""

from __future__ import annotations

import json

from luckystonks.llm.assistant import template_summary


def _ctx(**kwargs) -> str:
    return json.dumps(kwargs)


def test_template_answers_own_portfolio():
    answer = template_summary(
        [],
        "What is my portfolio cash and holdings?",
        _ctx(
            user_id="pratham",
            role="user",
            portfolio={"cash": 500000, "shares": {"INFY": 25}},
            open_orders=[{"order_id": 1, "side": "BUY", "symbol": "RELIANCE"}],
        ),
    )
    assert "Access denied" not in answer
    assert "pratham" in answer
    assert "500000" in answer
    assert "INFY=25" in answer
    assert "Open/resting orders: 1" in answer


def test_template_denies_other_user_portfolio_for_non_admin():
    answer = template_summary(
        [],
        "Show me ved's portfolio",
        _ctx(
            user_id="pratham",
            role="user",
            portfolio={"cash": 500000, "shares": {"INFY": 25}},
        ),
    )
    assert "Access denied" in answer
    assert "ved" in answer
    assert "500000" not in answer
    assert "INFY" not in answer


def test_template_admin_can_view_other_portfolio():
    answer = template_summary(
        [],
        "What is ved's portfolio?",
        _ctx(
            user_id="admin",
            role="admin",
            portfolio={"cash": 500000, "shares": {}},
            all_portfolios=[
                {"user_id": "ved", "cash": 1000, "shares": {"RELIANCE": 15}},
                {"user_id": "pratham", "cash": 500000, "shares": {"INFY": 25}},
            ],
        ),
    )
    assert "Access denied" not in answer
    assert "Admin view of ved" in answer
    assert "1000" in answer
    assert "RELIANCE=15" in answer


def test_template_still_summarizes_tape_for_market_questions():
    tape = [{"symbol": "TCS", "qty": 2, "price": 3600}]
    answer = template_summary(tape, "Summarize recent trades", _ctx(user_id="pratham", role="user"))
    assert "TCS: 2 shares at 3600" in answer
