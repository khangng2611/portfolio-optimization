"""
Feature engineering for the ranking-based view generation model.

Computes time-series features per stock and cross-sectional features across
the K selected stocks at each time step. All computations are vectorized over
the full price history and only use information available up to time t (no
look-ahead bias).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gen_view.ranking.config import (
    RANKING_BOLLINGER_PERIOD,
    RANKING_BOLLINGER_STD,
    RANKING_MACD_FAST,
    RANKING_MACD_SIGNAL,
    RANKING_MACD_SLOW,
    RANKING_MOMENTUM_PERIODS,
    RANKING_RSI_PERIOD,
    RANKING_VOLATILITY_WINDOWS,
)
from utils.indicators import (
    bollinger_pctb_series,
    macd_hist_series,
    rsi_series,
)


# ====================== MAIN FEATURE BUILDER ======================


def compute_ranking_features(
    prices: pd.DataFrame,
    market_prices: pd.Series,
    feature_window: int = 60,
) -> pd.DataFrame:
    """
    Compute features for the ranking model.

    Returns a DataFrame with MultiIndex ``(date, stock)`` and one column per
    feature. Each row holds the feature vector for a single stock on a single
    date. Features rely only on prices up to and including the row's date
    (no look-ahead bias).

    Parameters
    ----------
    prices : pd.DataFrame
        Price data for the K selected stocks (columns = tickers).
    market_prices : pd.Series
        Market proxy price data (E1VFVN30) aligned by date.
    feature_window : int
        Minimum lookback window required before features are emitted. Rows
        before this index are dropped to ensure all indicators have enough
        history (typically 60 days).

    Returns
    -------
    pd.DataFrame
        Features with MultiIndex ``(date, stock)``. Columns:
        ``momentum_{p}`` for p in RANKING_MOMENTUM_PERIODS,
        ``volatility_{w}`` for w in RANKING_VOLATILITY_WINDOWS,
        ``rsi_{period}``, ``macd_hist``, ``bollinger_pctb``,
        ``market_ret_{p}`` for p in RANKING_MOMENTUM_PERIODS,
        ``market_vol_{w}`` for w in RANKING_VOLATILITY_WINDOWS (first window),
        ``rank_momentum_{p}``, ``rank_volatility_{w}`` (first window),
        ``rank_overall``.
    """
    if not isinstance(prices, pd.DataFrame) or prices.shape[1] == 0:
        raise ValueError("`prices` must be a non-empty DataFrame with stock columns.")
    if not isinstance(market_prices, pd.Series):
        raise ValueError("`market_prices` must be a pandas Series indexed by date.")

    # Align market series to the price index so all rolling/percent-change
    # operations share the same calendar.
    market_aligned = market_prices.reindex(prices.index)

    # Daily simple returns (used for rolling volatility).
    daily_returns = prices.pct_change()
    market_daily_returns = market_aligned.pct_change()

    # ---------- per-stock time-series features ----------
    feature_frames: dict[str, pd.DataFrame] = {}

    # Momentum: pct change over N days.
    for p in RANKING_MOMENTUM_PERIODS:
        feature_frames[f"momentum_{p}"] = prices.pct_change(periods=p)

    # Volatility: rolling std of daily returns.
    for w in RANKING_VOLATILITY_WINDOWS:
        feature_frames[f"volatility_{w}"] = daily_returns.rolling(
            window=w, min_periods=w
        ).std()

    # RSI / MACD / Bollinger %B computed column-wise (each stock independently).
    rsi_df = prices.apply(lambda s: rsi_series(s, RANKING_RSI_PERIOD))
    macd_df = prices.apply(
        lambda s: macd_hist_series(
            s, RANKING_MACD_FAST, RANKING_MACD_SLOW, RANKING_MACD_SIGNAL
        )
    )
    bbpct_df = prices.apply(
        lambda s: bollinger_pctb_series(
            s, RANKING_BOLLINGER_PERIOD, RANKING_BOLLINGER_STD
        )
    )
    feature_frames[f"rsi_{RANKING_RSI_PERIOD}"] = rsi_df
    feature_frames["macd_hist"] = macd_df
    feature_frames["bollinger_pctb"] = bbpct_df

    # ---------- market features (broadcast across all stocks) ----------
    for p in RANKING_MOMENTUM_PERIODS:
        market_ret = market_aligned.pct_change(periods=p)
        feature_frames[f"market_ret_{p}"] = pd.DataFrame(
            np.tile(market_ret.values[:, None], (1, prices.shape[1])),
            index=prices.index,
            columns=prices.columns,
        )

    market_vol_window = RANKING_VOLATILITY_WINDOWS[0]
    market_vol = market_daily_returns.rolling(
        window=market_vol_window, min_periods=market_vol_window
    ).std()
    feature_frames[f"market_vol_{market_vol_window}"] = pd.DataFrame(
        np.tile(market_vol.values[:, None], (1, prices.shape[1])),
        index=prices.index,
        columns=prices.columns,
    )

    # ---------- cross-sectional rank features ----------
    K = prices.shape[1]

    rank_momentum_frames: list[pd.DataFrame] = []
    for p in RANKING_MOMENTUM_PERIODS:
        mom = feature_frames[f"momentum_{p}"]
        # Rank across stocks (axis=1) per date; divide by K to get percentile.
        rank_p = mom.rank(axis=1, method="average") / K
        feature_frames[f"rank_momentum_{p}"] = rank_p
        rank_momentum_frames.append(rank_p)

    vol_rank_window = RANKING_VOLATILITY_WINDOWS[0]
    vol = feature_frames[f"volatility_{vol_rank_window}"]
    feature_frames[f"rank_volatility_{vol_rank_window}"] = (
        vol.rank(axis=1, method="average") / K
    )

    # Overall rank: average of momentum rank percentiles across periods.
    rank_overall = sum(rank_momentum_frames) / len(rank_momentum_frames)
    feature_frames["rank_overall"] = rank_overall

    # ---------- assemble into long-format MultiIndex DataFrame ----------
    # Each per-feature DataFrame has shape (T, K). Stack to (T*K,) Series with
    # MultiIndex (date, stock) and concat horizontally into final feature matrix.
    # `future_stack=True` matches the new pandas default which preserves NaN
    # rows (so dates with insufficient history still appear in the output).
    long_columns = {
        name: frame.stack(future_stack=True) for name, frame in feature_frames.items()
    }
    features = pd.concat(long_columns, axis=1)
    features.index.set_names(["date", "stock"], inplace=True)

    # Drop rows before `feature_window` to guarantee every indicator has
    # sufficient history. We use positional indexing on the unique date axis.
    if feature_window > 0 and len(prices.index) > feature_window:
        valid_dates = prices.index[feature_window:]
        features = features.loc[features.index.get_level_values("date").isin(valid_dates)]

    return features
