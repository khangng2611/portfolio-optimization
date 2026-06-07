"""
View Generators for Black-Litterman Model
==========================================

This module provides all approaches to generate views for Black-Litterman:
1. Static View Generator (predefined views from config)
2. Rule-based View Generator (using MA, RSI, Momentum)
3. Relative View Generator (comparing pairs of assets)
4. ML-based View Generator (XGBoost supervised learning)

Each generator returns a list of view dicts compatible with Black-Litterman.
"""

import warnings
from typing import Optional

import numpy as np
import pandas as pd

from config import DEFAULT_PREDICTION_HORIZON, STATIC_VIEWS, TRADING_DAYS_PER_YEAR

warnings.filterwarnings("ignore")

# ====================== CONSTANTS ======================
# Rule-based defaults
DEFAULT_MA_SHORT = 10
DEFAULT_MA_LONG = 30
DEFAULT_RSI_PERIOD = 14
DEFAULT_MOMENTUM_PERIOD = 20
DEFAULT_ATR_PERIOD = 14

# Thresholds
MA_CROSSOVER_THRESHOLD = 0.02  # 2% difference for MA crossover signal
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MOMENTUM_THRESHOLD = 0.01  # 1% monthly momentum for signal


# ====================== TECHNICAL INDICATORS ======================
def compute_sma(prices: pd.Series, period: int) -> pd.Series:
    """
    Simple Moving Average (SMA)
    
    SMA = (P1 + P2 + ... + Pn) / n
    
    - Smooths price data by averaging over `period` days
    - Lagging indicator: reacts slowly to price changes
    """
    return prices.rolling(window=period, min_periods=1).mean()


def compute_ema(prices: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average (EMA)
    
    EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1}
    where alpha = 2 / (period + 1)
    
    - Gives more weight to recent prices
    - Reacts faster than SMA to price changes
    """
    return prices.ewm(span=period, adjust=False, min_periods=1).mean()


def compute_rsi(prices: pd.Series, period: int = DEFAULT_RSI_PERIOD) -> float:
    """
    Relative Strength Index (RSI)
    
    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss over `period` days
    
    - Momentum oscillator measuring speed/change of price movements
    - Range: 0-100
    - RSI > 70: Overbought (potential reversal down)
    - RSI < 30: Oversold (potential reversal up)
    """
    if len(prices) < period + 1:
        return 50.0  # Neutral if not enough data
    
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50.0


def compute_macd(
    prices: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[float, float, float]:
    """
    Moving Average Convergence Divergence (MACD)
    
    MACD Line = EMA(fast) - EMA(slow)
    Signal Line = EMA(MACD Line, signal_period)
    Histogram = MACD Line - Signal Line
    
    - Trend-following momentum indicator
    - MACD > Signal: Bullish
    - MACD < Signal: Bearish
    - Histogram shows strength of trend
    """
    ema_fast = compute_ema(prices, fast_period)
    ema_slow = compute_ema(prices, slow_period)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal_period)
    histogram = macd_line - signal_line
    
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]


def compute_momentum(prices: pd.Series, period: int = DEFAULT_MOMENTUM_PERIOD) -> float:
    """
    Rate of Change (ROC) / Momentum
    
    ROC = (P_t - P_{t-n}) / P_{t-n}
    
    - Measures percentage change over `period` days
    - ROC > 0: Upward momentum
    - ROC < 0: Downward momentum
    """
    if len(prices) <= period:
        return 0.0
    return (prices.iloc[-1] / prices.iloc[-period - 1]) - 1


def compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = DEFAULT_ATR_PERIOD
) -> float:
    """
    Average True Range (ATR)
    
    True Range = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
    ATR = SMA(True Range, period)
    
    - Measures volatility (not direction)
    - Higher ATR = higher volatility
    - Used to scale confidence in views
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=1).mean()
    return atr.iloc[-1] if not np.isnan(atr.iloc[-1]) else 0.0


