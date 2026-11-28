"""Paper account reconciliation and owner-scoped HTTP operations."""

from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import Field
from sqlalchemy import select, text

from portfolio_contracts import StrictModel, aware, canonical_hash, utcnow
from . import paper_ledger as ledger
from .models import AcceptedTarget, PaperAccount, PaperDecision
from .paper_market import VN, read_market


class PaperCapital(StrictModel):
    capital_vnd: Decimal = Field(gt=0, le=10**19, decimal_places=4, max_digits=24)


class PaperAction(StrictModel):
    preview_id: UUID
    action: Literal["CONFIRM", "SKIP"]


def latest_targets(session, portfolio):
    return session.scalars(
        select(AcceptedTarget)
        .where(
            AcceptedTarget.portfolio_id == portfolio.id,
            AcceptedTarget.owner_user_id == portfolio.owner_user_id,
        )
        .order_by(
            AcceptedTarget.portfolio_version.desc(),
            AcceptedTarget.accepted_at.desc(),
            AcceptedTarget.id.desc(),
        )
    ).all()


def weights(target):
    if target is None:
        return {}
    return {
        asset: float(weight)
        for asset, weight in zip(
            target.allocation["asset_ids"], target.allocation["weights"], strict=True
        )
    }


def new_state(capital):
    return dict(
        ledger=ledger.new_account(capital),
        initial_capital_vnd=str(capital),
        frame=None,
        revision=0,
        history=[],
        events=[],
        reviews=[],
        sessions_since_open=0,
        orders=[],
        decisions=[],
        marks={},
        mark_dates={},
    )


def balances(book, day):
    return dict(
        date=day,
        nav_vnd=book["total"],
        pnl_vnd=book["pnl"],
        return_fraction=book["pnl_pct"] / 100,
        available_cash_vnd=book["cash"],
        reserved_cash_vnd=book["reserved"],
        receivable_vnd=book["receivable"],
        fees_vnd=book["fees"],
        spread_vnd=book["spread"],
    )


def display_order(order, frame):
    asset = order["asset"]
    price = frame["eligible"][asset]
    price_date = frame["date"]
    if asset == "GOLD":
        side_key = "ask" if order["side"] == "buy" else "bid"
        price = frame.get("eligible_gold_" + side_key, frame.get("gold_" + side_key))
        price_date = frame.get("eligible_gold_date", frame["date"])
    elif asset == "VFF":
        price_date = frame.get("eligible_vff_date") or frame["date"]
    return dict(
        asset_id=asset,
        side=order["side"].upper(),
        quantity=order["units"],
        price_vnd=price,
        price_date=price_date,
        gross_vnd=order["gross"],
        estimated_fee_vnd=order["fee"] + order["tax"] + order["spread"],
    )


def record_events(state, events, frame):
    for event in events:
        event = {
            **event,
            "quote_source": frame["source"],
            "market_hash": canonical_hash(frame),
        }
        state["events"].append(event)
        order = next(
            (
                o
                for o in reversed(state["orders"])
                if o["asset_id"] == event["asset"]
                and o["preview_id"] == event.get("reference")
                and (event.get("side") is None or o["side"] == event["side"].upper())
            ),
            None,
        )
        if order is None:
            continue
        if event["kind"] == "fill":
            order.update(
                status="FILLED",
                fill_date=frame["date"],
                deal_date=event.get("deal_date", frame["date"]),
                filled_quantity=event["units"],
                fill_price_vnd=event["gross"] / event["units"],
                fee_vnd=event["fee"] + event["tax"],
            )
        elif event["kind"] == "settle":
            order.update(status="SETTLED", settled_date=frame["date"])
        elif event["kind"] in ("expire", "skip"):
            order.update(status="EXPIRED", reason=event.get("reason", event["kind"]))


