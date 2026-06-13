"""Core walk-forward backtest loop.

Orchestrates EW / MVO / BL strategy NAV computation across rebalance
periods.  Ranking-mode logic is delegated to ``_ranking_helpers`` to
keep this module focused on the loop mechanics.
"""

import numpy as np
import pandas as pd

from config import (
    DEFAULT_FEATURE_WINDOW,
    DEFAULT_PREDICTION_HORIZON,
    INITIAL_NAV,
    ML_MIN_RETURN_THRESHOLD,
    RETRAIN_FREQUENCY,
    ML_TRAINING_MODE,
    REBALANCE_FREQ,
    VIEW_MODE,
    WINDOW,
    RANKING_RESELECT_FREQUENCY,
    RANKING_RETRAIN_FREQUENCY,
)
from gen_view.xgboost.config import MIN_TRAIN_SAMPLES
from gen_view.xgboost.xgboost_core import XGBoostEnsembleModel
from gen_view.ranking.ranking_model import XGBoostRankingModel

from backtest._black_litterman import black_litterman_posterior_mu
from backtest._optimizer import optimize_weight
from backtest._views import generate_dynamic_views
from backtest._ranking_helpers import run_ranking_step


def backtest(
    prices,
    window=WINDOW,
    rebalance_freq=REBALANCE_FREQ,
    initial_nav=INITIAL_NAV,
    view_mode=VIEW_MODE,
    ml_model=None,
    ml_min_return_threshold=ML_MIN_RETURN_THRESHOLD,
    ml_training_mode=ML_TRAINING_MODE,
    retrain_frequency=RETRAIN_FREQUENCY,
    ranking_universe_prices=None,
    ranking_market_prices=None,
    warmup_end_index=0,
):
    """Run a walk-forward backtest comparing EW, MVO, and BL strategies.

    Parameters
    ----------
    prices : pd.DataFrame
        Price table (columns = assets, index = business dates).
    window : int
        Lookback window for covariance / mean estimation.
    rebalance_freq : int
        Rebalance every *rebalance_freq* trading days.
    initial_nav : float
        Starting NAV for all strategies.
    view_mode : str
        View generation mode (rule_based, relative, ml, combined, ranking, ranking_absolute).
    ml_model : XGBoostCoreModel, optional
        Pretrained ML model (used for ml / combined modes).
    ml_min_return_threshold : float
        Minimum predicted return to generate an ML view.
    ml_training_mode : str
        ``"pretrained"`` (load cached) or ``"walk_forward"`` (retrain during backtest).
    retrain_frequency : int
        Retrain walk-forward ML model every N trading days.
    ranking_universe_prices : pd.DataFrame, optional
        VN30 universe prices (required for ranking / ranking_absolute modes).
    ranking_market_prices : pd.Series, optional
        E1VFVN30 market proxy prices (required for ranking / ranking_absolute modes).
    warmup_end_index : int
        Index in ``returns`` where the evaluation period starts.  All data
        before this index is used for model warm-up only — NAV series,
        weights history, views history, and rebalance records begin at
        ``warmup_end_index``.  Set to 0 (default) to evaluate the full
        period.

    Returns
    -------
    dict
        Result dict with keys: returns, ew_nav, mvo_nav, bl_nav, weights
        histories, rebalance_dates, assets, views_history,
        rebalance_weights_history, view_mode, ml_model.
    """
    returns = prices.pct_change().dropna()
    assets = list(prices.columns)
    m = len(assets)

    ew_weight = np.full(m, 1.0 / m)
    mvo_weight = np.full(m, 1.0 / m)
    bl_weight = np.full(m, 1.0 / m)

    ew_nav = [initial_nav]
    mvo_nav = [initial_nav]
    bl_nav = [initial_nav]
    ew_weights_hist = []
    mvo_weights_hist = []
    bl_weights_hist = []
    rebalance_dates = []
    views_history = []
    rebalance_weights_history = []

    # --- Walk-forward ML state ---
    if view_mode in ("ml", "combined") and ml_training_mode == "walk_forward" and ml_model is None:
        ml_model = XGBoostEnsembleModel()
        last_retrain_t = -retrain_frequency  # force first train ASAP
    else:
        last_retrain_t = None

    prediction_horizon = (
        getattr(ml_model, "prediction_horizon", DEFAULT_PREDICTION_HORIZON)
        if ml_model else DEFAULT_PREDICTION_HORIZON
    )

    # --- Ranking mode state (shared for ranking / ranking_absolute) ---
    ranking_state = None
    if view_mode == "ranking":
        ranking_state = {
            "ranking_model": XGBoostRankingModel(),
            "ranking_abs_model": None,
            "selected_stocks": None,
            "last_reselect_t": -RANKING_RESELECT_FREQUENCY,
            "last_ranking_retrain_t": -RANKING_RETRAIN_FREQUENCY,
        }
        if ranking_universe_prices is None or ranking_market_prices is None:
            raise ValueError("ranking mode requires ranking_universe_prices and ranking_market_prices")
    elif view_mode == "ranking_absolute":
        ranking_state = {
            "ranking_model": None,
            "ranking_abs_model": XGBoostEnsembleModel(),
            "selected_stocks": None,
            "last_reselect_t": -RANKING_RESELECT_FREQUENCY,
            "last_ranking_retrain_t": -RETRAIN_FREQUENCY,
        }
        if ranking_universe_prices is None or ranking_market_prices is None:
            raise ValueError("ranking_absolute mode requires ranking_universe_prices and ranking_market_prices")

    # -----------------------------------------------------------------------
    # Main walk-forward loop
    # -----------------------------------------------------------------------
    for t in range(window, len(returns)):
        hist = returns.iloc[t - window:t]
        r_t = returns.iloc[t].values

        # EW always updates
        ew_nav.append(ew_nav[-1] * (1 + np.dot(ew_weight, r_t)))
        ew_weights_hist.append(ew_weight.copy())

        if (t - window) % rebalance_freq == 0:
            mu = hist.mean().values
            sigma = hist.cov().values
            mvo_weight = optimize_weight(mu, sigma)
            market_weights = np.full(m, 1.0 / m)

            if view_mode in ("ranking", "ranking_absolute"):
                # --- RANKING MODES (delegated to run_ranking_step) ---
                bl_weight, views_record = run_ranking_step(
                    t, ranking_state, view_mode,
                    mu, sigma, returns, assets,
                    ranking_universe_prices, ranking_market_prices
                )
                views_history.append(views_record)

            else:
                # --- STANDARD MODES (rule_based, relative, ml, combined) ---
                # Walk-forward retrain
                if view_mode in ("ml", "combined") and ml_training_mode == "walk_forward" and last_retrain_t is not None:
                    if t - last_retrain_t >= retrain_frequency:
                        train_end = t - prediction_horizon
                        feature_window = getattr(ml_model, "feature_window", DEFAULT_FEATURE_WINDOW)
                        min_samples = getattr(ml_model, "_min_train_check", MIN_TRAIN_SAMPLES)
                        if train_end >= min_samples + feature_window:
                            train_prices = prices.iloc[:train_end]
                            ml_model.train(train_prices, verbose=False)
                            last_retrain_t = t

                price_window = prices.iloc[max(0, t - window - 30):t]

                effective_ml_model = ml_model
                if view_mode in ("ml", "combined") and ml_training_mode == "walk_forward" and hasattr(ml_model, "is_trained"):
                    if not ml_model.is_trained:
                        effective_ml_model = None

                p_view, q_view, conf_view, view_names = generate_dynamic_views(
                    price_window, assets, view_mode,
                    ml_model=effective_ml_model,
                    ml_min_return_threshold=ml_min_return_threshold,
                )

                # Volatility-based confidence dampener
                if conf_view is not None and view_mode in ("ml", "combined"):
                    recent_vol = returns.iloc[max(0, t - 20):t].std().mean()
                    hist_vol = returns.iloc[max(0, t - 120):t].std().mean()
                    vol_ratio = recent_vol / hist_vol if hist_vol > 0 else 1.0
                    if vol_ratio > 1.3:
                        dampener = 1.3 / vol_ratio
                        conf_view = conf_view * dampener

                views_history.append({
                    "date": returns.index[t],
                    "view_names": view_names if p_view is not None else [],
                    "q_values": q_view.tolist() if q_view is not None else [],
                    "confidences": conf_view.tolist() if conf_view is not None else [],
                })

                if p_view is not None:
                    mu_bl = black_litterman_posterior_mu(sigma, market_weights, p_view, q_view, conf_view)
                else:
                    mu_bl = mu
                bl_weight = optimize_weight(mu_bl, sigma)

            rebalance_dates.append(returns.index[t])
            rebalance_weights_history.append({
                "date": returns.index[t],
                "EW": ew_weight.copy(),
                "MVO": mvo_weight.copy(),
                "BL": bl_weight.copy(),
            })

        # NAV updates for MVO and BL
        mvo_nav.append(mvo_nav[-1] * (1 + np.dot(mvo_weight, r_t)))
        bl_nav.append(bl_nav[-1] * (1 + np.dot(bl_weight, r_t)))
        mvo_weights_hist.append(mvo_weight.copy())
        bl_weights_hist.append(bl_weight.copy())

        # --- Warm-up reset: discard warm-up period records, restart NAV ---
        # All strategies restart from initial_nav for a fair comparison;
        # current weights (shaped during warm-up) are carried forward.
        if warmup_end_index > 0 and t == warmup_end_index:
            ew_nav = [initial_nav]
            mvo_nav = [initial_nav]
            bl_nav = [initial_nav]
            ew_weights_hist = [ew_weight.copy()]
            mvo_weights_hist = [mvo_weight.copy()]
            bl_weights_hist = [bl_weight.copy()]
            rebalance_dates.clear()
            views_history.clear()
            rebalance_weights_history.clear()

    start = max(window - 1, warmup_end_index)
    nav_index = returns.index[start:]
    ew_series = pd.Series(ew_nav, index=nav_index)
    mvo_series = pd.Series(mvo_nav, index=nav_index)
    bl_series = pd.Series(bl_nav, index=nav_index)

    return {
        "returns": returns,
        "ew_nav": ew_series,
        "mvo_nav": mvo_series,
        "bl_nav": bl_series,
        "ew_weights_hist": np.array(ew_weights_hist),
        "mvo_weights_hist": np.array(mvo_weights_hist),
        "bl_weights_hist": np.array(bl_weights_hist),
        "rebalance_dates": rebalance_dates,
        "assets": assets,
        "views_history": views_history,
        "rebalance_weights_history": rebalance_weights_history,
        "view_mode": view_mode,
        "ml_model": ml_model,
    }
