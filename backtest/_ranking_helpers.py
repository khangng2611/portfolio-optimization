"""Shared helpers for ranking and ranking_absolute backtest modes.

Both modes share the same infrastructure:
* Stock re-selection (K-Medoids)
* Active-asset set construction
* Risk management (regime detection, vol dampener, defensive views)
* Constrained BL sub-optimisation + weight mapping

The ONLY difference is view generation, handled by the mode-specific
``_generate_ranking_mode_views`` / ``_generate_ranking_abs_mode_views`` helpers.

The top-level orchestrator ``run_ranking_step`` is called once per
rebalance from the main backtest loop.
"""

import numpy as np

from config import (
    DEFAULT_FEATURE_WINDOW,
    DEFAULT_PREDICTION_HORIZON,
    DEFAULT_DEFENSIVE_ASSETS,
    RANKING_FEATURE_WINDOW,
    RANKING_K,
    MAX_EQUITY_EXPOSURE,
    MIN_DEFENSIVE_WEIGHT,
    RANKING_PREDICTION_HORIZON,
    RANKING_RESELECT_FREQUENCY,
    RANKING_RETRAIN_FREQUENCY,
    RISK_AVERSION_BASE,
    RISK_AVERSION_STRESS,
    RANKING_VIEW_SPREAD,
    VOL_DAMPENER_THRESHOLD,
    ML_MIN_ALLOWED_PREDICTION_RETURN,
    RETRAIN_FREQUENCY
)

from gen_view.ranking.config import RANKING_MIN_TRAIN_SAMPLES
from gen_view.xgboost.config import MIN_TRAIN_SAMPLES
from gen_view.ranking.relative_views import generate_ranking_relative_views
from gen_view.ranking.risk_management import detect_market_regime, generate_defensive_views
from gen_view.ranking.stock_selection import select_representatives
from gen_view.view_generators import build_views_matrix, generate_ml_views

from backtest._black_litterman import black_litterman_posterior_mu
from backtest._optimizer import optimize_weight_ranking


# ---------------------------------------------------------------------------
# Stock selection
# ---------------------------------------------------------------------------

def select_stocks_if_due(t, last_reselect_t, ranking_universe_prices, k=RANKING_K):
    """Re-run K-Medoids stock selection if the reselect interval has elapsed.

    Returns ``(selected_stocks, last_reselect_t)`` — either updated or unchanged.
    """
    if t - last_reselect_t >= RANKING_RESELECT_FREQUENCY:
        # prices.iloc[t] = yesterday; returns is offset by 1 due to dropna()
        universe_up_to_t = ranking_universe_prices.iloc[:t]
        return select_representatives(universe_up_to_t, k=k), t
    return None, last_reselect_t  # caller should keep existing selected_stocks


# ---------------------------------------------------------------------------
# Active-asset set construction
# ---------------------------------------------------------------------------

def build_active_assets(selected_stocks, assets):
    """Build the active-asset set: K selected stocks + GOLD + defensive assets.

    Returns ``(active_indices, active_asset_names)``.
    """
    if selected_stocks is None:
        return list(range(len(assets))), list(assets)

    active_assets_list = list(selected_stocks) + ["GOLD"] + DEFAULT_DEFENSIVE_ASSETS
    active_assets_list = list(dict.fromkeys(active_assets_list))  # deduplicate, keep order
    active_indices = [assets.index(a) for a in active_assets_list if a in assets]
    active_asset_names = [assets[i] for i in active_indices]
    return active_indices, active_asset_names


# ---------------------------------------------------------------------------
# Risk management
# ---------------------------------------------------------------------------