def reconcile(account, targets, now, market=read_market):
    state = deepcopy(account.state)
    opened = aware(account.opened_at).astimezone(VN).date()
    today = now.astimezone(VN).date()
    original = state["frame"]
    start = date.fromisoformat(original["date"]) if original else opened
    status = "MISSING"
    try:
        frames, latest = market(start, now)
        # A pre-opening close may price a new decision. No NAV or position predates opening.
        if original is None and not state["history"] and not frames:
            frames, latest = market(None, now)
        if original and (
            not frames or canonical_hash(frames[0]) != canonical_hash(original)
        ):
            return "MISSING"
        for frame in frames:
            if state["frame"] and frame["date"] <= state["frame"]["date"]:
                continue
            # Apply each close to a copy so a missing held mark cannot partially debit the account.
            next_book = deepcopy(state["ledger"])
            marks = state["marks"] | frame["prices"]
            execution = frame | {"prices": marks}
            events = []
            pending = []
            for order in next_book["orders"]:
                asset = order["asset"]
                if (
                    asset != "VFF"
                    and asset not in frame["prices"]
                    and frame["date"] > order["decision_day"]
                ):
                    events.append(
                        dict(
                            date=frame["date"],
                            kind="skip",
                            asset=asset,
                            side=order["side"],
                            reference=order["reference"],
                            reason="PRICE_UNAVAILABLE",
                        )
                    )
                    continue
                if asset == "VFF" and order.get("deal_date") in frame.get(
                    "vff_navs", {}
                ):
                    deal_day = order["deal_date"]
                    execution.update(
                        vff_nav_date=deal_day, vff_nav=frame["vff_navs"][deal_day]
                    )
                pending.append(order)
            next_book["orders"] = pending
            events.extend(ledger.advance(next_book, execution))
            book = ledger.valuation(next_book, execution)
            state["marks"] = marks
            for asset in frame["prices"]:
                state["mark_dates"][asset] = (
                    frame.get("eligible_vff_date") if asset == "VFF" else frame["date"]
                )
            state["ledger"], state["frame"] = next_book, frame
            state["revision"] += 1
            record_events(state, events, frame)
            day = date.fromisoformat(frame["date"])
            if day >= opened:
                state["sessions_since_open"] += 1
                if (
                    state["sessions_since_open"] > 1
                    and (state["sessions_since_open"] - 1) % 5 == 0
                ):
                    as_of = datetime.fromisoformat(frame["as_of"])
                    target = next(
                        (t for t in targets if aware(t.accepted_at) <= as_of), None
                    )
                    if target is not None:
                        try:
                            check = ledger.preview(next_book, weights(target), frame)
                            drift, reason = check["drift"], check["blocked"]
                        except (KeyError, ValueError):
                            drift, reason = None, "MISSING_PRICE"
                        state["reviews"].append(
                            dict(
                                date=str(day),
                                checked_at=now.isoformat(),
                                target_id=target.id,
                                status="DUE",
                                drift=drift,
                                reason=reason,
                            )
                        )
                snapshot = balances(book, str(day))
                snapshot["quote_status"] = (
                    "FRESH"
                    if book["positions"].keys() <= frame["prices"].keys()
                    else "MISSING"
                )
                snapshot["stale_assets"] = sorted(
                    book["positions"].keys() - frame["prices"].keys()
                )
                if state["history"] and state["history"][-1]["date"] == str(day):
                    state["history"][-1] = snapshot
                else:
                    state["history"].append(snapshot)
        frame = state["frame"]
        if frame and frame["date"] == latest:
            required = {
                a for a, w in weights(targets[0] if targets else None).items() if w > 0
            }
            held = set(
                ledger.valuation(state["ledger"], {"prices": state["marks"]})[
                    "positions"
                ]
            )
            if (required | held) <= frame["eligible"].keys() and held <= frame[
                "prices"
            ].keys():
                status = (
                    "FRESH"
                    if (today - date.fromisoformat(latest)).days <= 3
                    else "STALE"
                )
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        status = "MISSING"
    if not state["history"]:
        state["history"].append(
            balances(ledger.valuation(state["ledger"], {"prices": {}}), str(opened))
        )
    if state != account.state:
        account.state = state
    return status


def pending_estimate(order, book, frame):
    if order.get("deal_date"):
        return dict(expected_session=order["deal_date"], wait_reason="VFF_NAV")
    asset = order["asset"]
    day = date.fromisoformat(max(order["decision_day"], book["date"]))
    remaining = 1
    weekdays = range(5)
    reason = "GOLD_QUOTE" if asset == "GOLD" else "STOCK_CLOSE"
    if asset == "VFF":
        age = book["session"] - order["submitted"]
        remaining = max(1, ledger.VFF_MIN_SESSIONS - age)
        weekdays = frame.get("vff_dealing_weekdays", ledger.VFF_DEALING_WEEKDAYS)
        reason = "VFF_DEALING"
    # Future exchange holidays are not present in the observed-session calendar.
    for _ in range(14):
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
            if remaining <= 0 and day.weekday() in weekdays:
                return dict(expected_session=str(day), wait_reason=reason)
    return dict(expected_session=None, wait_reason=reason)


