"""Self-financing VND paper ledger. Mutations advance by observed market session."""

from datetime import date
from math import floor, isfinite, ulp


def new_account(capital):
    capital = float(capital)
    if not isfinite(capital) or capital <= 0:
        raise ValueError("Invalid paper capital")
    return dict(
        capital=capital,
        cash=capital,
        reserved=0.0,
        receivables=[],
        lots={},
        orders=[],
        date=None,
        session=0,
        fees=0.0,
        spread=0.0,
    )


def _price(prices, asset):
    value = prices.get(asset)
    if value is None or not isfinite(float(value)) or float(value) <= 0:
        raise ValueError(f"Missing valid price: {asset}")
    return float(value)


def _units(state, asset):
    return sum(lot["units"] for lot in state["lots"].get(asset, []))


def valuation(state, frame):
    positions = {}
    receivable = sum(p["net"] for p in state["receivables"])
    total = state["cash"] + state["reserved"] + receivable
    for asset in state["lots"]:
        qty = _units(state, asset)
        if qty:
            price = _price(frame["prices"], asset)
            positions[asset] = dict(units=qty, price=price, value=qty * price)
            total += qty * price
    for p in positions.values():
        p["weight"] = p["value"] / total
    pnl = total - state["capital"]
    return dict(
        total=total,
        cash=state["cash"],
        reserved=state["reserved"],
        receivable=receivable,
        positions=positions,
        pnl=pnl,
        pnl_pct=100 * pnl / state["capital"],
        fees=state["fees"],
        spread=state["spread"],
    )


def _gold(frame, side, *, eligible=False):
    prefix = (
        "eligible_"
        if eligible and ("eligible_gold_bid" in frame or "eligible_gold_ask" in frame)
        else ""
    )
    bid = _price(frame, prefix + "gold_bid")
    ask = _price(frame, prefix + "gold_ask")
    if ask < bid:
        raise ValueError("Crossed GOLD quote")
    return ask if side == "buy" else bid


def _sell_parts(state, asset, qty, day):
    parts = []
    for lot in state["lots"].get(asset, []):
        if lot["available"] > state["session"]:
            continue
        take = min(lot["units"], qty)
        if take > 0:
            age = (date.fromisoformat(day) - date.fromisoformat(lot["opened"])).days
            parts.append((lot, take, age))
            qty -= take
    return parts


def _trade(state, frame, asset, side, units, price, mark):
    parts = _sell_parts(state, asset, units, frame["date"]) if side == "sell" else []
    if side == "sell":
        units = sum(n for _, n, _ in parts)
    gross = units * price
    fee = tax = spread = 0.0
    if asset == "VFF":
        rates = frame.get("vff_fee_rates", (0.02, 0.005, 0.0))
        fee = sum(
            q * price * rates[0 if age < 365 else 1 if age < 730 else 2]
            for _, q, age in parts
        )
        tax = gross * 0.001 if side == "sell" else 0.0
    elif asset == "GOLD":
        spread = gross - units * mark if side == "buy" else units * mark - gross
    else:
        fee = gross * frame.get("stock_fee_bps", 10) / 10000
        tax = gross * 0.001 if side == "sell" else 0.0
    return dict(
        asset=asset,
        side=side,
        units=units,
        gross=gross,
        fee=fee,
        tax=tax,
        spread=spread,
    ), parts


def preview(state, weights, frame):
    if state["date"] != frame["date"]:
        raise ValueError("Preview date differs from last session")
    if (
        not weights
        or any(not isfinite(w) or w < 0 for w in weights.values())
        or abs(sum(weights.values()) - 1) > 1e-6
    ):
        raise ValueError("Invalid target weights")
    book = valuation(state, {**frame, "prices": frame["eligible"]})
    orders = []
    cash_weight = (book["cash"] + book["reserved"] + book["receivable"]) / book["total"]
    drift = cash_weight
    blocked = "PENDING_ORDERS" if state["orders"] else None
    if (
        state.get("last_vff_fill_date")
        and "eligible_vff_date" in frame
        and (frame["eligible_vff_date"] or "") < state["last_vff_fill_date"]
    ):
        blocked = "VFF_FILL_AWAITING_PUBLICATION"
    for asset in sorted(set(weights) | set(book["positions"])):
        held = book["positions"].get(asset, {})
        change = weights.get(asset, 0.0) - held.get("weight", 0.0)
        drift += abs(change)
        amount = abs(change) * book["total"]
        if amount < 1:
            continue
        side = "buy" if change > 0 else "sell"
        mark = _price(frame["eligible"], asset)
        price = mark
        if asset == "GOLD":
            try:
                price = _gold(frame, side, eligible=True)
            except ValueError:
                blocked = "MISSING_GOLD_QUOTE"
                continue
        units = amount / mark
        if asset == "VFF":
            if side == "buy" and amount < frame.get("vff_min_buy", 100000):
                continue
            units = floor(units * 100 + 1e-8) / 100
            if side == "sell":
                if units < 10:
                    continue
                if held["units"] - units < 10:
                    units = held["units"]
        trade, _ = _trade(state, frame, asset, side, units, price, mark)
        if trade["units"] > 0:
            if asset == "VFF" and side == "buy":
                trade["gross"] = amount
            orders.append(trade)
    return dict(
        date=frame["date"],
        total=book["total"],
        drift=drift / 2,
        orders=orders,
        estimated_cost=sum(t["fee"] + t["tax"] + t["spread"] for t in orders),
        blocked=blocked,
    )