def apply_risk_management(p_view, q_view, conf_view, view_names, returns, t, active_asset_names):
    """Apply regime detection, vol dampener, and defensive-view injection.

    Returns ``(p_view, q_view, conf_view, view_names, regime)``.
    """
    regime = detect_market_regime(returns, t)

    # Volatility dampener
    if conf_view is not None:
        if regime["vol_ratio"] > VOL_DAMPENER_THRESHOLD:
            dampener = VOL_DAMPENER_THRESHOLD / regime["vol_ratio"]
            conf_view = conf_view * dampener

    # Defensive views during stress/crisis
    if regime["regime"] in ("stress", "crisis"):
        def_p, def_q, def_conf, def_names = generate_defensive_views(regime, active_asset_names)
        if def_p is not None:
            if p_view is not None:
                p_view = np.vstack([p_view, def_p])
                q_view = np.concatenate([q_view, def_q])
                conf_view = np.concatenate([conf_view, def_conf])
                view_names = list(view_names) + list(def_names)
            else:
                p_view, q_view, conf_view = def_p, def_q, def_conf
                view_names = list(def_names)

    return p_view, q_view, conf_view, view_names, regime


# ---------------------------------------------------------------------------
# Sub-optimisation (BL + constrained MVO + weight mapping)
# ---------------------------------------------------------------------------

def ranking_sub_optimize(
    mu, sigma, active_indices, active_asset_names,
    p_view, q_view, conf_view, regime, m,
):
    """Run BL posterior + constrained MVO on the active-asset sub-set,
    then map weights back to the full asset vector.

    Returns ``(bl_weight, mvo_weight)`` — both full-size vectors of length
    *m*, with non-zero entries only on the active sub-universe.  The MVO
    leg uses the same constrained optimiser (defensive floor / equity cap)
    but **without** BL views, so it can be blended apples-to-apples with
    the BL leg in the HYBRID strategy.
    """
    sub_mu = mu[active_indices]
    sub_sigma = sigma[np.ix_(active_indices, active_indices)]
    sub_market_weights = np.full(len(active_indices), 1.0 / len(active_indices))

    if p_view is not None:
        mu_bl_sub = black_litterman_posterior_mu(
            sub_sigma, sub_market_weights, p_view, q_view, conf_view
        )
    else:
        mu_bl_sub = sub_mu

    current_risk_aversion = (
        RISK_AVERSION_STRESS
        if regime["regime"] == "crisis"
        else RISK_AVERSION_BASE
    )
    sub_bl_weight = optimize_weight_ranking(
        mu_bl_sub,
        sub_sigma,
        active_asset_names,
        risk_aversion=current_risk_aversion,
        min_defensive_weight=MIN_DEFENSIVE_WEIGHT,
        max_equity_exposure=MAX_EQUITY_EXPOSURE,
        defensive_assets=DEFAULT_DEFENSIVE_ASSETS,
    )

    # Constrained MVO on the same sub-universe (no BL views) for HYBRID.
    sub_mvo_weight = optimize_weight_ranking(
        sub_mu,
        sub_sigma,
        active_asset_names,
        risk_aversion=current_risk_aversion,
        min_defensive_weight=MIN_DEFENSIVE_WEIGHT,
        max_equity_exposure=MAX_EQUITY_EXPOSURE,
        defensive_assets=DEFAULT_DEFENSIVE_ASSETS,
    )

    bl_weight = np.zeros(m)
    mvo_weight = np.zeros(m)
    for i, idx in enumerate(active_indices):
        bl_weight[idx] = sub_bl_weight[i]
        mvo_weight[idx] = sub_mvo_weight[i]
    return bl_weight, mvo_weight


# ---------------------------------------------------------------------------
# Mode-specific view generators
# ---------------------------------------------------------------------------

