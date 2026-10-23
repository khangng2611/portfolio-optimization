"""Predict next-period portfolio weights given current market data."""

import numpy as np

from config import ML_MIN_ALLOWED_PREDICTION_RETURN, VIEW_MODE, WINDOW
from backtest._black_litterman import black_litterman_posterior_mu
from backtest._optimizer import optimize_weight
from backtest._views import generate_dynamic_views


def get_next_period_weights(
    returns,
    prices,
    as_of_date,
    window=WINDOW,
    view_mode=VIEW_MODE,
    ml_model=None,
    ml_min_return_threshold=ML_MIN_ALLOWED_PREDICTION_RETURN,
):
    """Estimate MVO and BL weights for the period after *as_of_date*.

    Parameters
    ----------
    returns : pd.DataFrame
        Return series (columns = assets).
    prices : pd.DataFrame
        Price series (columns = assets).
    as_of_date : pd.Timestamp
        Date up to which data is available.
    window : int
        Lookback window for mean / covariance estimation.
    view_mode : str
        View generation mode.
    ml_model : XGBoostCoreModel, optional
        Trained ML model.
    ml_min_return_threshold : float
        Minimum predicted return to generate a view.

    Returns
    -------
    tuple
        ``(w_mvo, w_bl, last_hist_date, view_names)``
    """
    eligible = returns.loc[returns.index <= as_of_date]
    if len(eligible) < window:
        raise ValueError(
            f"Khong du du lieu de tinh weight sau {as_of_date.date()}: co {len(eligible)} dong"
        )

    hist = eligible.iloc[-window:]
    mu = hist.mean().values
    sigma = hist.cov().values
    market_weights = np.full(len(mu), 1.0 / len(mu))
    assets = list(returns.columns)

    price_eligible = prices.loc[prices.index <= as_of_date]
    price_window = price_eligible.iloc[-window - 30:] if len(price_eligible) > window + 30 else price_eligible
    p_view, q_view, conf_view, view_names = generate_dynamic_views(
        price_window, assets, view_mode,
        ml_model=ml_model,
        ml_min_return_threshold=ml_min_return_threshold,
    )

    if p_view is not None:
        mu_bl = black_litterman_posterior_mu(sigma, market_weights, p_view, q_view, conf_view)
    else:
        mu_bl = mu

    w_mvo = optimize_weight(mu, sigma)
    w_bl = optimize_weight(mu_bl, sigma)
    return w_mvo, w_bl, hist.index[-1], view_names
