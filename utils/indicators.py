"""
Technical Indicators Library
============================

Centralized implementations of technical indicators used across the codebase
(rule-based view generation, ML feature engineering, ranking model features).

Two flavors are exposed for each indicator:

* ``compute_*`` functions return either a scalar (latest value) or a full
  ``pd.Series`` aligned to the input index, matching the legacy semantics used
  by ``gen_view/view_generators.py`` (lenient ``min_periods=1`` for rolling
  windows so the latest value is always defined).
* ``*_series`` helpers return the full vectorized series with strict
  ``min_periods=period`` so leading values are ``NaN`` until enough history is
  available. These are the building blocks for batch feature engineering
  (``gen_view/ranking/feature_engineering.py``).

All functions are pure (no side effects) and operate only on data passed in.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ====================== DEFAULT PERIODS ======================
DEFAULT_MA_SHORT = 10
DEFAULT_MA_LONG = 30
DEFAULT_RSI_PERIOD = 14
DEFAULT_MOMENTUM_PERIOD = 20
DEFAULT_ATR_PERIOD = 14
DEFAULT_MACD_FAST = 12
DEFAULT_MACD_SLOW = 26
DEFAULT_MACD_SIGNAL = 9
DEFAULT_BOLLINGER_PERIOD = 20
DEFAULT_BOLLINGER_STD = 2.0


# ====================== MOVING AVERAGES ======================
def compute_sma(prices: pd.Series, period: int) -> pd.Series:
    """
    Simple Moving Average (SMA).

    SMA = (P1 + P2 + ... + Pn) / n

    Uses ``min_periods=1`` so the result is always defined from the first row.
    """
    return prices.rolling(window=period, min_periods=1).mean()


def compute_ema(prices: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average (EMA).

    EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1},  alpha = 2 / (period + 1)
    """
    return prices.ewm(span=period, adjust=False, min_periods=1).mean()


# ====================== RSI ======================
def rsi_series(prices: pd.Series, period: int = DEFAULT_RSI_PERIOD) -> pd.Series:
    """
    Vectorized RSI as a full series.

    RSI = 100 - 100 / (1 + RS), where RS = avg_gain / avg_loss over `period`.
    Uses simple rolling means with strict ``min_periods=period`` so the leading
    rows are ``NaN`` until enough history is accumulated.
    """
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def compute_rsi(prices: pd.Series, period: int = DEFAULT_RSI_PERIOD) -> float:
    """
    Scalar RSI of the most recent observation.

    Uses ``min_periods=1`` (lenient) for backward compatibility with
    ``gen_view/view_generators.py``: returns ``50.0`` when not enough history.
    """
    if len(prices) < period + 1:
        return 50.0  # neutral

    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    return rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50.0


# ====================== MACD ======================
def macd_series(
    prices: pd.Series,
    fast_period: int = DEFAULT_MACD_FAST,
    slow_period: int = DEFAULT_MACD_SLOW,
    signal_period: int = DEFAULT_MACD_SIGNAL,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Vectorized MACD components as full series.

    Returns ``(macd_line, signal_line, histogram)`` where::

        macd_line = EMA(fast) - EMA(slow)
        signal_line = EMA(macd_line, signal_period)
        histogram = macd_line - signal_line
    """
    ema_fast = compute_ema(prices, fast_period)
    ema_slow = compute_ema(prices, slow_period)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal_period)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def macd_hist_series(
    prices: pd.Series,
    fast_period: int = DEFAULT_MACD_FAST,
    slow_period: int = DEFAULT_MACD_SLOW,
    signal_period: int = DEFAULT_MACD_SIGNAL,
) -> pd.Series:
    """Vectorized MACD histogram only (used by feature engineering)."""
    _, _, histogram = macd_series(prices, fast_period, slow_period, signal_period)
    return histogram


def compute_macd(
    prices: pd.Series,
    fast_period: int = DEFAULT_MACD_FAST,
    slow_period: int = DEFAULT_MACD_SLOW,
    signal_period: int = DEFAULT_MACD_SIGNAL,
) -> tuple[float, float, float]:
    """
    Scalar MACD values for the most recent observation.

    Returns ``(macd_line[-1], signal_line[-1], histogram[-1])``.
    """
    macd_line, signal_line, histogram = macd_series(
        prices, fast_period, slow_period, signal_period
    )
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]


# ====================== MOMENTUM / ROC ======================
def compute_momentum(
    prices: pd.Series, period: int = DEFAULT_MOMENTUM_PERIOD
) -> float:
    """
    Rate-of-Change momentum: (P_t - P_{t-period}) / P_{t-period}.

    Returns ``0.0`` if there isn't enough history.
    """
    if len(prices) <= period:
        return 0.0
    return (prices.iloc[-1] / prices.iloc[-period - 1]) - 1


# ====================== ATR ======================
def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = DEFAULT_ATR_PERIOD,
) -> float:
    """
    Average True Range (ATR), scalar latest value.

    True Range = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
    ATR = SMA(True Range, period)
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=1).mean()
    return atr.iloc[-1] if not np.isnan(atr.iloc[-1]) else 0.0


# ====================== BOLLINGER BANDS ======================
def compute_bollinger_bands(
    prices: pd.Series,
    period: int = DEFAULT_BOLLINGER_PERIOD,
    num_std: float = DEFAULT_BOLLINGER_STD,
) -> tuple[float, float, float]:
    """
    Bollinger Bands, scalar latest values: ``(lower, middle, upper)``.

    Uses ``min_periods=1`` (lenient) for compatibility with the legacy
    rule-based view generator.
    """
    sma = compute_sma(prices, period)
    std = prices.rolling(window=period, min_periods=1).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return lower.iloc[-1], sma.iloc[-1], upper.iloc[-1]


def bollinger_pctb_series(
    prices: pd.Series,
    period: int = DEFAULT_BOLLINGER_PERIOD,
    num_std: float = DEFAULT_BOLLINGER_STD,
) -> pd.Series:
    """
    Vectorized Bollinger %B series.

    %B = (price - lower) / (upper - lower); ``0.5`` on the SMA, ``> 1`` above
    the upper band, ``< 0`` below the lower band. ``NaN`` where band width is
    zero. Uses strict ``min_periods=period`` for batch feature engineering.
    """
    sma = prices.rolling(window=period, min_periods=period).mean()
    std = prices.rolling(window=period, min_periods=period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    width = (upper - lower).replace(0, np.nan)
    return (prices - lower) / width


__all__ = [
    "DEFAULT_MA_SHORT",
    "DEFAULT_MA_LONG",
    "DEFAULT_RSI_PERIOD",
    "DEFAULT_MOMENTUM_PERIOD",
    "DEFAULT_ATR_PERIOD",
    "DEFAULT_MACD_FAST",
    "DEFAULT_MACD_SLOW",
    "DEFAULT_MACD_SIGNAL",
    "DEFAULT_BOLLINGER_PERIOD",
    "DEFAULT_BOLLINGER_STD",
    "compute_sma",
    "compute_ema",
    "compute_rsi",
    "rsi_series",
    "compute_macd",
    "macd_series",
    "macd_hist_series",
    "compute_momentum",
    "compute_atr",
    "compute_bollinger_bands",
    "bollinger_pctb_series",
]