def generate_ranking_mode_views(
    t, ranking_model, selected_stocks, ranking_universe_prices,
    ranking_market_prices, active_asset_names,
):
    """Generate relative views from XGBoostRankingModel, with momentum cold-start fallback."""
    if ranking_model.is_trained and selected_stocks is not None:
        lookback_start = max(0, t - RANKING_FEATURE_WINDOW)
        stock_prices_recent = ranking_universe_prices[selected_stocks].iloc[
            lookback_start:t
        ]
        market_recent = ranking_market_prices.iloc[lookback_start:t]
        rank_scores, ensemble_std = ranking_model.predict(stock_prices_recent, market_recent)
        return generate_ranking_relative_views(
            rank_scores, ensemble_std, active_asset_names, spread=RANKING_VIEW_SPREAD
        )

    # Cold-start fallback: 20-day momentum
    if selected_stocks is not None and t >= 20:
        momentum_lookback = min(20, t)
        recent_prices = ranking_universe_prices[selected_stocks].iloc[
            t - momentum_lookback:t
        ]
        if len(recent_prices) >= 20:
            mom_scores = {}
            for stock in selected_stocks:
                if stock in recent_prices.columns:
                    p_start = recent_prices[stock].iloc[0]
                    p_end = recent_prices[stock].iloc[-1]
                    if p_start > 0:
                        mom_scores[stock] = (p_end / p_start) - 1.0
            mom_std = {s: 0.1 for s in mom_scores}
            if len(mom_scores) >= 2:
                p_view, q_view, conf_view, view_names = generate_ranking_relative_views(
                    mom_scores, mom_std, active_asset_names, spread=RANKING_VIEW_SPREAD
                )
                if conf_view is not None:
                    conf_view = np.clip(conf_view, 0.0, 0.45)
                return p_view, q_view, conf_view, view_names

    return None, None, None, []


def generate_ranking_abs_mode_views(
    t, ranking_abs_model, selected_stocks, ranking_universe_prices,
    active_asset_names, returns,
):
    """Generate absolute ML views from XGBoostEnsembleModel."""
    if ranking_abs_model.is_trained and selected_stocks is not None:
        lookback_start = max(0, t - DEFAULT_FEATURE_WINDOW)
        stock_prices_recent = ranking_universe_prices[selected_stocks].iloc[
            lookback_start:t
        ]
        predictions = ranking_abs_model.predict(stock_prices_recent)
        # Recent returns slice for volatility-adjusted view scaling (Option B)
        vol_start = max(0, t - 20)
        recent_returns = returns.iloc[vol_start:t]
        ml_views = generate_ml_views(
            predictions,
            prediction_horizon=ranking_abs_model.prediction_horizon,
            min_return_threshold=ML_MIN_ALLOWED_PREDICTION_RETURN,
            returns=recent_returns,
        )
        return build_views_matrix(ml_views, active_asset_names)

    return None, None, None, []


# ---------------------------------------------------------------------------
# Model retraining
# ---------------------------------------------------------------------------

def retrain_ranking_model_if_due(
    t, last_retrain_t, ranking_model, selected_stocks,
    ranking_universe_prices, ranking_market_prices,
):
    """Retrain the XGBoostRankingModel if the retrain interval has elapsed."""
    if t - last_retrain_t >= RANKING_RETRAIN_FREQUENCY or not ranking_model.is_trained:
        train_end = t - RANKING_PREDICTION_HORIZON
        if train_end > (RANKING_FEATURE_WINDOW + RANKING_PREDICTION_HORIZON + RANKING_MIN_TRAIN_SAMPLES):
            stock_prices_train = ranking_universe_prices[selected_stocks].iloc[:train_end]
            market_train = ranking_market_prices.iloc[:train_end]
            ranking_model.train(stock_prices_train, market_train, verbose=False)
            return t
    return last_retrain_t


