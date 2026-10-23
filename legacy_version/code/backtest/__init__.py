"""Backtest package — re-export facade for backward compatibility.

External consumers (``import backtest as bt``) can continue to access
all public symbols exactly as they did when backtest was a single module.
"""

from backtest._metrics import (  # noqa: F401
    annual_return,
    annual_volatility,
    calmar_ratio,
    max_drawdown,
    metric_summary,
    sharpe_ratio,
    sortino_ratio,
)
from backtest._optimizer import (  # noqa: F401
    optimize_weight,
    optimize_weight_ranking,
)
from backtest._black_litterman import black_litterman_posterior_mu  # noqa: F401
from backtest._data_helpers import (  # noqa: F401
    load_market_proxy_prices,
    load_ml_model,
    load_vn30_universe_prices,
)
from backtest._views import generate_dynamic_views  # noqa: F401
from backtest._loop import backtest  # noqa: F401
from backtest._prediction import get_next_period_weights  # noqa: F401
from backtest._cli import parse_args  # noqa: F401
from backtest._main import main  # noqa: F401

from config import BACKTEST_DATA_MODE, WINDOW  # noqa: F401

__all__ = [
    # Core backtest
    "backtest",
    "main",
    "parse_args",
    "get_next_period_weights",
    # Optimisation
    "optimize_weight",
    "optimize_weight_ranking",
    "black_litterman_posterior_mu",
    # Views
    "generate_dynamic_views",
    # Data helpers
    "load_ml_model",
    "load_vn30_universe_prices",
    "load_market_proxy_prices",
    # Metrics
    "sharpe_ratio",
    "max_drawdown",
    "annual_return",
    "annual_volatility",
    "sortino_ratio",
    "calmar_ratio",
    "metric_summary",
    # Config re-exports
    "BACKTEST_DATA_MODE",
    "WINDOW",
]