def compute_bollinger_bands(
    prices: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[float, float, float]:
    """
    Bollinger Bands
    
    Middle Band = SMA(period)
    Upper Band = Middle + num_std * STD(period)
    Lower Band = Middle - num_std * STD(period)
    
    - Measures volatility and potential overbought/oversold conditions
    - Price near upper band: potentially overbought
    - Price near lower band: potentially oversold
    """
    sma = compute_sma(prices, period)
    std = prices.rolling(window=period, min_periods=1).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return lower.iloc[-1], sma.iloc[-1], upper.iloc[-1]


# ====================== VIEW GENERATORS ======================


def generate_static_views() -> list[dict]:
    """
    Static View Generator

    Returns the predefined static views from config (STATIC_VIEWS).
    These views are fixed and do not change with market conditions.

    Returns
    -------
    list[dict]
        List of static view dictionaries for Black-Litterman.
        Compatible with :func:`build_views_matrix`.
    """
    return list(STATIC_VIEWS)


def generate_rule_based_views(
    prices: pd.DataFrame,
    ma_short: int = DEFAULT_MA_SHORT,
    ma_long: int = DEFAULT_MA_LONG,
    rsi_period: int = DEFAULT_RSI_PERIOD,
    momentum_period: int = DEFAULT_MOMENTUM_PERIOD,
) -> list[dict]:
    """
    Rule-based View Generator
    
    Generates views based on technical indicators:
    1. MA Crossover: EMA short vs EMA long
    2. RSI: Adjusts confidence based on overbought/oversold
    3. Momentum: Determines view magnitude
    
    Parameters
    ----------
    prices : pd.DataFrame
        Price data with assets as columns
    ma_short : int
        Short-term MA period (default 10)
    ma_long : int
        Long-term MA period (default 30)
    rsi_period : int
        RSI calculation period (default 14)
    momentum_period : int
        Momentum calculation period (default 20)
    
    Returns
    -------
    list[dict]
        List of view dictionaries for Black-Litterman
    """
    views = []
    
    for asset in prices.columns:
        price_series = prices[asset].dropna()
        if len(price_series) < ma_long + 1:
            continue
        
        # Calculate indicators
        ema_short = compute_ema(price_series, ma_short).iloc[-1]
        ema_long = compute_ema(price_series, ma_long).iloc[-1]
        rsi = compute_rsi(price_series, rsi_period)
        momentum = compute_momentum(price_series, momentum_period)
        
        # MA Crossover signal
        ma_ratio = (ema_short / ema_long) - 1
        
        # Determine view direction and magnitude
        if ma_ratio > MA_CROSSOVER_THRESHOLD:
            # Bullish: short MA above long MA
            base_return = 0.05 + abs(momentum) * 0.5  # 5% base + momentum bonus
            base_confidence = 0.6
            signal_type = "bullish"
        elif ma_ratio < -MA_CROSSOVER_THRESHOLD:
            # Bearish: short MA below long MA
            base_return = -0.03 - abs(momentum) * 0.3
            base_confidence = 0.5
            signal_type = "bearish"
        else:
            # No clear signal
            continue
        
        # Adjust confidence based on RSI
        if rsi > RSI_OVERBOUGHT:
            # Overbought: reduce confidence in bullish views
            if signal_type == "bullish":
                base_confidence *= 0.7
            else:
                base_confidence *= 1.2  # Increase confidence in bearish
        elif rsi < RSI_OVERSOLD:
            # Oversold: reduce confidence in bearish views
            if signal_type == "bearish":
                base_confidence *= 0.7
            else:
                base_confidence *= 1.2  # Increase confidence in bullish
        
        # Cap confidence
        base_confidence = min(0.9, max(0.3, base_confidence))
        
        views.append({
            "name": f"{asset}_rule_based",
            "legs": {asset: 1.0},
            "view_return_annual": base_return,
            "confidence": base_confidence,
            "signal_type": signal_type,
            "indicators": {
                "ma_ratio": ma_ratio,
                "rsi": rsi,
                "momentum": momentum,
            },
        })
    
    return views


def generate_relative_views(
    prices: pd.DataFrame,
    asset_pairs: Optional[list[tuple[str, str]]] = None,
    momentum_period: int = DEFAULT_MOMENTUM_PERIOD,
    min_momentum_diff: float = MOMENTUM_THRESHOLD,
) -> list[dict]:
    """
    Relative View Generator
    
    Compares momentum between pairs of assets to generate relative views.
    
    Parameters
    ----------
    prices : pd.DataFrame
        Price data with assets as columns
    asset_pairs : list[tuple[str, str]], optional
        List of asset pairs to compare. If None, generates all pairs.
    momentum_period : int
        Period for momentum calculation
    min_momentum_diff : float
        Minimum momentum difference to generate a view
    
    Returns
    -------
    list[dict]
        List of relative view dictionaries
    """
    views = []
    assets = list(prices.columns)
    
    # Generate all pairs if not specified
    if asset_pairs is None:
        asset_pairs = []
        for i, a in enumerate(assets):
            for b in assets[i + 1:]:
                asset_pairs.append((a, b))
    
    for asset_a, asset_b in asset_pairs:
        if asset_a not in prices.columns or asset_b not in prices.columns:
            continue
        
        price_a = prices[asset_a].dropna()
        price_b = prices[asset_b].dropna()
        
        if len(price_a) <= momentum_period or len(price_b) <= momentum_period:
            continue
        
        # Calculate momentum for each asset
        momentum_a = compute_momentum(price_a, momentum_period)
        momentum_b = compute_momentum(price_b, momentum_period)
        
        # Momentum difference
        diff = momentum_a - momentum_b
        
        if abs(diff) < min_momentum_diff:
            continue
        
        # Determine which asset outperforms
        if diff > 0:
            long_asset, short_asset = asset_a, asset_b
        else:
            long_asset, short_asset = asset_b, asset_a
            diff = -diff
        
        # Annualized expected outperformance
        view_return_annual = diff * TRADING_DAYS_PER_YEAR / momentum_period
        view_return_annual = max(-0.30, min(0.30, view_return_annual))  # Cap at 30%
        
        # Confidence based on momentum strength
        confidence = min(0.8, 0.4 + abs(diff) * 10)
        
        views.append({
            "name": f"{long_asset}_over_{short_asset}",
            "legs": {long_asset: 1.0, short_asset: -1.0},
            "view_return_annual": view_return_annual,
            "confidence": confidence,
            "indicators": {
                "momentum_long": momentum_a if diff > 0 else momentum_b,
                "momentum_short": momentum_b if diff > 0 else momentum_a,
                "momentum_diff": abs(diff),
            },
        })
    
    return views


# ====================== ML VIEW GENERATION (prediction -> BL views) =========


def generate_ml_views(
    predictions: dict[str, tuple[float, float]],
    prediction_horizon: int = DEFAULT_PREDICTION_HORIZON,
    min_return_threshold: float = 0.005,
    model_type: str = "xgboost",
) -> list[dict]:
    """
    Convert ML predictions into Black-Litterman view dicts.

    This function is the bridge between the ML layer (predictions) and the
    portfolio layer (BL views).  It knows the view-dict schema but nothing
    about how the predictions were produced.

    Parameters
    ----------
    predictions : dict
        {asset_name: (predicted_return, confidence)}  as returned by
        ``XGBoostCoreModel.predict()``
    prediction_horizon : int
        Days ahead the prediction covers (used for annualization)
    min_return_threshold : float
        Minimum absolute predicted return to emit a view
    model_type : str
        Label stored in the view dict for provenance

    Returns
    -------
    list[dict]
        List of view dictionaries compatible with Black-Litterman
    """
    views = []

    # Scaling parameters
    MAX_ANNUAL_VIEW = 0.30    # max annual view magnitude (hard cap)

    for asset, (pred_return, confidence) in predictions.items():
        if abs(pred_return) < min_return_threshold:
            continue

        # Annualize and clip
        view_return_annual = pred_return * (TRADING_DAYS_PER_YEAR / prediction_horizon)
        view_return_annual = max(-MAX_ANNUAL_VIEW, min(MAX_ANNUAL_VIEW, view_return_annual))

        views.append({
            "name": f"{asset}_ml_{model_type}",
            "legs": {asset: 1.0},
            "view_return_annual": view_return_annual,
            "confidence": confidence,
            "source": "traditional_ml",
            "model_type": model_type,
            "predicted_return_horizon": pred_return,
        })

    return views


# ====================== UTILITY FUNCTIONS ======================


def build_views_matrix(
    views: list[dict],
    assets: list[str],
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray], list[str]]:
    """
    Convert list of view dicts to P, Q, confidence matrices for Black-Litterman.
    
    Parameters
    ----------
    views : list[dict]
        List of view dictionaries
    assets : list[str]
        List of asset names (defines column order)
    trading_days_per_year : int
        Number of trading days per year
    
    Returns
    -------
    tuple
        (P matrix, Q vector, confidence vector, active view names)
    """
    if not views:
        return None, None, None, []
    
    asset_to_idx = {asset: i for i, asset in enumerate(assets)}
    p_rows = []
    q_vals = []
    conf_vals = []
    active_names = []
    
    for view in views:
        row = np.zeros(len(assets), dtype=float)
        is_valid = True
        
        for asset, coeff in view["legs"].items():
            if asset not in asset_to_idx:
                is_valid = False
                break
            row[asset_to_idx[asset]] = coeff
        
        if not is_valid:
            continue
        
        p_rows.append(row)
        q_vals.append(view["view_return_annual"] / trading_days_per_year)
        conf_vals.append(view.get("confidence", 0.5))
        active_names.append(view["name"])
    
    if len(p_rows) == 0:
        return None, None, None, []
    
    return (
        np.array(p_rows, dtype=float),
        np.array(q_vals, dtype=float),
        np.array(conf_vals, dtype=float),
        active_names,
    )