def retrain_ranking_abs_model_if_due(
    t, last_retrain_t, ranking_abs_model, selected_stocks,
    ranking_universe_prices,
):
    """Retrain the XGBoostEnsembleModel if the retrain interval has elapsed."""
    if t - last_retrain_t >= RETRAIN_FREQUENCY or not ranking_abs_model.is_trained:
        train_end = t - DEFAULT_PREDICTION_HORIZON
        threshold = DEFAULT_FEATURE_WINDOW + DEFAULT_PREDICTION_HORIZON + MIN_TRAIN_SAMPLES
        if train_end > threshold:
            stock_prices_train = ranking_universe_prices[selected_stocks].iloc[:train_end]
            ranking_abs_model.train(stock_prices_train, verbose=False)
            return t
    return last_retrain_t


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def run_ranking_step(
    t,
    state,
    view_mode,
    mu,
    sigma,
    returns,
    assets,
    ranking_universe_prices,
    ranking_market_prices,
):
    """Orchestrate one ranking-mode rebalance step.

    Parameters
    ----------
    t : int
        Current time index in the returns series.
    state : dict
        Mutable state dict with keys: ``selected_stocks``, ``last_reselect_t``,
        ``last_ranking_retrain_t``, ``ranking_model``, ``ranking_abs_model``.
    view_mode : str
        ``"ranking"`` or ``"ranking_absolute"``.
    mu, sigma : ndarray
        Historical mean returns and covariance for the full asset set.
    returns : pd.DataFrame
        Full returns series (used for regime detection).
    assets : list[str]
        Full asset name list.
    ranking_universe_prices : pd.DataFrame
        VN30 universe price table.
    ranking_market_prices : pd.Series
        E1VFVN30 market proxy prices.
    window : int
        Lookback window size.

    Returns
    -------
    tuple
        ``(bl_weight, mvo_weight, regime, views_record)`` where:
        * ``bl_weight`` and ``mvo_weight`` are full-size weight vectors
          (non-zero only on the active sub-universe). ``mvo_weight`` is the
          constrained MVO leg used by the HYBRID strategy.
        * ``regime`` is the dict returned by ``detect_market_regime``.
        * ``views_record`` is the dict to append to ``views_history``.
    """
    m = len(assets)

    # --- Stock selection ---
    new_stocks, new_reselect_t = select_stocks_if_due(
        t, state["last_reselect_t"], ranking_universe_prices
    )
    if new_stocks is not None:
        state["selected_stocks"] = new_stocks
        state["last_reselect_t"] = new_reselect_t

    selected_stocks = state["selected_stocks"]

    # --- Model retraining ---
    if view_mode == "ranking":
        state["last_ranking_retrain_t"] = retrain_ranking_model_if_due(
            t, state["last_ranking_retrain_t"],
            state["ranking_model"], selected_stocks,
            ranking_universe_prices, ranking_market_prices,
        )
    else:  # ranking_absolute
        state["last_ranking_retrain_t"] = retrain_ranking_abs_model_if_due(
            t, state["last_ranking_retrain_t"],
            state["ranking_abs_model"], selected_stocks,
            ranking_universe_prices,
        )

    # --- Active-asset set ---
    active_indices, active_asset_names = build_active_assets(selected_stocks, assets)

    # --- View generation (mode-specific) ---
    if view_mode == "ranking":
        p_view, q_view, conf_view, view_names = generate_ranking_mode_views(
            t, state["ranking_model"], selected_stocks,
            ranking_universe_prices, ranking_market_prices,
            active_asset_names,
        )
    else:
        p_view, q_view, conf_view, view_names = generate_ranking_abs_mode_views(
            t, state["ranking_abs_model"], selected_stocks,
            ranking_universe_prices, active_asset_names, returns,
        )

    # --- Risk management ---
    p_view, q_view, conf_view, view_names, regime = apply_risk_management(
        p_view, q_view, conf_view, view_names, returns, t, active_asset_names
    )

    # --- Views history record ---
    views_record = {
        "date": returns.index[t],
        "view_names": view_names if p_view is not None else [],
        "q_values": q_view.tolist() if q_view is not None else [],
        "confidences": conf_view.tolist() if conf_view is not None else [],
    }

    # --- Sub-optimisation ---
    bl_weight, mvo_weight = ranking_sub_optimize(
        mu, sigma, active_indices, active_asset_names,
        p_view, q_view, conf_view, regime, m,
    )

    return bl_weight, mvo_weight, regime, views_record
