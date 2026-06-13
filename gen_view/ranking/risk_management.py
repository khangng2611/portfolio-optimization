"""
Risk Management for Ranking-Based Portfolio
============================================

Provides market regime detection and defensive view generation to protect
the ranking-based portfolio during market stress and crisis periods.

Regime Classification:
    - Normal: vol_ratio < 1.3, drawdown > -10%
    - Stress: vol_ratio >= 1.3 OR drawdown <= -10%
    - Crisis: vol_ratio >= 1.8 OR drawdown <= -20%

Defensive Mechanism:
    During stress/crisis, inject explicit views favoring Gold and MBBOND
    over stocks with high confidence, shifting the BL posterior toward safety.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    RANKING_DEFAULT_DEFENSIVE_ASSETS,
    RANKING_DRAWDOWN_LOOKBACK,
    RANKING_DRAWDOWN_STRESS_THRESHOLD,
    RANKING_DRAWDOWN_CRISIS_THRESHOLD,
    RANKING_DEFENSIVE_CONFIDENCE,
    RANKING_VOL_DAMPENER_THRESHOLD,
    RANKING_VOL_DAMPENER_SEVERE,
    TRADING_DAYS_PER_YEAR,
)


def detect_market_regime(
    returns: pd.DataFrame,
    t: int,
    lookback: int = RANKING_DRAWDOWN_LOOKBACK,
) -> dict:
    """
    Detect current market regime from recent returns.

    Uses two signals:
    1. Volatility ratio: recent (20-day) vs historical (120-day) volatility
    2. Drawdown: current NAV vs peak over lookback window

    Parameters
    ----------
    returns : pd.DataFrame
        Full returns DataFrame (rows=dates, columns=assets)
    t : int
        Current time index in returns
    lookback : int
        Lookback window for drawdown computation

    Returns
    -------
    dict with keys:
        - regime: "normal" | "stress" | "crisis"
        - vol_ratio: float (recent_vol / historical_vol)
        - drawdown: float (negative, current drawdown from peak)
        - equity_momentum: float (mean return over lookback)
    """
    # Volatility ratio: 20-day vs 120-day
    recent_start = max(0, t - 20)
    hist_start = max(0, t - 120)

    recent_vol = returns.iloc[recent_start:t].std().mean()
    hist_vol = returns.iloc[hist_start:t].std().mean()
    vol_ratio = recent_vol / hist_vol if hist_vol > 0 else 1.0

    # Drawdown from peak over lookback window
    dd_start = max(0, t - lookback)
    window_returns = returns.iloc[dd_start:t].mean(axis=1)  # equal-weight portfolio proxy
    if len(window_returns) > 0:
        cumulative = (1 + window_returns).cumprod()
        peak = cumulative.cummax()
        current_dd = (cumulative.iloc[-1] / peak.iloc[-1]) - 1.0 if peak.iloc[-1] > 0 else 0.0
    else:
        current_dd = 0.0

    # Equity momentum (average daily return over lookback)
    equity_momentum = window_returns.mean() if len(window_returns) > 0 else 0.0

    # Classify regime
    if vol_ratio >= RANKING_VOL_DAMPENER_SEVERE or current_dd <= RANKING_DRAWDOWN_CRISIS_THRESHOLD:
        regime = "crisis"
    elif vol_ratio >= RANKING_VOL_DAMPENER_THRESHOLD or current_dd <= RANKING_DRAWDOWN_STRESS_THRESHOLD:
        regime = "stress"
    else:
        regime = "normal"

    return {
        "regime": regime,
        "vol_ratio": vol_ratio,
        "drawdown": current_dd,
        "equity_momentum": equity_momentum,
    }


def generate_defensive_views(
    regime: dict,
    assets: list[str],
    defensive_assets: list[str] = RANKING_DEFAULT_DEFENSIVE_ASSETS,
    confidence: float = RANKING_DEFENSIVE_CONFIDENCE,
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None, list[str]]:
    """
    Generate defensive views favoring safe-haven assets during market stress.

    Creates views of the form:
        "MBBOND outperforms average stock"

    The view magnitude scales with regime severity:
        - Stress: 5% annual outperformance
        - Crisis: 10% annual outperformance

    Parameters
    ----------
    regime : dict
        Output from detect_market_regime()
    assets : list[str]
        Full asset list (defines P matrix columns)
    defensive_assets : list[str]
        Assets to favor (default: RANKING_DEFAULT_DEFENSIVE_ASSETS)
    confidence : float
        Confidence level for defensive views

    Returns
    -------
    tuple (P, Q, confidence_array, view_names)
        Returns (None, None, None, []) if no defensive assets in the universe
    """

    asset_to_idx = {a: i for i, a in enumerate(assets)}

    # Filter to defensive assets that are actually in the portfolio
    valid_defensive = [a for a in defensive_assets if a in asset_to_idx]
    if not valid_defensive:
        return None, None, None, []

    # Identify stock assets (everything that's not defensive)
    stock_assets = [a for a in assets if a not in defensive_assets]
    if not stock_assets:
        return None, None, None, []

    # View magnitude based on regime severity
    if regime["regime"] == "crisis":
        annual_spread = 0.10  # 10% annual outperformance
        conf_multiplier = 1.0
    else:  # stress
        annual_spread = 0.05  # 5% annual outperformance
        conf_multiplier = 0.85

    daily_spread = annual_spread / TRADING_DAYS_PER_YEAR
    n_assets = len(assets)
    n_stocks = len(stock_assets)

    p_rows = []
    q_vals = []
    conf_vals = []
    view_names = []

    for def_asset in valid_defensive:
        # View: defensive_asset outperforms the equal-weighted stock basket
        row = np.zeros(n_assets, dtype=float)
        row[asset_to_idx[def_asset]] = 1.0

        # Short side: equal-weight across all stocks
        for stock in stock_assets:
            row[asset_to_idx[stock]] = -1.0 / n_stocks

        p_rows.append(row)
        q_vals.append(daily_spread)
        conf_vals.append(confidence * conf_multiplier)
        view_names.append(f"{def_asset}_defensive_{regime['regime']}")

    P = np.array(p_rows, dtype=float)
    Q = np.array(q_vals, dtype=float)
    conf_array = np.array(conf_vals, dtype=float)

    return P, Q, conf_array, view_names
