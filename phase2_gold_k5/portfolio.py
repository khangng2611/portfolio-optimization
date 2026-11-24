"""Frozen BL allocations and next-close, self-financing portfolio paths."""
from dataclasses import dataclass
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from experiments_core.src.core import prior_posterior

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "extensions_C_v1"
INPUT = BASE / "inputs"
OPTIMIZER = HERE.parent / "trusted_baseline/backtest/_optimizer.py"
ARMS = {"B1": ("B1", None), "B2": ("B2", None), "B2_gold": ("B2", "gold"),
        "B2_derived": ("B2", "derived"), "B2_direct": ("B2", "direct"),
        "prior_derived": ("B1", "derived"), "prior_direct": ("B1", "direct")}
TOL = 1e-8


def load_optimizer():
    # Load just the byte-identical Step 2 solver, bypassing its legacy package initialization.
    if sha256(OPTIMIZER.read_bytes()).hexdigest() != '65fd5b54065a6c3ecef6f64caa1665c95ec033c85003d245c81f3bdd470120a9':
        raise ValueError("Frozen optimizer source mismatch")
    spec = importlib.util.spec_from_file_location("gold_k5_frozen_optimizer", OPTIMIZER)
    solver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(solver)
    if (solver.optimize_weight_ranking.__defaults__ != (1.5, .5, .15, .7, ["VFF"])
            or solver.MIN_WEIGHT_THRESHOLD != .01):
        raise ValueError("Optimizer config differs from the accepted Step 2 configuration")
    return solver


def view_row(names, view):
    if len(set(names)) != 7 or len(names) != 7 or not {"GOLD", "VFF"} <= set(names):
        raise ValueError("Expected five distinct stocks, GOLD and VFF")
    if view not in ("gold", "derived", "direct"):
        raise ValueError(f"Unknown view {view}")
    return [1. if a == "GOLD" else 0. if a == "VFF" or view == "gold" else -.2 for a in names]


@dataclass
class Allocation:
    active: np.ndarray
    mu: np.ndarray
    covariance: np.ndarray
    target: np.ndarray


