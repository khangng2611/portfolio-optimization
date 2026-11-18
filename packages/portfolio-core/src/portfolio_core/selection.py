"""Pure deterministic candidate K5 selection; callers pin the price endpoint."""

from itertools import combinations
from numbers import Integral

import numpy as np

from .phase1_full import EQUITY_IDS


def candidate_distance_matrix(prices) -> np.ndarray:
    prices = np.asarray(prices, dtype=float)
    if (
        prices.ndim != 2
        or prices.shape[0] < 2
        or prices.shape[1] > 30
        or not np.isfinite(prices).all()
        or np.any(prices <= 0)
    ):
        raise ValueError(
            "Selection requires a finite positive ordered equity price panel"
        )
    n_assets = prices.shape[1]
    returns = prices[1:] / prices[:-1] - 1
    # Match pandas' pairwise Welford correlation, including zero-variance columns.
    correlation = np.zeros((n_assets, n_assets))
    for i in range(n_assets):
        for j in range(i + 1):
            mx = my = xx = yy = xy = 0.0
            for n, (x, y) in enumerate(zip(returns[:, i], returns[:, j]), 1):
                dx, dy = x - mx, y - my
                mx += dx / n
                my += dy / n
                xx += (x - mx) * dx
                yy += (y - my) * dy
                xy += (x - mx) * dy
            denominator = np.sqrt(xx * yy)
            value = xy / denominator if denominator > 0 else 0.0
            correlation[i, j] = correlation[j, i] = value
    distance = np.clip(1 - correlation, 0, 2)
    np.fill_diagonal(distance, 0)
    return distance


def select_candidate_equities(prices, ordered_equity_ids: list[str], k=5) -> list[str]:
    if (
        not isinstance(ordered_equity_ids, list)
        or any(not isinstance(a, str) for a in ordered_equity_ids)
        or len(set(ordered_equity_ids)) != len(ordered_equity_ids)
        or not set(ordered_equity_ids) <= set(EQUITY_IDS)
        or ordered_equity_ids != [a for a in EQUITY_IDS if a in ordered_equity_ids]
    ):
        raise ValueError(
            "Equity candidates must be unique and in canonical catalog order"
        )
    if isinstance(k, bool) or not isinstance(k, Integral) or not 1 <= k <= 5:
        raise ValueError("k must be between one and five")
    prices = np.asarray(prices, dtype=float)
    if (
        prices.ndim != 2
        or prices.shape[1] != len(ordered_equity_ids)
        or prices.shape[0] < 2
        or not np.isfinite(prices).all()
        or np.any(prices <= 0)
    ):
        raise ValueError("Prices must align with finite positive candidate history")
    if len(ordered_equity_ids) <= k:
        return ordered_equity_ids.copy()
    distance = candidate_distance_matrix(prices)
    best_cost = float("inf")
    best = tuple(range(k))
    for combo in combinations(range(len(ordered_equity_ids)), k):
        cost = np.cumsum(np.min(distance[:, combo], axis=1))[-1]
        if cost < best_cost:
            best_cost, best = cost, combo
    return [ordered_equity_ids[i] for i in best]


def candidate_regime(returns, t: int) -> dict:
    """Candidate-only 20/120 volatility and 60-session equal-weight drawdown."""
    returns = np.asarray(returns, dtype=float)
    if (
        returns.ndim != 2
        or not 1 <= returns.shape[1] <= 32
        or returns.shape[0] < 2
        or not np.isfinite(returns).all()
    ):
        raise ValueError("Regime requires a finite candidate return panel")
    if isinstance(t, bool) or not isinstance(t, Integral) or t < 2 or t > len(returns):
        raise ValueError("t must end a valid return history of at least two sessions")
    recent = returns[max(0, t - 20) : t].std(axis=0, ddof=1).mean()
    historical = returns[max(0, t - 120) : t].std(axis=0, ddof=1).mean()
    ratio = float(recent / historical) if historical > 0 else 1.0
    window = returns[max(0, t - 60) : t].mean(axis=1)
    cumulative = np.cumprod(1 + window)
    peak = np.maximum.accumulate(cumulative)[-1]
    drawdown = float(cumulative[-1] / peak - 1) if peak > 0 else 0.0
    state = (
        "crisis"
        if ratio >= 1.8 or drawdown <= -0.2
        else ("stress" if ratio >= 1.3 or drawdown <= -0.1 else "normal")
    )
    result = {
        "regime": state,
        "vol_ratio": ratio,
        "drawdown": drawdown,
        "equity_momentum": float(window.mean()),
    }
    if not all(
        np.isfinite(result[k]) for k in ("vol_ratio", "drawdown", "equity_momentum")
    ):
        raise ValueError("returns exceed the stable numerical range")
    return result


def effective_candidate_constraints(constraints, regime) -> dict:
    """Versioned custom mixed policy; caller retains the requested profile separately."""
    from .allocator import _fraction, _positive

    if not isinstance(constraints, dict):
        raise ValueError("A risk profile is required")
    state = regime.get("regime") if isinstance(regime, dict) else regime
    if state not in {"normal", "stress", "crisis"}:
        raise ValueError("Unknown candidate regime")
    return {
        "risk_aversion": max(
            _positive(constraints.get("risk_aversion"), "risk_aversion"),
            5.0 if state == "crisis" else 1.5,
        ),
        "max_position_weight": min(
            0.5,
            _fraction(
                constraints.get("max_position_weight"),
                "max_position_weight",
                positive=True,
            ),
        ),
        "defensive_asset_ids": ["VFF"],
        "min_defensive_weight": max(
            0.15,
            _fraction(constraints.get("min_defensive_weight"), "min_defensive_weight"),
        ),
        "max_non_defensive_weight": min(
            0.7,
            _fraction(
                constraints.get("max_non_defensive_weight"), "max_non_defensive_weight"
            ),
        ),
    }


def check_candidate_feasibility(ids, constraints, strategy) -> str | None:
    from .assets import canonical_candidates
    from .allocator import _policy, _residuals
    from .errors import CoreError

    try:
        ids = canonical_candidates(ids)
    except ValueError:
        return "INPUT_INVALID"
    if len(ids) < 2:
        return "INSUFFICIENT_ASSETS"
    if constraints is None:
        return "RISK_PROFILE_REQUIRED"
    if strategy not in {"EW", "MVO", "BL_ML"}:
        return "INPUT_INVALID"
    if "VFF" not in ids:
        return "DEFENSIVE_ASSET_REQUIRED"
    active = (
        ids
        if strategy != "BL_ML"
        else [
            a
            for a in ids
            if a not in EQUITY_IDS or a in [e for e in ids if e in EQUITY_IDS][:5]
        ]
    )
    try:
        policy = _policy(constraints, active)
        if (
            strategy == "EW"
            and max(_residuals(np.full(len(active), 1 / len(active)), policy).values())
            > 1e-13
        ):
            return "CONSTRAINTS_INFEASIBLE"
    except CoreError as error:
        return (
            "CONSTRAINTS_INFEASIBLE"
            if error.code == "infeasible_constraints"
            else "INPUT_INVALID"
        )
    return None
