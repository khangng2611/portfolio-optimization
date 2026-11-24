"""Score a sealed decision ledger against the common VNINDEX valuation calendar."""

from datetime import date

import numpy as np
import pandas as pd

from portfolio_contracts.hybrid import constraint_violations
from scripts.eval_hybrid_policy import FEE, GUARDRAILS, PROFILES, scores


VARIANTS = ("candidate", "regime_only", "v1", "bl_ml")
REGIMES = ("normal", "stress", "crisis")
CONSTRAINTS = {"defensive_asset_ids": ["VFF"], "min_defensive_weight": .15,
               "max_non_defensive_weight": .70, "max_position_weight": .50}


def _target(row, assets):
    if "assets" in row and row["assets"] != assets:
        raise ValueError(f"Decision asset order differs from valuation on {row['session']}")
    if row.get("timing_verified") is not True or row.get("regime") not in REGIMES:
        raise ValueError(f"Unverified decision timing or regime on {row['session']}")
    source = row.get("weights")
    if not isinstance(source, dict) or set(source) != set(PROFILES):
        raise ValueError(f"Incomplete profiles on {row['session']}")
    target = []
    for profile in PROFILES:
        variants = source[profile]
        if not isinstance(variants, dict) or set(variants) != set(VARIANTS):
            raise ValueError(f"Incomplete variants on {row['session']} for {profile}")
        vectors = []
        for key in VARIANTS:
            w = np.asarray(variants[key])
            if (w.shape != (len(assets),) or w.dtype.kind not in 'ifu'
                    or not np.isfinite(w).all() or constraint_violations(assets, w, CONSTRAINTS, tolerance=1e-8)):
                raise ValueError(f"Invalid {profile}/{key} weights on {row['session']}")
            vectors.append(w)
        # All variants share legs. Only normal-growth changes between candidate and v1.
        twin = 1 if profile == "growth" and row["regime"] == "normal" else 2
        if not np.allclose(vectors[0], vectors[twin], atol=1e-12, rtol=0):
            raise ValueError(f"Locked policy identity mismatch for {profile} on {row['session']}")
        target.append(vectors)
    return np.asarray(target, dtype=float)