def allocations(out, columns, calendar):
    solver = load_optimizer()
    forecasts = pd.read_csv(out / "forecasts.csv", parse_dates=["date"]).set_index(["date", "view"], verify_integrity=True)
    files = {"B1": "B1_BLnoML", "B2": "B2_BLML"}
    audits, targets = {}, {}
    for base, prefix in files.items():
        audits[base] = pd.read_csv(INPUT / f"{prefix}_posterior_audit.csv", parse_dates=["decision_date"]).set_index("decision_date")
        targets[base] = pd.read_csv(INPUT / f"{prefix}_weights.csv", parse_dates=["decision_date"],
                                    float_precision="round_trip").pivot(index="decision_date", columns="asset", values="target_weight")[columns]
        if not (audits[base].index.equals(calendar.index) and targets[base].index.equals(calendar.index)):
            raise ValueError(f"Dated {base} input misalignment")
    evidence = []
    by_arm = {arm: {} for arm in ARMS}
    for date, event in calendar.iterrows():
        base_inputs = {}
        menu = [event[f"ticker_{i}"] for i in range(1, 6)] + ["GOLD", "VFF"]
        for base, audit in audits.items():
            r = audit.loc[date]
            names, p, q, conf = (json.loads(r[key]) for key in ("assets", "P", "Q", "confidence"))
            if names != menu or pd.Timestamp(r.information_end) > date or pd.Timestamp(r.selection_information_end) >= date:
                raise ValueError(f"Invalid dated menu or information cutoff: {base} {date}")
            sigma = np.array(json.loads(r.covariance))
            active = columns.get_indexer(names)
            if (active < 0).any():
                raise ValueError("Unknown asset in frozen menu")
            mu = prior_posterior(sigma, 2.5, .05, p, q, conf)
            target = targets[base].loc[date].to_numpy()
            resolved = solver.optimize_weight_ranking(mu, sigma, names, risk_aversion=1.5)
            error = np.max(np.abs(target[active] - resolved))
            if (error > 1e-8 or not np.allclose(mu, json.loads(r.mu), atol=1e-12, rtol=0)
                    or np.sum(np.abs(np.delete(target, active))) > TOL):
                raise ValueError(f"Frozen posterior or solver parity failure: {base} {date}, {error}")
            base_inputs[base] = (p, q, conf, mu, target, error)
        if audits["B1"].at[date, "covariance"] != audits["B2"].at[date, "covariance"]:
            raise ValueError("Unmatched base covariance")
        regularized = solver._regularize_covariance(sigma)
        for arm, (base, view) in ARMS.items():
            p, q, conf, mu, target, error = base_inputs[base]
            has_view = False
            if view is not None and (date, view) in forecasts.index:
                forecast = forecasts.loc[(date, view)]
                if pd.notna(forecast.q_daily):
                    if not (np.isfinite(forecast.q_daily) and 0 < forecast.confidence <= 1):
                        raise ValueError(f"Invalid forecast {date} {view}")
                    p = p + [view_row(names, view)]
                    q, conf = q + [forecast.q_daily], conf + [forecast.confidence]
                    mu = prior_posterior(sigma, 2.5, .05, p, q, conf)
                    target = np.zeros(len(columns))
                    target[active] = solver.optimize_weight_ranking(mu, sigma, names, risk_aversion=1.5)
                    has_view = True
            if not feasible(target, active, columns.get_loc("VFF")):
                raise ValueError(f"Infeasible {arm} target on {date}")
            by_arm[arm][int(event.decision_index)] = Allocation(active, mu, regularized, target)
            evidence.append(dict(decision_date=date, arm=arm, base=base, extra_view=view, extra_view_used=has_view,
                                 assets=json.dumps(names), P=json.dumps(p), Q=json.dumps(q), confidence=json.dumps(conf),
                                 mu=json.dumps(mu.tolist()), target=json.dumps(target[active].tolist()),
                                 base_target_max_abs_error=error))
    pd.DataFrame(evidence).to_csv(out / "allocations.csv", index=False)
    return by_arm


def feasible(w, active, vff):
    selected = w[active]
    return bool(np.isfinite(w).all() and abs(selected.sum()-1) <= TOL and w.min() >= -TOL
                and w.max() <= .5+TOL and w[vff] >= .3-TOL and np.sum(w)-w[vff] <= .7+TOL
                and np.abs(np.delete(w, active)).sum() <= TOL)


def rebalance(units, cash, mark, target, gold, bid, ask, rate):
    """Target fractions of NAV *after* spending the actual cash on both sides."""
    if not (0 < bid <= ask and np.isclose(mark[gold], (bid+ask)/2, rtol=1e-12, atol=0)
            and 0 <= rate < 1):
        raise ValueError("Invalid execution price, midpoint or cost")
    value = units * mark
    gross_nav = value.sum() + cash
    pre = value / gross_nav
    rates = np.full(len(mark), rate, dtype=float)
    rates[gold] = (ask-bid)/(ask+bid)
    fraction = brentq(lambda f: f + np.abs(f*target-pre) @ rates - 1., 0., 1., xtol=5e-15)
    new_units = fraction*gross_nav*target/mark
    delta = new_units-units
    trading_price = mark.copy()
    trading_price[gold] = ask if delta[gold] >= 0 else bid
    gold_cost = delta[gold]*(trading_price[gold]-mark[gold])
    other_cost = rate*np.delete(np.abs(delta*mark), gold).sum()
    new_cash = cash-delta @ trading_price-other_cost
    if abs(new_cash) > 1e-11*gross_nav or not np.isclose(
            gross_nav-gold_cost-other_cost, fraction*gross_nav, atol=1e-11*gross_nav, rtol=0):
        raise ValueError("Execution cash failed to reconcile")
    return new_units, new_cash, gold_cost, other_cost