def response(account, target, status):
    result = dict(
        initialized=account is not None,
        target_id=target.id if target else None,
        initial_capital_vnd=None,
        valuation=None,
        history=[],
        positions=[],
        orders=[],
        reviews=[],
        events=[],
        decisions=[],
        quote_status=status,
        quote_date=None,
        quote_as_of=None,
        quote_source=None,
    )
    if account is None:
        return result
    state = account.state
    frame = state["frame"] or {"prices": {}}
    book = ledger.valuation(state["ledger"], {"prices": state["marks"]})
    allocation = weights(target)
    positions = []
    for asset in sorted(
        set(book["positions"]) | {a for a, w in allocation.items() if w > 0}
    ):
        p = book["positions"].get(asset, {})
        weight, target_weight = p.get("weight", 0.0), allocation.get(asset, 0.0)
        positions.append(
            dict(
                asset_id=asset,
                quantity=p.get("units", 0.0),
                price_vnd=state["marks"].get(asset),
                price_date=state["mark_dates"].get(asset),
                value_vnd=p.get("value", 0.0),
                weight=weight,
                target_weight=target_weight,
                drift=weight - target_weight,
            )
        )
    estimates = {
        (order["reference"], order["asset"]): pending_estimate(order, state["ledger"], frame)
        for order in state["ledger"]["orders"]
    }
    return result | dict(
        initial_capital_vnd=state["ledger"]["capital"],
        valuation=balances(book, state["history"][-1]["date"]),
        history=state["history"],
        positions=positions,
        orders=[
            row | estimates.get((row["preview_id"], row["asset_id"]), {})
            if row["status"] == "PENDING" else row
            for row in reversed(state["orders"])
        ],
        reviews=list(reversed(state["reviews"])),
        events=state["events"],
        decisions=list(reversed(state["decisions"])),
        quote_date=frame.get("date"),
        quote_source=frame.get("source"),
        quote_as_of=frame.get("as_of"),
    )


def lock_sqlite_writer(session):
    # SQLite ignores FOR UPDATE. Acquire its write lock before reading the account.
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))


