from datetime import date, timedelta
from math import isclose

import pytest

from portfolio_service.paper_ledger import (
    advance,
    confirm,
    new_account,
    preview,
    valuation,
)


def frame(day, stock=100.0, fund=20000.0, **extra):
    prices = {"ACB": stock, "GOLD": 1000.0, "VFF": fund}
    return dict(
        date=day,
        prices=prices,
        eligible=prices,
        gold_bid=990.0,
        gold_ask=1010.0,
        vff_nav=fund,
        **extra,
    )


def test_confirm_is_distinct_from_fill_and_settle():
    state = new_account(1_000_000)
    start = frame("2025-01-06")
    advance(state, start)
    q = preview(state, {"ACB": 1}, start)
    assert q["drift"] == 1 and valuation(state, start)["pnl"] == 0
    confirm(state, q, reference="accept-1")
    with pytest.raises(ValueError):
        confirm(state, q)
    bought = advance(state, frame("2025-01-07"))[0]
    assert bought["reference"] == "accept-1" and bought["side"] == "buy"
    assert isclose(valuation(state, frame("2025-01-07"))["pnl"], -bought["fee"])
    advance(state, frame("2025-01-08"))
    day = frame("2025-01-09", stock=110.0)
    advance(state, day)
    confirm(state, preview(state, {"GOLD": 1}, day))
    sale = advance(state, frame("2025-01-10", stock=110.0))[0]
    assert sale["tax"] > 0 and state["cash"] < 0.01
    book = valuation(state, frame("2025-01-10", stock=110.0))
    assert book["receivable"] > 1_000_000 and book["pnl"] > 0
    advance(state, frame("2025-01-13"))
    assert isclose(advance(state, frame("2025-01-14"))[0]["net"], book["receivable"])
    assert isclose(state["cash"], book["total"])


def test_vff_partial_fifo_has_no_fees_on_retained_units():
    day = date(2025, 1, 7)

    def opened(age):
        return (day - timedelta(days=age)).isoformat()

    state = new_account(2_000_000)
    state.update(
        cash=0,
        lots={
            "VFF": [
                {"units": 25.0, "opened": opened(age), "available": 0}
                for age in (730, 729, 365, 364)
            ]
        },
    )
    friday = frame("2025-01-03")
    advance(state, friday)
    confirm(state, preview(state, {"VFF": 0.2, "ACB": 0.8}, friday))
    advance(state, frame("2025-01-06"))
    sale = advance(state, frame(str(day)))[0]
    assert [lot["units"] for lot in sale["sold_lots"]] == [25.0, 25.0, 25.0, 5.0]
    assert (
        sale["fee"] == 7000
        and sale["tax"] == 1600
        and state["lots"]["VFF"][0]["units"] == 20
    )
    late = frame(str(day), eligible_vff_date="2025-01-02")
    assert (
        preview(state, {"ACB": 1}, late)["blocked"] == "VFF_FILL_AWAITING_PUBLICATION"
    )


def test_forward_confirmation_and_expiry_do_not_spend_reserved_cash_twice():
    state = new_account(1_000_000)
    start = frame("2025-01-03")
    advance(state, start)
    confirm(state, preview(state, {"VFF": 1}, start), decision_day="2025-01-07")
    for d in [6, 7, 8, 9, 10, 13, 14]:
        f = frame(f"2025-01-{d:02d}")
        f["vff_nav"] = None
        advance(state, f)
        assert valuation(state, f)["total"] == 1_000_000
        assert state["reserved"] == (1_000_000 if d in (8, 9, 10, 13) else 0)
    assert not state["orders"] and state["cash"] == 1_000_000


def test_corporate_action_does_not_create_profit_and_stale_gold_is_not_traded():
    state = new_account(1000)
    start = frame("2025-01-06", stock_fee_bps=0)
    advance(state, start)
    confirm(state, preview(state, {"ACB": 1}, start))
    advance(state, frame("2025-01-07", stock_fee_bps=0))
    split = frame("2025-01-08", stock=50.0, share_factors={"ACB": 2})
    advance(state, split)
    assert valuation(state, split)["pnl"] == 0
    late = frame(
        "2025-01-09", stock=50.0, eligible_gold_bid=None, eligible_gold_ask=None
    )
    advance(state, late)
    assert preview(state, {"GOLD": 1}, late)["blocked"] == "MISSING_GOLD_QUOTE"


def test_live_fill_waits_for_publication_and_uses_economic_date():
    state = new_account(1_000_000)
    monday = frame("2025-01-06", vff_nav_date="2025-01-02")
    advance(state, monday)
    confirm(state, preview(state, {"VFF": 1}, monday))
    for d, observed in [(7, 2), (8, 7), (9, 7)]:
        advance(
            state, frame(f"2025-01-{d:02d}", vff_nav_date=f"2025-01-{observed:02d}")
        )
        assert state["reserved"] == 1_000_000
    (event,) = advance(state, frame("2025-01-10", vff_nav_date="2025-01-09"))
    assert event["date"] == "2025-01-10" and event["deal_date"] == "2025-01-09"
    assert state["lots"]["VFF"][0]["opened"] == "2025-01-09"


@pytest.mark.parametrize("capital", [1e15, 1e19])
def test_large_vnd_account_can_fill_a_fully_funded_basket(capital):
    state = new_account(capital)
    first = frame("2025-01-06", stock=12345)
    advance(state, first)
    confirm(state, preview(state, {"ACB": 1}, first))
    second = frame("2025-01-07", stock=12345)
    (trade,) = advance(state, second)
    assert 0 <= state["cash"] < capital * 1e-14
    assert isclose(
        valuation(state, second)["total"], capital - trade["fee"], rel_tol=1e-14
    )