def confirm(state, quote, decision_day=None, reference=None):
    if state["orders"] or quote["blocked"] or quote["date"] != state["date"]:
        raise ValueError("Stale or blocked paper preview")
    decision_day = decision_day or quote["date"]
    if date.fromisoformat(decision_day) < date.fromisoformat(quote["date"]):
        raise ValueError("Decision precedes quote")
    state["orders"] = [
        dict(
            t,
            submitted=state["session"],
            decision_day=decision_day,
            reference=reference,
        )
        for t in quote["orders"]
    ]


def advance(state, frame):
    day = frame["date"]
    weekday = date.fromisoformat(day).weekday()
    if state["date"] is not None and day <= state["date"]:
        raise ValueError("Sessions must be strictly increasing")
    if any(
        not isfinite(float(frame.get(k, d))) or frame.get(k, d) < 0
        for k, d in [
            ("stock_fee_bps", 10),
            ("stock_settlement", 2),
            ("vff_settlement", 5),
        ]
    ):
        raise ValueError("Invalid execution costs or settlement lag")
    valuation(state, frame)
    for o in state["orders"]:
        _price(frame["prices"], o["asset"])
    state["date"] = day
    state["session"] += 1
    index = state["session"]
    events = []

    def event(kind, **fields):
        events.append(dict(date=day, kind=kind, **fields))

    for asset, factor in frame.get("share_factors", {}).items():
        if not isfinite(factor) or factor <= 0 or asset in ("GOLD", "VFF"):
            raise ValueError("Invalid equity split factor")
        for lot in state["lots"].get(asset, []):
            lot["units"] *= factor
        for order in state["orders"]:
            if order["asset"] == asset:
                order["units"] *= factor
        if factor != 1 and _units(state, asset):
            event("split", asset=asset, factor=factor)
    due = [p for p in state["receivables"] if p["due"] <= index]
    for payment in due:
        state["cash"] += payment["net"]
        event("settle", **payment)
    state["receivables"] = [p for p in state["receivables"] if p["due"] > index]
    pending = []
    buys = []
    for order in sorted(state["orders"], key=lambda o: o["side"] == "buy"):
        asset, side = order["asset"], order["side"]
        if day <= order.get("decision_day", ""):
            order["submitted"] = index
            pending.append(order)
            continue
        age = index - order["submitted"]
        mark = _price(frame["prices"], asset)
        price = mark
        if asset == "VFF":
            exact = frame.get("vff_nav")
            dealing_session = age >= 2 and weekday in frame.get(
                "vff_dealing_weekdays", (1, 3)
            )
            if "vff_nav_date" in frame:
                # Forward publications can arrive after the economic dealing day.
                if dealing_session and "deal_date" not in order:
                    order.update(deal_date=day, deal_index=index)
                dealing_session = (
                    "deal_date" in order and order["deal_date"] == frame["vff_nav_date"]
                )
            tradable = (
                dealing_session
                and exact is not None
                and isfinite(float(exact))
                and float(exact) > 0
            )
            if not tradable:
                if age >= 5:
                    state["cash"] += state["reserved"]
                    state["reserved"] = 0.0
                    event(
                        "expire",
                        asset=asset,
                        side=side,
                        reference=order.get("reference"),
                    )
                elif age == 1 and side == "buy":
                    buys.append((order, None, mark))
                else:
                    pending.append(order)
                continue
            price = float(exact)
        elif asset == "GOLD":
            try:
                price = _gold(frame, side)
            except ValueError:
                price = None
            if not price or not frame.get("gold_tradable", True):
                event(
                    "skip",
                    asset=asset,
                    side=side,
                    reference=order.get("reference"),
                    reason="GOLD_UNAVAILABLE",
                )
                continue
        if side == "buy":
            buys.append((order, price, mark))
            continue
        deal_date = order.get("deal_date", day)
        trade, parts = _trade(
            state,
            {**frame, "date": deal_date},
            asset,
            side,
            order["units"],
            price,
            mark,
        )
        if not parts:
            event(
                "skip",
                asset=asset,
                side=side,
                reference=order.get("reference"),
                reason="NO_SETTLED_UNITS",
            )
            continue
        for lot, n, _ in parts:
            lot["units"] -= n
        state["lots"][asset] = [
            lot for lot in state["lots"][asset] if lot["units"] > 1e-12
        ]
        lag = (
            frame.get("vff_settlement", 5)
            if asset == "VFF"
            else 0
            if asset == "GOLD"
            else frame.get("stock_settlement", 2)
        )
        net = trade["gross"] - trade["fee"] - trade["tax"]
        settle_index = order.get("deal_index", index) + lag
        if settle_index > index:
            state["receivables"].append(
                dict(
                    asset=asset,
                    net=net,
                    due=settle_index,
                    reference=order.get("reference"),
                )
            )
        else:
            state["cash"] += net
        state["fees"] += trade["fee"] + trade["tax"]
        state["spread"] += trade["spread"]
        if asset == "VFF":
            state["last_vff_fill_date"] = deal_date
        event(
            "fill",
            **trade,
            reference=order.get("reference"),
            deal_date=deal_date,
            sold_lots=[
                dict(opened=lot["opened"], units=quantity, age_days=age)
                for lot, quantity, age in parts
            ],
        )
    # Reserve the fund subscription alongside the equity/gold buys. Never spend unsettled sales.
    needed = sum(
        o["gross"]
        if price is None
        else o["units"]
        * price
        * (
            1
            + (
                frame.get("stock_fee_bps", 10) / 10000
                if o["asset"] not in ("GOLD", "VFF")
                else 0
            )
        )
        for o, price, _ in buys
        if o["asset"] != "VFF" or price is None
    )
    scale = min(1.0, max(0.0, state["cash"]) / needed) if needed else 1.0
    # Each funded debit can round by a few ULPs at very large VND balances.
    rounding_tolerance = max(
        0.001, 3 * (len(buys) + 1) * ulp(state["cash"] + state["reserved"])
    )
    for o, price, mark in buys:
        asset = o["asset"]
        if price is None:
            amount = o["gross"] * scale
            if amount >= frame.get("vff_min_buy", 100000):
                state["cash"] -= amount
                state["reserved"] += amount
                pending.append(o)
                event(
                    "reserve",
                    asset=asset,
                    side="buy",
                    gross=amount,
                    reference=o.get("reference"),
                )
            else:
                event(
                    "skip",
                    asset=asset,
                    side="buy",
                    reference=o.get("reference"),
                    reason="MIN_SUBSCRIPTION",
                )
            continue
        if asset == "VFF":
            units = floor(state["reserved"] / price * 100) / 100
            state["cash"] += state["reserved"]
            state["reserved"] = 0.0
        else:
            units = o["units"] * scale
        if units <= 0:
            event(
                "skip",
                asset=asset,
                side="buy",
                reference=o.get("reference"),
                reason="NO_AVAILABLE_CASH",
            )
            continue
        trade, _ = _trade(state, frame, asset, "buy", units, price, mark)
        state["cash"] -= trade["gross"] + trade["fee"]
        state["fees"] += trade["fee"]
        state["spread"] += trade["spread"]
        lock = frame.get("stock_settlement", 2) if asset not in ("VFF", "GOLD") else 0
        state["lots"].setdefault(asset, []).append(
            dict(opened=o.get("deal_date", day), units=units, available=index + lock)
        )
        if asset == "VFF":
            state["last_vff_fill_date"] = o.get("deal_date", day)
        event(
            "fill",
            **trade,
            deal_date=o.get("deal_date", day),
            reference=o.get("reference"),
        )
    state["orders"] = pending
    if state["cash"] < -rounding_tolerance:
        raise ArithmeticError("Negative available cash")
    state["cash"] = max(0.0, state["cash"])
    return events