def install_paper_routes(app, *, sessions, owner, owned_portfolio):
    base = "/api/v1/portfolios/{portfolio_id}/paper"

    def load(session, portfolio_id, user_id, *, required=True):
        lock_sqlite_writer(session)
        portfolio = owned_portfolio(session, portfolio_id, user_id, lock=True)
        targets = latest_targets(session, portfolio)
        target = targets[0] if targets else None
        account = session.get(PaperAccount, portfolio.id)
        if required and account is None:
            raise HTTPException(409, "Hãy khởi tạo tài khoản mô phỏng trước.")
        return portfolio, account, targets, target

    @app.get(base)
    def summary(portfolio_id: UUID, user_id=Depends(owner)):
        with sessions.begin() as session:
            _, account, targets, target = load(
                session, portfolio_id, user_id, required=False
            )
            status = reconcile(account, targets, utcnow()) if account else "MISSING"
            return response(account, target, status)

    @app.post(base + "/initialize")
    def initialize(portfolio_id: UUID, body: PaperCapital, user_id=Depends(owner)):
        with sessions.begin() as session:
            portfolio, account, targets, target = load(
                session, portfolio_id, user_id, required=False
            )
            now = utcnow()
            if account is None:
                if not target or target.portfolio_version != portfolio.version:
                    raise HTTPException(
                        409, "Cần chấp nhận mục tiêu phù hợp trước khi khởi tạo."
                    )
                account = PaperAccount(
                    portfolio_id=portfolio.id,
                    opened_at=now,
                    state=new_state(body.capital_vnd),
                )
                session.add(account)
            elif Decimal(account.state["initial_capital_vnd"]) != body.capital_vnd:
                raise HTTPException(409, "Tài khoản mô phỏng đã có vốn đầu kỳ.")
            return response(account, target, reconcile(account, targets, now))

    @app.post(base + "/preview")
    def preview(portfolio_id: UUID, body: StrictModel, user_id=Depends(owner)):
        with sessions.begin() as session:
            portfolio, account, targets, target = load(session, portfolio_id, user_id)
            now = utcnow()
            status = reconcile(account, targets, now)
            if (
                status != "FRESH"
                or not target
                or target.portfolio_version != portfolio.version
            ):
                raise HTTPException(
                    409, "Cần giá mới và mục tiêu hiện hành để xem trước."
                )
            state, frame = account.state, account.state["frame"]
            try:
                quote = ledger.preview(state["ledger"], weights(target), frame)
            except (ValueError, KeyError):
                raise HTTPException(
                    409, "Thiếu báo giá đủ điều kiện cho tài sản."
                ) from None
            if quote["blocked"]:
                raise HTTPException(
                    409, "Lệnh đang chờ hoặc báo giá chưa đủ điều kiện."
                )
            review = next(
                (
                    r["date"]
                    for r in reversed(state["reviews"])
                    if r["status"] == "DUE" and r["target_id"] == target.id
                ),
                None,
            )
            decision = PaperDecision(
                portfolio_id=portfolio.id,
                target_id=target.id,
                created_at=now,
                expires_at=now + timedelta(minutes=15),
                revision=state["revision"],
                quote=quote
                | {
                    "source": frame["source"],
                    "as_of": frame["as_of"],
                    "target_version": target.portfolio_version,
                    "frame_hash": canonical_hash(frame),
                    "review": review,
                },
            )
            session.add(decision)
            session.flush()
            return dict(
                id=decision.id,
                target_id=target.id,
                quote_date=quote["date"],
                quote_source=frame["source"],
                quote_as_of=frame["as_of"],
                expires_at=decision.expires_at,
                drift=quote["drift"],
                estimated_fee_vnd=quote["estimated_cost"],
                orders=[display_order(o, frame) for o in quote["orders"]],
            )

    @app.post(base + "/decisions")
    def decide(portfolio_id: UUID, body: PaperAction, user_id=Depends(owner)):
        with sessions.begin() as session:
            portfolio, account, targets, target = load(session, portfolio_id, user_id)
            decision = session.scalar(
                select(PaperDecision).where(
                    PaperDecision.id == str(body.preview_id),
                    PaperDecision.portfolio_id == portfolio.id,
                )
            )
            if decision is None:
                raise HTTPException(404, "Không tìm thấy bản xem trước.")
            now = utcnow()
            status = reconcile(account, targets, now)
            if decision.action:
                if decision.action != body.action:
                    raise HTTPException(409, "Bản xem trước đã được xử lý.")
                return response(account, target, status)
            state = deepcopy(account.state)
            if (
                not target
                or target.id != decision.target_id
                or target.portfolio_version != portfolio.version
                or now >= aware(decision.expires_at)
                or decision.revision != state["revision"]
                or status != "FRESH"
                or canonical_hash(state["frame"]) != decision.quote["frame_hash"]
            ):
                raise HTTPException(
                    409, "Giá, mục tiêu hoặc tài khoản đã thay đổi. Hãy xem trước lại."
                )
            day = str(now.astimezone(VN).date())
            if body.action == "CONFIRM":
                ledger.confirm(
                    state["ledger"],
                    decision.quote,
                    decision_day=day,
                    reference=decision.id,
                )
                for order in decision.quote["orders"]:
                    state["orders"].append(
                        display_order(order, state["frame"])
                        | dict(
                            status="PENDING",
                            date=day,
                            preview_id=decision.id,
                            target_id=target.id,
                        )
                    )
            for review in state["reviews"]:
                if (
                    review["date"] == decision.quote["review"]
                    and review["status"] == "DUE"
                ):
                    review["status"] = (
                        "REVIEWED" if body.action == "CONFIRM" else "SKIPPED"
                    )
            decision.action, decision.decided_at = body.action, now
            state["decisions"].append(
                dict(
                    id=decision.id,
                    action=body.action,
                    decided_at=now.isoformat(),
                    target_id=target.id,
                    kind="MANUAL",
                    review=decision.quote["review"],
                )
            )
            state["revision"] += 1
            account.state = state
            return response(account, target, status)

    @app.post(base + "/reviews/{review_date}/skip")
    def skip_review(
        portfolio_id: UUID, review_date: date, body: StrictModel, user_id=Depends(owner)
    ):
        with sessions.begin() as session:
            _, account, targets, target = load(session, portfolio_id, user_id)
            status = reconcile(account, targets, utcnow())
            state = deepcopy(account.state)
            for review in state["reviews"]:
                if review["date"] == str(review_date):
                    if review["status"] == "REVIEWED":
                        raise HTTPException(409, "Kỳ xem xét đã được xử lý.")
                    if review["status"] == "DUE":
                        review["status"] = "SKIPPED"
                        state["revision"] += 1
                        account.state = state
                    return response(account, target, status)
            raise HTTPException(404, "Không tìm thấy kỳ xem xét.")
