"""Score exported HYBRID GOLD–K5 paper decisions against contemporaneous source archives."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from experiments_core.src.core import bootstrap_effects, return_stats
from market_service.hybrid_forward_capture import VIETNAM
from phase2_gold_k5.portfolio import rebalance
from portfolio_contracts import canonical_hash
from portfolio_contracts.assets import EQUITY_IDS, candidate_hash
from scripts.gold_shadow_marks import Captures, CaptureUnavailable

ARMS = ("production", "shadow")
CONTEXT = ("series_id", "view_protocol", "policy_version", "risk_profile", "selection_policy_id",
           "applied_selection", "data_policy_id", "constraints_hash", "candidate_hash")
STUDY_ID = "gold-k5-derived-hybrid-shadow-v1"
PROTOCOL_SHA256 = "8227f058373339b5f8a133598404bcc82e1c8c327528bea66129d57be0f747d3"
REGISTERED_AT = datetime.fromisoformat("2026-11-24T09:34:00+00:00")
FEE = .001


def aware(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("Timezone required")
    return stamp


def targets(row):
    names = row["asset_ids"]
    k5 = row["selected_equity_ids"]
    if (candidate_hash(names) != row["candidate_hash"] or "GOLD" not in names
            or len(k5) != 5 or len(set(k5)) != 5 or not set(k5) <= set(EQUITY_IDS).intersection(names)
            or row["view_protocol"] != "gold-k5-derived-v1" or row["horizon_sessions"] != 5
            or row["execution_lag_sessions"] != 1):
        raise ValueError("Invalid matched asset, horizon or view contract")
    weights = {}
    for arm in ARMS:
        values = np.asarray(row[f"{arm}_weights"])
        if (values.shape != (len(names),) or values.dtype.kind not in "fiu" or not np.isfinite(values).all()
                or values.min() < 0 or abs(values.sum() - 1.) > 1e-8):
            raise ValueError("Invalid paired weights")
        weights[arm] = dict(zip(names, values.tolist(), strict=True))
    return weights


def trade(position, target, mark):
    units, cash = position
    assets = [a for a in target if target[a] > 0 or units.get(a, 0.) > 0 or a == "GOLD"]
    before = np.array([units.get(a, 0.) for a in assets])
    prices = np.array([mark["prices"][a] for a in assets])
    nav = cash + before @ prices
    after, cash, spread, fee = rebalance(before, cash, prices, np.array([target[a] for a in assets]),
                                          assets.index("GOLD"), mark["bid"], mark["ask"], FEE)
    # The cash leg makes a first purchase from all-cash a full one-way rebalance.
    pre = before * prices / nav
    end_nav = cash + after @ prices
    post = after * prices / end_nav
    turnover = (np.abs(post - pre).sum() + abs(cash / end_nav - (1 - pre.sum()))) / 2
    fill = dict(nav_before=nav, nav_after=end_nav, pre_weights=dict(zip(assets, pre, strict=True)),
                post_weights=dict(zip(assets, post, strict=True)), turnover=turnover,
                traded_notional=np.abs((after - before) * prices).sum() / nav,
                gold_spread_cost=spread / nav, non_gold_fee=fee / nav)
    return (dict(zip(assets, after, strict=True)), cash), fill


def delta(paths):
    values = [return_stats(paths[:, i])["sharpe"] for i in (0, 1)]
    return float(values[1] - values[0]) if np.isfinite(values).all() else None


def assessment(mature, censored=()):
    result = dict(status="INSUFFICIENT_EVIDENCE", mature_dates=len(mature), required_dates=60)
    if not mature:
        return result
    # The first confirmatory comparison is frozen at 60 dates; subsequent outcomes remain descriptive.
    sample = mature[:60]
    paths = np.array([[event["arms"][arm]["daily_returns"] for arm in ARMS] for event in sample])
    daily = paths.transpose(0, 2, 1).reshape(-1, 2)
    result.update(sample_start=sample[0]["decision_session"], sample_end=sample[-1]["decision_session"],
                  paired_sessions=len(daily), net_sharpe_delta=delta(daily))
    result["arms"] = {}
    for index, arm in enumerate(ARMS):
        stats = return_stats(daily[:, index])
        result["arms"][arm] = {
            "net_return_over_observed_windows": stats["final_nav"] - 1,
            "net_sharpe": stats["sharpe"] if np.isfinite(stats["sharpe"]) else None,
            "max_drawdown_over_observed_windows": stats["max_drawdown"],
            "sum_one_way_turnover": sum(e["arms"][arm]["turnover"] for e in sample),
            "sum_gold_spread_cost_nav_fractions": sum(e["arms"][arm]["gold_spread_cost"] for e in sample),
            "sum_non_gold_fee_nav_fractions": sum(e["arms"][arm]["non_gold_fee"] for e in sample),
        }
    blocks = [daily[i:i+100] for i in range(0, len(daily), 100)]
    result["complete_20_date_blocks"] = [delta(block) for block in blocks if len(block) == 100]
    result["censored_executions_through_sample_end"] = [
        e["job_id"] for e in censored if e["decision_session"] <= result["sample_end"]]
    if len(sample) < 60:
        return result
    effect = next(r for r in bootstrap_effects(daily[:, 1], daily[:, 0]) if r["metric"] == "sharpe")
    interval = [effect["ci_low"], effect["ci_high"]]
    leave = [delta(np.concatenate([block for j, block in enumerate(blocks) if j != i])) for i in range(3)]
    result.update(ci_95=interval if np.isfinite(interval).all() else None, leave_one_block_out_delta=leave,
                  bootstrap_block_observed_sessions=10, bootstrap_replicates=1000, bootstrap_seed=20261014)
    values = [result["net_sharpe_delta"], *(result["ci_95"] or [None]), *leave, *result["complete_20_date_blocks"]]
    if all(v is not None for v in values) and not result["censored_executions_through_sample_end"]:
        passes = (result["net_sharpe_delta"] > 0 and interval[0] > 0 and min(leave) > 0
                  and sum(v > 0 for v in result["complete_20_date_blocks"]) >= 2)
        result["status"] = "MEETS_RESEARCH_CRITERIA" if passes else "CRITERIA_NOT_MET"
    return result


def score_context(rows, market):
    positions = {arm: ({}, 1.) for arm in ARMS}
    sessions = market.sessions
    indices = {day: i for i, day in enumerate(sessions)}
    last_selected = -5
    broken_at = previous_fill = None
    events = []
    for row in sorted(rows, key=lambda r: (r["decision_session"], r["witnessed_at_epoch"], r["job_id"])):
        day = row["decision_session"]
        event = dict(job_id=row["job_id"], decision_session=day, issued_at=row["issued_at"], witnessed_at=row["witnessed_at"], status="PENDING")
        events.append(event)
        if row["status"] == "ABSTAIN":
            event.update(status="ABSTAIN", reason=row.get("reason"))
            continue
        if row["status"] != "TARGET":
            raise ValueError("Unknown decision status")
        weights = targets(row)
        if aware(row["issued_at"]) <= REGISTERED_AT:
            event.update(status="INELIGIBLE", reason="issued_on_or_before_registration")
            continue
        if day not in indices or indices[day] + 1 >= len(sessions):
            if sessions and day < sessions[-1] and day not in indices:
                event.update(status="INELIGIBLE", reason="decision_date_not_in_observed_calendar")
            else:
                event.update(reason="decision_or_execution_session_unconfirmed")
            continue
        i = indices[day]
        opens = datetime.combine(date.fromisoformat(sessions[i + 1]), time(9), VIETNAM)
        issued, cutoff = aware(row["issued_at"]), aware(row["decision_at"])
        witness = aware(row["witnessed_at"])
        enrolled = aware(row["enrolled_at"])
        committed = aware(row["registered_at"])
        if (not REGISTERED_AT <= enrolled <= cutoff <= issued or not enrolled <= committed <= issued
                or issued < datetime.combine(date.fromisoformat(day), time(15), VIETNAM)
                or witness >= min(opens, aware(row["issue_before"]), aware(row["valid_until"]))):
            event.update(status="INELIGIBLE", reason="outside_prospective_issue_window")
            continue
        if i < last_selected + 5:
            event.update(status="DUPLICATE_DATE" if i == last_selected else "OVERLAPPING_WINDOW")
            continue
        last_selected = i
        event["execution_session"] = sessions[i + 1]
        if i + 6 < len(sessions):
            event["exit_session"] = sessions[i + 6]
        if broken_at:
            event.update(status="UNRESOLVED", reason=f"prior_entry_unresolved:{broken_at}")
            continue
        # A sale requires the old position's entry mark. Only post-trade holdings need subsequent marks.
        holding_assets = {a for w in weights.values() for a, value in w.items() if value > 0} | {"GOLD"}
        entry_assets = holding_assets | {a for units, _ in positions.values() for a, value in units.items() if value > 0}
        if i + 1 + (5 if "VFF" in entry_assets else 0) >= len(sessions):
            event.update(reason="awaiting_execution_and_vff_vintage")
            continue
        try:
            start = market.mark(i + 1, entry_assets, previous_fill)
        except CaptureUnavailable as exc:
            broken_at = day
            event.update(status="UNRESOLVED", reason=str(exc))
            continue
        event["entry_quote"] = {key: start[key] for key in ("day", "bid", "ask", "provider_carry_flag")}
        if start["provider_carry_flag"]:
            event.update(status="NON_EXECUTABLE", reason="provider_flagged_entry_quote")
            continue
        event["arms"] = {}
        for arm in ARMS:
            units, cash = positions[arm]
            units = {a: u * start["share_factors"].get(a, 1.) for a, u in units.items()}
            positions[arm], event["arms"][arm] = trade((units, cash), weights[arm], start)
        previous_fill = start
        if i + 6 + (5 if "VFF" in holding_assets else 0) >= len(sessions):
            event.update(reason="awaiting_exit_vff_vintage")
            continue
        try:
            # K5 labels need endpoints even for selected equities with zero portfolio weight.
            selected = set(row["selected_equity_ids"])
            label_basis = market.mark(i + 1, selected) if selected - entry_assets else start
            basis = start | {"prices": start["prices"] | label_basis["prices"]}
            marks = [market.mark(j, holding_assets, basis) for j in range(i+2, i+6)]
            marks.append(market.mark(i+6, holding_assets | selected, basis))
        except CaptureUnavailable as exc:
            event.update(status="UNRESOLVED", reason=str(exc))
            continue
        end = marks[-1]
        event["exit_quote"] = {key: end[key] for key in ("day", "bid", "ask", "provider_carry_flag")}
        if end["provider_carry_flag"]:
            event.update(status="NON_EXECUTABLE", reason="provider_flagged_exit_quote")
            continue
        event["valuation_vintages"] = [{k: m[k] for k in ("day", "nav_date", "nav_vintage")} for m in [start, *marks]]
        for arm in ARMS:
            units, cash = positions[arm]
            fill = event["arms"][arm]
            navs = np.array([fill["nav_before"], *(cash + sum(u * m["prices"][a] * m["share_factors"].get(a, 1.) for a, u in units.items())
                                                   for m in marks)])
            fill.update(daily_returns=(navs[1:] / navs[:-1] - 1).tolist(), net_return=navs[-1] / navs[0] - 1)
        spread = end["ask"] / start["ask"] - np.mean([end["prices"][a] * end["share_factors"][a] / basis["prices"][a]
                                                     for a in row["selected_equity_ids"]])
        event.update(status="MATURE", realized_spread_5d=spread,
                     forecast_error_5d=row["forecast"]["prediction_5d"] - spread)
    mature = [e for e in events if e["status"] == "MATURE"]
    filled = [e for e in events if "arms" in e]
    totals = {}
    for arm in ARMS:
        fills = [e["arms"][arm] for e in filled]
        totals[arm] = dict(executions=len(fills), sum_one_way_turnover=sum(f["turnover"] for f in fills),
                           sum_gold_spread_cost_nav_fractions=sum(f["gold_spread_cost"] for f in fills),
                           sum_non_gold_fee_nav_fractions=sum(f["non_gold_fee"] for f in fills))
    censored = [e for e in filled if e["status"] != "MATURE"]
    return dict(context={k: rows[0][k] for k in CONTEXT}, events=events, all_fills=totals,
                counts=dict(Counter(e["status"] for e in events)), assessment=assessment(mature, censored))


def report(rows, market, as_of):
    groups = defaultdict(list)
    seen = {}
    abstentions = []
    duplicates = 0
    excluded_future = 0
    for row in rows:
        if row.get("receipt_sha256") != canonical_hash({key: val for key, val in row.items() if key != "receipt_sha256"}):
            raise ValueError("Decision receipt hash mismatch")
        job = row["job_id"]
        if job in seen:
            if seen[job] != row:
                raise ValueError(f"Conflicting immutable receipts for job {job}")
            duplicates += 1
            continue
        seen[job] = row
        if row.get("study_id") != STUDY_ID or row.get("protocol_sha256") != PROTOCOL_SHA256:
            raise ValueError("Decision study or protocol hash mismatch")
        stamp = aware(row["witnessed_at"])
        issued = aware(row["issued_at"])
        if issued > stamp and row["status"] != "ABSTAIN":
            raise ValueError("Receipt witness precedes issuance")
        if max(stamp, issued) > as_of:
            excluded_future += 1
            continue
        if row["status"] == "ABSTAIN" and not all(row.get(k) for k in (*CONTEXT, "decision_session")):
            abstentions.append(dict(job_id=job, reason=row.get("reason")))
            continue
        if not all(isinstance(row.get(k), str) and row[k] for k in CONTEXT):
            raise ValueError("Missing proposal context")
        groups[tuple(row[k] for k in CONTEXT)].append(row | {"witnessed_at_epoch": stamp.timestamp()})
    cohorts = [score_context(groups[k], market) for k in sorted(groups)]
    return dict(schema_version=1, status="PER_CONTEXT_ASSESSMENTS" if cohorts else "INSUFFICIENT_EVIDENCE",
                study_id=STUDY_ID, protocol_sha256=PROTOCOL_SHA256, as_of=as_of.isoformat(), context_count=len(cohorts),
                mature_context_dates=sum(c["assessment"]["mature_dates"] for c in cohorts),
                duplicate_exports=duplicates, excluded_after_as_of=excluded_future, unassigned_abstentions=abstentions,
                cohorts=cohorts, source_receipts=market.provenance, calendar_errors=market.calendar_errors,
                execution_policy=dict(gold="SJC HCM dated midpoint valuation, buy ask/sell bid; flagged endpoints ineligible",
                                      vff="weekly NAV <=7 calendar days old, economic vintage D+5 VNINDEX sessions",
                                      equities="KBS provider-adjusted share-equivalents reconciled to each vintage",
                                      non_gold_bps_per_side=10, annual_risk_free_rate=.06, holding_sessions=5,
                                      continuity="paper units carried within cohort; initial cash, no terminal liquidation",
                                      inference="first 60 nonoverlapping mature dates per context; bootstrap in observed-session order"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", required=True, help="immutable decision JSONL export, or - for stdin")
    parser.add_argument("--captures", type=Path, default=Path("output/hybrid-mvo60-forward"))
    parser.add_argument("--as-of", type=aware)
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    as_of = args.as_of or now
    if as_of > now:
        parser.error("--as-of must be in the past")
    data = sys.stdin.buffer.read() if args.decisions == "-" else Path(args.decisions).read_bytes()
    result = report([json.loads(line) for line in data.splitlines() if line.strip()], Captures(args.captures, as_of), as_of)
    result["export_sha256"] = hashlib.sha256(data).hexdigest()
    print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