def combine_views(
    rule_views: list[dict],
    relative_views: list[dict],
    ml_views: list[dict],
    static_views: list[dict],
    weights: tuple[float, float, float, float] = (0.4, 0.3, 0.3, 0.0),
) -> list[dict]:
    """
    Combine views from multiple generators with confidence weighting.
    
    Parameters
    ----------
    rule_views : list[dict]
        Views from rule-based generator
    relative_views : list[dict]
        Views from relative generator
    ml_views : list[dict]
        Views from ML generator
    static_views : list[dict]
        Views from static (predefined) generator
    weights : tuple[float, float, float, float]
        Weights for (rule, relative, ml, static) generators
    
    Returns
    -------
    list[dict]
        Combined list of views with adjusted confidence
    """
    combined = []
    
    w_rule, w_rel, w_ml, w_static = weights
    
    for view in rule_views:
        view = view.copy()
        view["confidence"] *= w_rule
        view["source"] = "rule_based"
        combined.append(view)
    
    for view in relative_views:
        view = view.copy()
        view["confidence"] *= w_rel
        view["source"] = "relative"
        combined.append(view)
    
    for view in ml_views:
        view = view.copy()
        view["confidence"] *= w_ml
        view["source"] = "ml"
        combined.append(view)
    
    for view in static_views:
        view = view.copy()
        view["confidence"] *= w_static
        view["source"] = "static"
        combined.append(view)
    
    return combined


def generate_ranking_views_bridge(
    rank_scores: dict,
    ensemble_std: dict,
    assets: list,
    spread: float = 0.03,
):
    """
    Bridge function to ranking relative view generation.

    Delegates to gen_view.ranking.relative_views.generate_ranking_relative_views().
    """
    from gen_view.ranking.relative_views import generate_ranking_relative_views
    return generate_ranking_relative_views(rank_scores, ensemble_std, assets, spread)