def score(ledger, valuation, sessions, assets):
    """The caller seals provenance, settlement marks and the full evaluation calendar first."""
    if (len(sessions) < 2 or sessions != sorted(set(sessions))
            or any(date.fromisoformat(s).isoformat() != s for s in sessions)):
        raise ValueError("Expected ordered, unique ISO evaluation sessions")
    if (len(set(assets)) != len(assets) or "VFF" not in assets
            or not isinstance(valuation.index, pd.DatetimeIndex)
            or not valuation.index.is_unique or not valuation.columns.is_unique
            or not set(assets) <= set(valuation.columns)):
        raise ValueError("Invalid valuation universe or valuation index")
    marks = valuation.reindex(index=pd.to_datetime(sessions), columns=assets).to_numpy(dtype=float)
    if not np.isfinite(marks).all() or (marks <= 0).any():
        raise ValueError("Missing or invalid valuation marks on the common calendar")
    if [row.get("session") for row in ledger] != sessions[::5]:
        raise ValueError("Decision ledger must contain each scheduled cutoff in order, including HOLD")

    plans, decisions, missed = {}, [], []
    informative = 0
    for index, row in zip(range(0, len(sessions), 5), ledger, strict=True):
        session = row["session"]
        if row.get("status") == "HOLD":
            if not isinstance(row.get("reason"), str) or not row["reason"].strip() or row.get("weights"):
                raise ValueError(f"Expected HOLD reason without rebalancing targets on {session}")
            missed.append({"session": session, "reason": row["reason"]})
            continue
        if row.get("status") != "DECIDED":
            raise ValueError(f"Unknown decision status on {session}")
        target = _target(row, assets)
        regime = row["regime"]
        # Absence of the subsequent in-period close leaves that execution/return unobserved.
        execution = sessions[index + 1] if index + 1 < len(sessions) else None
        first_return = sessions[index + 2] if index + 2 < len(sessions) else None
        if execution:
            plans[execution] = regime, target
        distances = {}
        for p, profile in enumerate(PROFILES):
            distances[profile] = {
                key: float(.5 * np.abs(target[p, 0] - target[p, v]).sum())
                for v, key in enumerate(VARIANTS) if key != "candidate"
            }
        if first_return and regime == "normal" and distances["growth"]["v1"] > 1e-12:
            informative += 1
        decisions.append({"session": session, "regime": regime, "execution_session": execution,
                          "first_return_session": first_return, "target_half_l1_distance": distances})

    # weights include only risky assets; the residual starts in cash with zero yield.
    shape = (len(PROFILES), len(VARIANTS))
    weights = np.zeros((*shape, len(assets)))
    daily = np.zeros((len(sessions), *shape))
    traded = np.zeros_like(daily)
    active_regime = "cash"
    by_regime = {r: {"sessions_held": 0, "executions": 0, "net_factor": np.ones(shape)}
                 for r in (*REGIMES, "cash")}
    for i, session in enumerate(sessions):
        relative = marks[i] / marks[i - 1] if i else np.ones(len(assets))
        gross_factor = 1 + weights @ (relative - 1)
        weights = weights * relative / gross_factor[..., None]
        held = by_regime[active_regime]
        held["sessions_held"] += 1
        held["net_factor"] *= gross_factor
        net_factor = gross_factor
        if session in plans:
            active_regime, target = plans[session]
            cash = 1 - weights.sum(axis=-1)
            traded[i] = .5 * (np.abs(target - weights).sum(axis=-1) + np.abs(cash))
            fee_factor = 1 - FEE * traded[i]
            net_factor = gross_factor * fee_factor
            by_regime[active_regime]["net_factor"] *= fee_factor
            by_regime[active_regime]["executions"] += 1
            weights = target
        daily[i] = net_factor - 1

    profiles, checks, differences = {}, {}, {}
    for p, profile in enumerate(PROFILES):
        results = {}
        for v, key in enumerate(VARIANTS):
            results[key] = scores(daily[:, p, v], traded[:, p, v])
            results[key]["net_return_by_regime"] = {
                r: float(group["net_factor"][p, v] - 1) for r, group in by_regime.items()
            }
        profiles[profile] = results
        candidate, control = results["candidate"], results["regime_only"]
        vol_delta = candidate["annual_volatility"] - control["annual_volatility"]
        dd_delta = candidate["max_drawdown"] - control["max_drawdown"]
        primary_turnover = control["one_way_turnover"]
        differences[profile] = {
            "annual_volatility_increase": vol_delta, "drawdown_increase": dd_delta,
            "turnover_ratio": candidate["one_way_turnover"] / primary_turnover if primary_turnover else None,
            "net_return_difference": candidate["net_return"] - control["net_return"],
        }
        checks[profile] = {
            "volatility": vol_delta <= GUARDRAILS["annual_volatility_increase"],
            "drawdown": dd_delta <= GUARDRAILS["drawdown_increase"],
            "turnover": candidate["one_way_turnover"] <= GUARDRAILS["turnover_ratio"] * primary_turnover,
        }
    status = "PASS" if all(all(result.values()) for result in checks.values()) else "FAIL"
    if not informative:
        status = "INSUFFICIENT_EVIDENCE"
    return {
        "status": status, "session_count": len(sessions), "start_session": sessions[0],
        "end_session": sessions[-1], "fee_per_turnover": FEE, "guardrails": dict(GUARDRAILS),
        "profiles": profiles, "checks": checks, "candidate_minus_control": differences,
        "decisions": decisions, "missed_decisions": missed, "informative_normal_executions": informative,
        "regimes": {r: {"sessions_held": group["sessions_held"], "executions": group["executions"]}
                    for r, group in by_regime.items()},
    }
