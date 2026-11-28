"""Exercise the paper HTTP lifecycle against a fixed observed-session feed."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from uuid import uuid4

import pytest
from portfolio_contracts import canonical_hash
from portfolio_service import paper, paper_ledger as ledger
from portfolio_service.models import AcceptedTarget, Portfolio
from portfolio_service.paper_market import read_market
from test_onboarding import accept, complete
from test_workflow import headers, portfolio, stack as workflow_stack

stack = workflow_stack
DAYS = [
    "2026-11-16",
    "2026-11-17",
    "2026-11-18",
    "2026-11-19",
    "2026-11-20",
    "2026-11-23",
    "2026-11-24",
    "2026-11-25",
    "2026-11-26",
    "2026-11-27",
]


def close(day):
    return datetime.fromisoformat(day + "T13:00:00+00:00")


@pytest.fixture
def feed(monkeypatch, tmp_path):
    clock = [close(DAYS[0])]
    monkeypatch.setattr(paper, "utcnow", lambda: clock[0])
    monkeypatch.setenv("PAPER_MARKET_DIRECTORY", str(tmp_path))
    frames = []

    def append(index, prices=None, **extras):
        day = DAYS[index]
        clock[0] = close(day)
        prices = (
            prices
            if prices is not None
            else {"FPT": 80000 + 1000 * index, "HPG": 30000, "VFF": 25000}
        )
        frame = dict(
            date=day,
            as_of=close(day).isoformat(),
            source="fixed test close",
            prices=prices,
            eligible=prices,
            **extras,
        )
        (tmp_path / f"{day}.json").write_text(
            json.dumps({"frame": frame, "sha256": canonical_hash(frame)})
        )
        frames.append(frame)
        (tmp_path / "calendar.json").write_text(
            json.dumps({"sessions": [f["date"] for f in frames]})
        )
        return frame

    return clock, frames, append


def target(client, sessions, pid, day, asset="FPT"):
    with sessions() as s:
        version = s.get(Portfolio, pid).version
    rid = complete(client, sessions, pid, str(uuid4()))
    result = accept(client, rid, version=str(version))
    assert result.status_code == 200, result.text
    tid = result.json()["id"]
    with sessions.begin() as s:
        row = s.get(AcceptedTarget, tid)
        row.allocation = {"asset_ids": [asset], "weights": [1.0]}
        row.accepted_at = close(day) - timedelta(minutes=5)
    return tid


def api(stack, day):
    client, sessions = stack
    pid = portfolio(client)
    tid = target(client, sessions, pid, day)
    url = f"/api/v1/portfolios/{pid}/paper"

    def post(path, body=None, *, user="alice", code=200):
        r = client.post(url + path, headers=headers(user), json=body or {})
        assert r.status_code == code, r.text
        return r.json()

    def get(user="alice", code=200):
        r = client.get(url, headers=headers(user))
        assert r.status_code == code, r.text
        return r.json()

    return pid, tid, get, post


def test_balances_orders_and_settlement_match_shared_engine(stack, feed):
    clock, frames, append = feed
    f0 = append(0)
    pid, _, get, post = api(stack, DAYS[0])
    assert get()["initialized"] is False
    assert get()["history"] == []
    capital = {"capital_vnd": 10_000_000}
    assert post("/initialize", capital) == post("/initialize", capital)
    post("/initialize", {"capital_vnd": 12_000_000}, code=409)
    quote = post("/preview")
    action = {"preview_id": quote["id"], "action": "CONFIRM"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.map(lambda _: post("/decisions", action), range(2))
    assert a == b == get()
    assert a["orders"][0]["status"] == "PENDING"
    assert a["positions"][0]["quantity"] == 0
    expected = ledger.new_account(capital["capital_vnd"])
    ledger.advance(expected, f0)
    ledger.confirm(expected, ledger.preview(expected, {"FPT": 1.0}, f0))
    for i in (1, 2, 3):
        frame = append(i)
        ledger.advance(expected, frame)
    after = get()
    assert [h["date"] for h in after["history"]] == DAYS[:4]
    assert after["orders"][0]["status"] == "FILLED"
    assert after["positions"][0]["quantity"] == pytest.approx(
        expected["lots"]["FPT"][0]["units"]
    )
    target(*stack, pid, DAYS[3], "HPG")
    decision = post("/preview")
    confirmed = post("/decisions", {"preview_id": decision["id"], "action": "CONFIRM"})
    assert len(confirmed["orders"]) >= 2
    ledger.confirm(expected, ledger.preview(expected, {"HPG": 1.0}, frames[-1]))
    for i in (4, 5, 6):
        frame = append(i)
        ledger.advance(expected, frame)
        value = get()
        check = ledger.valuation(expected, frame)
        assert value["valuation"]["nav_vnd"] == pytest.approx(check["total"])
        assert value["valuation"]["available_cash_vnd"] == pytest.approx(check["cash"])
        assert value["valuation"]["fees_vnd"] == pytest.approx(check["fees"])
        assert value["history"][-1]["receivable_vnd"] == pytest.approx(
            check["receivable"]
        )
        if i == 4:
            assert check["receivable"] > 0
    assert value["valuation"]["receivable_vnd"] == 0
    assert any(o["status"] == "SETTLED" for o in value["orders"])
    assert value["reviews"][0]["date"] == DAYS[5]
    assert value["reviews"][0]["drift"] is not None
    before_orders = len(value["orders"])
    assert post("/reviews/" + DAYS[5] + "/skip")["reviews"][0]["status"] == "SKIPPED"
    assert len(get()["orders"]) == before_orders


def test_staleness_ownership_delayed_clicks_and_replay(stack, feed):
    clock, _, append = feed
    append(0)
    pid, _, get, post = api(stack, DAYS[0])
    post("/initialize", {"capital_vnd": 1_000_000})
    q = post("/preview")
    for user in ("bob", "admin"):
        get(user, 404)
        post("/initialize", {"capital_vnd": 100}, user=user, code=404)
        post("/preview", user=user, code=404)
        post(
            "/decisions",
            {"preview_id": q["id"], "action": "CONFIRM"},
            user=user,
            code=404,
        )
    clock[0] += timedelta(minutes=16)
    post("/decisions", {"preview_id": q["id"], "action": "CONFIRM"}, code=409)
    q = post("/preview")
    target(*stack, pid, DAYS[0], "HPG")
    post("/decisions", {"preview_id": q["id"], "action": "CONFIRM"}, code=409)
    q = post("/preview")
    skip = {"preview_id": q["id"], "action": "SKIP"}
    assert post("/decisions", skip) == post("/decisions", skip)
    assert get()["orders"] == []
    # Tuesday morning: Monday close can size an order. Tuesday's later close cannot fill it.
    clock[0] = close(DAYS[1]) - timedelta(hours=10)
    q = post("/preview")
    post("/decisions", {"preview_id": q["id"], "action": "CONFIRM"})
    append(1)
    assert get()["orders"][0]["status"] == "PENDING"
    append(2)
    assert get()["orders"][0]["fill_date"] == DAYS[2]
    append(3, prices={"FPT": 83000})
    assert get()["quote_status"] == "MISSING"
    assert get()["history"][-1]["stale_assets"] == ["HPG"]
    append(4)
    assert get()["quote_status"] == "FRESH"
    clock[0] += timedelta(days=7)
    assert get()["quote_status"] == "STALE"
    post("/preview", code=409)


def test_market_reader_rejects_future_publication_and_crossed_quotes(feed, tmp_path):
    clock, _, append = feed
    frame = append(0, gold_bid=120, gold_ask=100)
    assert read_market(None, clock[0] - timedelta(minutes=1))[0] == []
    with pytest.raises(ValueError, match="SJC"):
        read_market(None, clock[0])
    frame["gold_bid"] = 95
    (tmp_path / (DAYS[0] + ".json")).write_text(
        json.dumps({"frame": frame, "sha256": "0" * 64})
    )
    with pytest.raises(ValueError, match="identity"):
        read_market(None, clock[0])


def test_dated_vff_nav_arrives_with_later_nav_and_fills_once(stack, feed):
    clock, _, append = feed
    append(0)
    pid, _, get, post = api(stack, DAYS[0])
    target(*stack, pid, DAYS[0], "VFF")
    post("/initialize", {"capital_vnd": 1_000_000})
    q = post("/preview")
    post("/decisions", {"preview_id": q["id"], "action": "CONFIRM"})
    for i in (1, 2, 3):
        append(i, vff_nav=25000, vff_nav_date=DAYS[0])
        assert get()["orders"][0]["status"] == "PENDING"
    append(4, vff_nav_date=DAYS[4], vff_nav=25000, vff_navs={DAYS[3]: 20000})
    account = get()
    assert account["positions"][0]["quantity"] == 50
    assert account["orders"][0]["deal_date"] == DAYS[3]
    assert account["orders"][0]["fill_date"] == DAYS[4]
    assert account["orders"][0]["fill_price_vnd"] == 20000
    assert account == get()


def test_independent_open_dates_ignore_weekends_and_never_create_orders(stack, feed):
    clock, _, append = feed
    client, sessions = stack
    append(0)
    first, _, get, post = api(stack, DAYS[0])
    post("/initialize", {"capital_vnd": 1_000_000})
    append(1)
    append(2)
    # A second owner starts two observed sessions later.
    second, _, get2, post2 = api(stack, DAYS[2])
    from portfolio_service.models import User
    from sqlalchemy import select

    client.get("/api/v1/me", headers=headers("bob"))
    with sessions.begin() as s:
        bob = s.scalar(select(User).where(User.subject == "bob"))
        s.get(Portfolio, second).owner_user_id = bob.id
        row = s.scalar(
            select(AcceptedTarget).where(AcceptedTarget.portfolio_id == second)
        )
        row.owner_user_id = bob.id
    post2("/initialize", {"capital_vnd": 2_000_000}, user="bob")
    q = post2("/preview", user="bob")
    # A preview from another portfolio never belongs to the authenticated account.
    post("/decisions", {"preview_id": q["id"], "action": "CONFIRM"}, code=404)
    for i in (3, 4, 5, 6, 7):
        append(i)
    first_state, second_state = get(), get2("bob")
    assert first_state["reviews"][0]["date"] == DAYS[5]
    assert second_state["reviews"][0]["date"] == DAYS[7]
    assert second_state["history"][0]["date"] == DAYS[2]
    assert first_state["orders"] == second_state["orders"] == []
    post2(
        "/decisions", {"preview_id": q["id"], "action": "CONFIRM"}, user="bob", code=409
    )


def test_background_worker_reconciles_idle_account_and_due_review(
    stack, feed, monkeypatch
):
    from portfolio_service import paper_worker
    from portfolio_service.models import PaperAccount

    clock, _, append = feed
    monkeypatch.setattr(paper_worker, "utcnow", lambda: clock[0])
    _, sessions = stack
    append(0)
    pid, tid, _, post = api(stack, DAYS[0])
    post("/initialize", {"capital_vnd": 1_000_000})
    for i in range(1, 6):
        append(i)
    paper_worker.tick(sessions)
    paper_worker.tick(sessions)
    with sessions() as session:
        saved = session.get(PaperAccount, pid).state
        assert [day["date"] for day in saved["history"]] == DAYS[:6]
        assert [(r["date"], r["target_id"], r["status"]) for r in saved["reviews"]] == [
            (DAYS[5], tid, "DUE")
        ]
        assert saved["orders"] == saved["decisions"] == []


def test_expected_session_tracks_vff_dealing_date_until_nav_arrives():
    book = dict(date="2026-11-27", session=10)
    order = dict(asset="VFF", decision_day=book["date"], submitted=10)
    for asset, reason in [("STB", "STOCK_CLOSE"), ("GOLD", "GOLD_QUOTE")]:
        assert paper.pending_estimate(order | {"asset": asset}, book, {}) == dict(
            expected_session="2026-11-30", wait_reason=reason
        )
    assert paper.pending_estimate(order, book, {}) == dict(
        expected_session="2026-12-01", wait_reason="VFF_DEALING"
    )
    # A missing Monday session pushes eligibility from Tuesday to Thursday.
    assert paper.pending_estimate(order, dict(date="2026-12-01", session=11), {}) == dict(
        expected_session="2026-12-03", wait_reason="VFF_DEALING"
    )
    assert paper.pending_estimate(order | {"deal_date": "2026-12-03"}, book, {}) == dict(
        expected_session="2026-12-03", wait_reason="VFF_NAV"
    )