@dataclass
class Market:
    dates: pd.DatetimeIndex
    names: pd.Index
    marks: np.ndarray
    eligible: np.ndarray
    quotes: np.ndarray  # bid, ask, known_bid, known_ask
    vff_observed: np.ndarray


def known_weights(market, now, last_fill, last_target, vff):
    if last_fill is None:
        return np.zeros(len(market.names))
    # Prior target is known regardless of realized fill NAV. Only measure VFF
    # drift over observations already visible at this decision.
    reference = market.marks[last_fill].copy()
    last_known = np.searchsorted(market.vff_observed[:now+1], market.dates[last_fill].to_datetime64(), side="right")-1
    if last_known < 0:
        raise ValueError("Missing eligible VFF fill basis")
    reference[vff] = market.eligible[last_known, vff]
    values = last_target * market.eligible[now] / reference
    return values/values.sum()


def sparse_weights(names, values):
    return json.dumps({names[i]: float(values[i]) for i in np.flatnonzero(values)}, separators=(",", ":"))


def simulate(market, decisions, arm, gate, bps):
    gold, vff = (market.names.get_loc(a) for a in ("GOLD", "VFF"))
    rate = bps/10000
    units = np.zeros(len(market.names))
    cash = prior_nav = 1.
    last_fill = last_target = None
    records, daily = [], []
    for i in range(min(decisions)+1, len(market.dates)):
        mark = market.marks[i]
        if i-1 in decisions:
            d = i-1
            allocation = decisions[d]
            active, target = allocation.active, allocation.target
            known = known_weights(market, d, last_fill, last_target, vff)
            known_bid, known_ask = market.quotes[d, 2:]
            rates = np.full(len(target), rate)
            rates[gold] = (known_ask-known_bid)/(known_ask+known_bid)
            expected_cost = np.abs(known-target) @ rates
            mandatory = not feasible(known, active, vff)
            gain = np.nan
            if not mandatory:
                old, new = known[active], target[active]
                gain = 5*((new-old) @ allocation.mu - 1.5*(new @ allocation.covariance @ new
                                                          - old @ allocation.covariance @ old))
            order = not gate or mandatory or gain > expected_cost
            bid, ask = market.quotes[i, :2]
            gross_nav = cash+units @ mark
            pre = units*mark/gross_nav
            cash_before, initial = cash, last_fill is None
            delta = np.zeros(len(units))
            gold_cost = other_cost = 0.
            if not np.isfinite([bid, ask]).all():
                status = "missing_quote"
            elif order:
                status = "executed"
                new_units, cash, gold_cost, other_cost = rebalance(units, cash, mark, target, gold, bid, ask, rate)
                delta = new_units-units
                units, last_fill, last_target = new_units, i, target
            else:
                status = "gate_hold"
            post = units*mark/(cash + units @ mark)
            if status == "executed" and not np.allclose(post, target, atol=1e-11, rtol=0):
                raise ValueError("Post-trade allocation mismatch")
            rows = dict(date=market.dates[i], decision_date=market.dates[d], execution_date=market.dates[i],
                        arm=arm, gate=gate, bps=bps, status=status, order_at_decision=order, mandatory=mandatory,
                        initial_allocation=initial and status=="executed", utility_gain=gain, expected_cost=expected_cost,
                        turnover=np.abs(post-pre).sum()/2, traded_notional=np.abs(delta*mark).sum()/gross_nav,
                        gold_cost=gold_cost, other_cost=other_cost, gold_weight_change=post[gold]-pre[gold],
                        gold_units_change=delta[gold], known_bid=known_bid, known_ask=known_ask,
                        bid=bid, ask=ask, cash_before=cash_before, cash_after=cash, nav_before=gross_nav,
                        nav_after=cash+units @ mark)
            for key, weights in (("known_weights", known), ("pre_weights", pre), ("target", target),
                                 ("post_weights", post), ("units_after", units)):
                rows[key] = sparse_weights(market.names, weights)
            records.append(rows)
        nav = cash + units @ mark
        daily.append((market.dates[i], arm, gate, bps, nav/prior_nav-1., nav))
        prior_nav = nav
    return daily, records


