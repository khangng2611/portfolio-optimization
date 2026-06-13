"""Portfolio performance metrics.

Centralised here so that ``backtest``, ``_compare_backtests``, and
``_compare_ranking`` all share the same implementations.
"""

import numpy as np
import pandas as pd

from config import RISK_FREE_RATE_ANNUAL, TRADING_DAYS_PER_YEAR


def sharpe_ratio(nav_series: pd.Series) -> float:
    """Annualised Sharpe ratio from a NAV series."""
    ret = nav_series.pct_change().dropna()
    if len(ret) == 0 or ret.std() == 0:
        return np.nan
    rf_daily = (1 + RISK_FREE_RATE_ANNUAL) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    excess_ret = ret - rf_daily
    excess_vol = excess_ret.std()
    if excess_vol == 0:
        return np.nan
    return np.sqrt(TRADING_DAYS_PER_YEAR) * excess_ret.mean() / excess_vol


def max_drawdown(nav_series: pd.Series) -> float:
    """Maximum drawdown (negative fraction) from a NAV series."""
    peak = nav_series.cummax()
    drawdown = nav_series / peak - 1
    return drawdown.min()


def annual_return(nav_series: pd.Series) -> float:
    """Annualised return from a NAV series."""
    total_days = len(nav_series) - 1
    if total_days <= 0:
        return np.nan
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    return (1 + total_return) ** (TRADING_DAYS_PER_YEAR / total_days) - 1


def annual_volatility(nav_series: pd.Series) -> float:
    """Annualised volatility from a NAV series."""
    ret = nav_series.pct_change().dropna()
    if len(ret) == 0:
        return np.nan
    return ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR)


def sortino_ratio(nav_series: pd.Series) -> float:
    """Sortino ratio using downside deviation."""
    ret = nav_series.pct_change().dropna()
    if len(ret) == 0:
        return np.nan
    rf_daily = (1 + RISK_FREE_RATE_ANNUAL) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    excess_ret = ret - rf_daily
    downside = excess_ret[excess_ret < 0]
    downside_std = np.sqrt(np.mean(downside ** 2)) if len(downside) > 0 else 0.0
    if downside_std == 0:
        return np.nan
    return np.sqrt(TRADING_DAYS_PER_YEAR) * excess_ret.mean() / downside_std


def calmar_ratio(nav_series: pd.Series) -> float:
    """Calmar ratio = annualised return / max drawdown."""
    total_days = len(nav_series) - 1
    if total_days <= 0:
        return np.nan
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    ann_ret = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / total_days) - 1
    mdd = max_drawdown(nav_series)
    if mdd == 0:
        return np.nan
    return ann_ret / abs(mdd)


def metric_summary(nav_series: pd.Series) -> dict:
    """Comprehensive performance metrics for a NAV series."""
    return {
        "final_nav": float(nav_series.iloc[-1]),
        "ann_return": float(annual_return(nav_series)),
        "ann_volatility": float(annual_volatility(nav_series)),
        "sharpe": float(sharpe_ratio(nav_series)),
        "sortino": float(sortino_ratio(nav_series)),
        "max_drawdown": float(max_drawdown(nav_series)),
        "calmar": float(calmar_ratio(nav_series)),
    }