def portfolios(out: Path):
    def panel(name):
        return pd.read_csv(INPUT / (name+".csv"), parse_dates=["date"], float_precision="round_trip").set_index("date")
    marks = panel("prices_valuation")
    eligible = panel("prices_eligible")
    quotes = pd.read_csv(out / "gold_quotes.csv", parse_dates=["date"]).set_index("date")
    if (not marks.index.equals(quotes.index) or not marks.index.equals(eligible.index)
            or not marks.columns.equals(eligible.columns) or not marks.index.is_unique or not marks.index.is_monotonic_increasing):
        raise ValueError("Misaligned quote or eligible-price calendar")
    for bid, ask in [("bid", "ask"), ("archive_bid", "archive_ask"), ("known_bid", "known_ask")]:
        pair = quotes[[bid, ask]].dropna()
        if (len(pair) != len(quotes) and bid != "bid" or quotes[bid].isna().ne(quotes[ask].isna()).any()
                or not np.isfinite(pair).all().all() or (pair[bid] <= 0).any() or (pair[bid] > pair[ask]).any()):
            raise ValueError(f"Missing or invalid {bid}/{ask} pair")
    marks["GOLD"] = (quotes.archive_bid + quotes.archive_ask)/2
    eligible["GOLD"] = (quotes.known_bid + quotes.known_ask)/2
    if not (np.isfinite(marks) & marks.gt(0) & np.isfinite(eligible) & eligible.gt(0)).all().all():
        raise ValueError("Invalid daily price")
    equity = marks.columns.difference(["VFF", "GOLD"])
    if not np.allclose(marks[equity], eligible[equity], rtol=1e-14, atol=0):
        raise ValueError("Prior equity fills require same-session eligible prices")
    ledger = pd.read_csv(INPUT / "availability_ledger.csv", usecols=["asset","observed_at","session_date","price"],
                         parse_dates=["session_date"], float_precision="round_trip")
    ledger = ledger[ledger.asset == "VFF"].set_index("session_date")
    observed = pd.to_datetime(ledger.observed_at, utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None).dt.normalize()
    if (not observed.index.equals(marks.index) or not observed.is_monotonic_increasing
            or not np.array_equal(ledger.price, eligible.VFF)):
        raise ValueError("Invalid VFF decision basis")
    market = Market(marks.index, marks.columns, marks.to_numpy(), eligible.to_numpy(),
                    quotes[["bid", "ask", "known_bid", "known_ask"]].to_numpy(), observed.to_numpy())
    calendar = pd.read_csv(BASE / "selected_k5_events.csv", parse_dates=["decision_date","assumed_execution_date"]).set_index("decision_date")
    indices = calendar.decision_index.to_numpy()
    if not (marks.index[indices].equals(calendar.index) and np.array_equal(marks.index[indices+1], calendar.assumed_execution_date)):
        raise ValueError("Invalid decision/execution mapping")
    allocation = allocations(out, marks.columns, calendar)
    costs = json.loads((HERE / "protocol.json").read_text())["cost_grid_bps"]
    first = True
    for arm, decisions in allocation.items():
        for gate in (False, True):
            for bps in costs:
                daily, records = simulate(market, decisions, arm, gate, bps)
                mode = "w" if first else "a"
                pd.DataFrame(daily, columns=["date","arm","gate","bps","return","nav"]).to_csv(
                    out / "daily.csv", index=False, mode=mode, header=first)
                pd.DataFrame(records).to_csv(out / "trades.csv", index=False, mode=mode, header=first)
                first = False
