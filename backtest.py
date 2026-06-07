import argparse
from pathlib import Path

import cvxpy as cp
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from utils.data_loader import (
    build_price_table,
    load_assets_config,
    resolve_period,
    summarize_asset_returns,
)
from utils.view_logger import log_view_history

from config import (
    BACKTEST_DATA_MODE,
    BACKTEST_PHASE,
    BL_DELTA,
    BL_TAU,
    COMBINED_VIEW_WEIGHTS,
    INITIAL_NAV,
    MAX_POSITION_SIZE,
    DEFAULT_FEATURE_WINDOW,
    DEFAULT_PREDICTION_HORIZON,
    ML_MIN_RETURN_THRESHOLD,
    ML_MODEL_TYPE,
    ML_RETRAIN_FREQUENCY,
    ML_TRAINING_MODE,
    PHASE_PERIODS,
    RISK_FREE_RATE_ANNUAL,
    REBALANCE_FREQ,
    TRADING_DAYS_PER_YEAR,
    VIEW_MODE,
    WINDOW,
    RANKING_K,
    RANKING_FEATURE_WINDOW,
    RANKING_PREDICTION_HORIZON,
    RANKING_RETRAIN_FREQUENCY,
    RANKING_RESELECT_FREQUENCY,
    RANKING_VIEW_SPREAD,
    VN30_LIST_PATH,
    RANKING_MIN_DEFENSIVE_WEIGHT,
    RANKING_MAX_EQUITY_EXPOSURE,
    RANKING_VOL_DAMPENER_THRESHOLD,
    RANKING_VOL_DAMPENER_SEVERE,
    RANKING_RISK_AVERSION_BASE,
    RANKING_RISK_AVERSION_STRESS,
)
from gen_view.xgboost.config import MIN_TRAIN_SAMPLES
from gen_view.view_generators import (
    generate_ml_views,
    generate_rule_based_views,
    generate_relative_views,
    generate_static_views,
    build_views_matrix,
    combine_views,
)
from gen_view.xgboost.xgboost_core import XGBoostCoreModel, XGBoostEnsembleModel
from gen_view.ranking.stock_selection import select_representatives
from gen_view.ranking.ranking_model import XGBoostRankingModel
from gen_view.ranking.relative_views import generate_ranking_relative_views
from gen_view.ranking.risk_management import detect_market_regime, generate_defensive_views

ROOT_DIR = Path(__file__).resolve().parent
ML_MODEL_CACHE_DIR = ROOT_DIR / "gen_view" / "xgboost" / ".cache"

def parse_args():
    parser = argparse.ArgumentParser(
        description="Backtest EW/MVO/BL on dataset"
    )
    parser.add_argument(
        "--start-date", default=None, help="Override start date YYYY-MM-DD"
    )
    parser.add_argument("--end-date", default=None, help="Override end date YYYY-MM-DD")
    parser.add_argument(
        "--no-plot", action="store_true", help="Disable NAV comparison plot"
    )
    parser.add_argument(
        "--assets-config",
        default=None,
        help="Path to assets JSON config (default: datasets/assets.json)",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated asset list, e.g. E1VFVN30,GOLD,DCDS",
    )
    parser.add_argument(
        "--phase",
        choices=list(PHASE_PERIODS.keys()),
        default=BACKTEST_PHASE,
        help="Backtest phase: train/test/full",
    )
    parser.add_argument(
        "--view-mode",
        choices=["rule_based", "relative", "ml", "combined", "ranking", "ranking_absolute"],
        default=VIEW_MODE,
        help="View generation mode",
    )
    parser.add_argument(
        "--ml-model-type",
        choices=["xgboost"],
        default=ML_MODEL_TYPE,
        help="ML model for ml/combined view mode",
    )
    parser.add_argument(
        "--ml-training-mode",
        choices=["pretrained", "walk_forward"],
        default=ML_TRAINING_MODE,
        help="ML training mode: pretrained (load cached) or walk_forward (retrain during backtest)",
    )
    return parser.parse_args()


def load_vn30_universe_prices(start_date, end_date, phase, window):
    """Load price data for the full VN30 stock universe (for K-Medoids selection)."""
    vn30_list_path = ROOT_DIR / VN30_LIST_PATH
    with open(vn30_list_path, "r") as f:
        vn30_tickers = [line.strip() for line in f if line.strip()]

    # Build asset config for VN30 stocks
    vn30_assets = {}
    for ticker in vn30_tickers:
        vn30_assets[ticker] = {
            "full_path": ROOT_DIR / f"datasets/stocks/full/{ticker}.csv",
            "train_path": ROOT_DIR / f"datasets/stocks/train/{ticker}_train.csv",
            "test_path": ROOT_DIR / f"datasets/stocks/test/{ticker}_test.csv",
            "date_col": "date",
            "price_col": "close",
        }

    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=vn30_assets,
        phase=phase,
        data_mode=BACKTEST_DATA_MODE,
        window=window,
    )
    return prices


def load_market_proxy_prices(start_date, end_date, phase, window):
    """Load E1VFVN30 ETF prices as market proxy."""
    market_asset = {
        "E1VFVN30": {
            "full_path": ROOT_DIR / "datasets/stocks/full/E1VFVN30.csv",
            "train_path": ROOT_DIR / "datasets/stocks/train/E1VFVN30_train.csv",
            "test_path": ROOT_DIR / "datasets/stocks/test/E1VFVN30_test.csv",
            "date_col": "date",
            "price_col": "close",
        }
    }
    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=market_asset,
        phase=phase,
        data_mode=BACKTEST_DATA_MODE,
        window=window,
    )
    return prices["E1VFVN30"]


def load_ml_model(model_type: str) -> XGBoostCoreModel:
    model_candidates = {
        "xgboost": [
            ML_MODEL_CACHE_DIR / "xgboost_models.pkl",
            ROOT_DIR / ".cache" / "xgboost_models.pkl",
        ],
    }

    candidates = model_candidates.get(model_type, [])
    model_path = next((p for p in candidates if p.exists()), None)

    if model_path is None:
        searched = "\n".join(str(p) for p in candidates)
        raise FileNotFoundError(
            "Khong tim thay model da train truoc do.\n"
            "Hay train model truoc bang: python gen_view/xgboost/model_train.py --method xgboost\n"
            f"Da tim o:\n{searched}"
        )

    model = XGBoostCoreModel()
    model.load(model_path)
    return model


def optimize_weight(mu, sigma, risk_aversion=0.5, max_weight=MAX_POSITION_SIZE):
    mu = np.asarray(mu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    n = len(mu)

    sigma = np.nan_to_num(sigma, nan=0.0, posinf=0.0, neginf=0.0)
    sigma = 0.5 * (sigma + sigma.T)
    eigvals, eigvecs = np.linalg.eigh(sigma)
    eigvals = np.clip(eigvals, 1e-8, None)
    sigma = eigvecs @ np.diag(eigvals) @ eigvecs.T

    w = cp.Variable(n)
    objective = cp.Maximize(mu @ w - risk_aversion * cp.quad_form(w, sigma))
    constraints = [cp.sum(w) == 1, w >= 0, w <= max_weight]
    problem = cp.Problem(objective, constraints)

    installed = set(cp.installed_solvers())
    for solver_name in ["ECOS", "OSQP", "SCS"]:
        if solver_name in installed:
            try:
                problem.solve(solver=getattr(cp, solver_name))
                if (
                    problem.status in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]
                    and w.value is not None
                ):
                    weight = np.maximum(w.value, 0)
                    total = np.sum(weight)
                    if total > 0:
                        return weight / total
            except Exception:
                continue

    return np.full(n, 1.0 / n)


def optimize_weight_ranking(
    mu,
    sigma,
    assets,
    risk_aversion=RANKING_RISK_AVERSION_BASE,
    max_weight=MAX_POSITION_SIZE,
    min_defensive_weight=RANKING_MIN_DEFENSIVE_WEIGHT,
    max_equity_exposure=RANKING_MAX_EQUITY_EXPOSURE,
    defensive_assets=None,
):
    """
    Constrained MVO for ranking mode with downside protection.

    Additional constraints beyond standard MVO:
    1. sum(defensive_assets weights) >= min_defensive_weight
    2. sum(stock weights) <= max_equity_exposure
    3. Higher risk_aversion penalizes variance more heavily
    """
    if defensive_assets is None:
        defensive_assets = ["GOLD", "MBBOND"]

    mu = np.asarray(mu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    n = len(mu)

    sigma = np.nan_to_num(sigma, nan=0.0, posinf=0.0, neginf=0.0)
    sigma = 0.5 * (sigma + sigma.T)
    eigvals, eigvecs = np.linalg.eigh(sigma)
    eigvals = np.clip(eigvals, 1e-8, None)
    sigma = eigvecs @ np.diag(eigvals) @ eigvecs.T

    defensive_indices = [i for i, a in enumerate(assets) if a in defensive_assets]
    stock_indices = [i for i, a in enumerate(assets) if a not in defensive_assets]

    w = cp.Variable(n)
    objective = cp.Maximize(mu @ w - risk_aversion * cp.quad_form(w, sigma))

    constraints = [
        cp.sum(w) == 1,
        w >= 0,
        w <= max_weight,
    ]

    if defensive_indices:
        constraints.append(cp.sum(w[defensive_indices]) >= min_defensive_weight)

    if stock_indices:
        constraints.append(cp.sum(w[stock_indices]) <= max_equity_exposure)

    problem = cp.Problem(objective, constraints)

    installed = set(cp.installed_solvers())
    for solver_name in ["ECOS", "OSQP", "SCS"]:
        if solver_name in installed:
            try:
                problem.solve(solver=getattr(cp, solver_name))
                if (
                    problem.status in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]
                    and w.value is not None
                ):
                    weight = np.maximum(w.value, 0)
                    total = np.sum(weight)
                    if total > 0:
                        return weight / total
            except Exception:
                continue

    # Fallback: give min_defensive_weight to defensive, rest equal across stocks
    fallback = np.zeros(n)
    if defensive_indices:
        def_w = min_defensive_weight / len(defensive_indices)
        for i in defensive_indices:
            fallback[i] = def_w
    if stock_indices:
        stock_w = (1.0 - min_defensive_weight) / len(stock_indices)
        for i in stock_indices:
            fallback[i] = stock_w
    return fallback


def generate_dynamic_views(
    price_window: pd.DataFrame,
    assets: list,
    mode: str = VIEW_MODE,
    ml_model=None,
    ml_min_return_threshold: float = ML_MIN_RETURN_THRESHOLD,
):
    """
    Generate views dynamically based on the selected mode.
    
    Parameters
    ----------
    price_window : pd.DataFrame
        Price data for the lookback window (used for indicator calculation)
    assets : list
        List of asset names
    mode : str
        View generation mode: "rule_based", "relative", "ml", "combined"
    ml_model : XGBoostCoreModel, optional
        Trained ML Model (used when mode is "ml" or "combined")
    ml_min_return_threshold : float
        Minimum predicted return to generate a view
    
    Returns
    -------
    tuple
        (P matrix, Q vector, confidence vector, view names)
    """
    views = []
    
    if mode == "rule_based":
        views = generate_rule_based_views(price_window)
    elif mode == "relative":
        views = generate_relative_views(price_window)
    elif mode == "ml":
        if ml_model is None:
            return None, None, None, []
        predictions = ml_model.predict(price_window)
        views = generate_ml_views(
            predictions,
            prediction_horizon=ml_model.prediction_horizon,
            min_return_threshold=ml_min_return_threshold,
        )
    elif mode == "combined":
        rule_views = generate_rule_based_views(price_window)
        rel_views = generate_relative_views(price_window)
        static_views = generate_static_views()
        if ml_model is not None:
            predictions = ml_model.predict(price_window)
            ml_views = generate_ml_views(
                predictions,
                prediction_horizon=ml_model.prediction_horizon,
                min_return_threshold=ml_min_return_threshold,
            )
        else:
            ml_views = []
        views = combine_views(
            rule_views, rel_views, ml_views, static_views, COMBINED_VIEW_WEIGHTS
        )
    
    return build_views_matrix(views, assets)


def black_litterman_posterior_mu(
    sigma,
    market_weights,
    p,
    q,
    confidences,
    tau=BL_TAU,
    delta=BL_DELTA,
):
    sigma = np.asarray(sigma, dtype=float)
    market_weights = np.asarray(market_weights, dtype=float)
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)
    confidences = np.asarray(confidences, dtype=float)

    sigma = np.nan_to_num(sigma, nan=0.0, posinf=0.0, neginf=0.0)
    sigma = 0.5 * (sigma + sigma.T)
    eigvals, eigvecs = np.linalg.eigh(sigma)
    eigvals = np.clip(eigvals, 1e-8, None)
    sigma = eigvecs @ np.diag(eigvals) @ eigvecs.T

    pi = delta * sigma @ market_weights
    omega_diag = np.diag(p @ (tau * sigma) @ p.T)
    omega_diag = np.clip(omega_diag, 1e-10, None)
    confidences = np.clip(confidences, 1e-6, 1.0)
    omega = np.diag(omega_diag / confidences)

    inv_tau_sigma = np.linalg.inv(tau * sigma)
    inv_omega = np.linalg.inv(omega)

    middle = inv_tau_sigma + p.T @ inv_omega @ p
    rhs = inv_tau_sigma @ pi + p.T @ inv_omega @ q
    return np.linalg.solve(middle, rhs)


def backtest(
    prices,
    window=WINDOW,
    rebalance_freq=REBALANCE_FREQ,
    initial_nav=INITIAL_NAV,
    view_mode=VIEW_MODE,
    ml_model=None,
    ml_min_return_threshold=ML_MIN_RETURN_THRESHOLD,
    ml_training_mode="pretrained",
    retrain_frequency=ML_RETRAIN_FREQUENCY,
    # NEW: ranking mode parameters
    ranking_universe_prices=None,   # Full VN30 stock prices for selection
    ranking_market_prices=None,     # E1VFVN30 for features
):
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
    views_history = []  # Track generated views at each rebalance

    # Walk-forward state
    if view_mode in ("ml", "combined") and ml_training_mode == "walk_forward" and ml_model is None:
        ml_model = XGBoostEnsembleModel()
        last_retrain_t = -retrain_frequency  # force first train ASAP
    else:
        last_retrain_t = None

    prediction_horizon = getattr(ml_model, "prediction_horizon", DEFAULT_PREDICTION_HORIZON) if ml_model else DEFAULT_PREDICTION_HORIZON

    # Ranking mode state (shared for 'ranking' and 'ranking_absolute')
    ranking_model = None
    ranking_abs_model = None
    selected_stocks = None
    last_reselect_t = -RANKING_RESELECT_FREQUENCY  # force first selection
    last_ranking_retrain_t = -RANKING_RETRAIN_FREQUENCY  # force first train

    if view_mode == "ranking":
        ranking_model = XGBoostRankingModel()
        if ranking_universe_prices is None or ranking_market_prices is None:
            raise ValueError(
                "ranking mode requires ranking_universe_prices and ranking_market_prices"
            )
    elif view_mode == "ranking_absolute":
        ranking_abs_model = XGBoostEnsembleModel()
        if ranking_universe_prices is None or ranking_market_prices is None:
            raise ValueError(
                "ranking_absolute mode requires ranking_universe_prices and ranking_market_prices"
            )

    for t in range(window, len(returns)):
        hist = returns.iloc[t - window : t]
        r_t = returns.iloc[t].values

        ew_nav.append(ew_nav[-1] * (1 + np.dot(ew_weight, r_t)))
        ew_weights_hist.append(ew_weight.copy())

        if (t - window) % rebalance_freq == 0:
            mu = hist.mean().values
            sigma = hist.cov().values
            mvo_weight = optimize_weight(mu, sigma)

            market_weights = np.full(m, 1.0 / m)

            if view_mode == "ranking":
                # --- RANKING MODE ---
                # Re-select representative stocks if due
                if (
                    t - last_reselect_t >= RANKING_RESELECT_FREQUENCY
                    or selected_stocks is None
                ):
                    # Use only VN30 prices up to current time for selection
                    universe_up_to_t = ranking_universe_prices.iloc[: t + window]
                    selected_stocks = select_representatives(
                        universe_up_to_t, k=RANKING_K
                    )
                    last_reselect_t = t

                # Retrain ranking model if due
                if (
                    t - last_ranking_retrain_t >= RANKING_RETRAIN_FREQUENCY
                    or not ranking_model.is_trained
                ):
                    train_end = t - RANKING_PREDICTION_HORIZON  # embargo gap
                    if train_end > RANKING_FEATURE_WINDOW + 50:
                        stock_prices_train = ranking_universe_prices[selected_stocks].iloc[
                            :train_end
                        ]
                        market_train = ranking_market_prices.iloc[:train_end]
                        ranking_model.train(
                            stock_prices_train, market_train, verbose=False
                        )
                        last_ranking_retrain_t = t

                # Predict rankings and generate relative views
                if ranking_model.is_trained and selected_stocks is not None:
                    lookback_start = max(0, t - RANKING_FEATURE_WINDOW - 30)
                    stock_prices_recent = ranking_universe_prices[selected_stocks].iloc[
                        lookback_start : t + window
                    ]
                    market_recent = ranking_market_prices.iloc[
                        lookback_start : t + window
                    ]
                    rank_scores, ensemble_std = ranking_model.predict(
                        stock_prices_recent, market_recent
                    )

                    p_view, q_view, conf_view, view_names = generate_ranking_relative_views(
                        rank_scores, ensemble_std, assets, spread=RANKING_VIEW_SPREAD
                    )
                else:
                    p_view, q_view, conf_view, view_names = None, None, None, []

                # --- RANKING RISK MANAGEMENT ---
                # Detect market regime
                regime = detect_market_regime(returns, t)

                # Apply volatility dampener to ranking views
                if conf_view is not None:
                    if regime["vol_ratio"] > RANKING_VOL_DAMPENER_THRESHOLD:
                        dampener = RANKING_VOL_DAMPENER_THRESHOLD / regime["vol_ratio"]
                        conf_view = conf_view * dampener

                # Inject defensive views during stress/crisis
                if regime["regime"] in ("stress", "crisis"):
                    def_p, def_q, def_conf, def_names = generate_defensive_views(
                        regime, assets
                    )
                    if def_p is not None:
                        if p_view is not None:
                            p_view = np.vstack([p_view, def_p])
                            q_view = np.concatenate([q_view, def_q])
                            conf_view = np.concatenate([conf_view, def_conf])
                            view_names = list(view_names) + list(def_names)
                        else:
                            p_view, q_view, conf_view = def_p, def_q, def_conf
                            view_names = list(def_names)

                # Record views history
                views_history.append({
                    "date": returns.index[t],
                    "view_names": view_names if p_view is not None else [],
                    "q_values": q_view.tolist() if q_view is not None else [],
                    "confidences": conf_view.tolist() if conf_view is not None else [],
                })

                # Black-Litterman posterior
                if p_view is not None:
                    mu_bl = black_litterman_posterior_mu(
                        sigma, market_weights, p_view, q_view, conf_view
                    )
                else:
                    mu_bl = mu

                # Use constrained optimizer with regime-adaptive risk aversion
                current_risk_aversion = (
                    RANKING_RISK_AVERSION_STRESS
                    if regime["regime"] == "crisis"
                    else RANKING_RISK_AVERSION_BASE
                )
                bl_weight = optimize_weight_ranking(
                    mu_bl,
                    sigma,
                    assets,
                    risk_aversion=current_risk_aversion,
                    min_defensive_weight=RANKING_MIN_DEFENSIVE_WEIGHT,
                    max_equity_exposure=RANKING_MAX_EQUITY_EXPOSURE,
                )
            elif view_mode == "ranking_absolute":
                # --- RANKING ABSOLUTE MODE ---
                # Re-select representative stocks if due (same logic as ranking)
                if (
                    t - last_reselect_t >= RANKING_RESELECT_FREQUENCY
                    or selected_stocks is None
                ):
                    universe_up_to_t = ranking_universe_prices.iloc[: t + window]
                    selected_stocks = select_representatives(
                        universe_up_to_t, k=RANKING_K
                    )
                    last_reselect_t = t

                # Retrain XGBoost Ensemble (regression) on selected stocks if due
                if (
                    t - last_ranking_retrain_t >= RANKING_RETRAIN_FREQUENCY
                    or not ranking_abs_model.is_trained
                ):
                    train_end = t - RANKING_PREDICTION_HORIZON  # embargo gap
                    if train_end > RANKING_FEATURE_WINDOW + 50:
                        # Build price table for selected stocks only
                        stock_prices_train = ranking_universe_prices[selected_stocks].iloc[:train_end]
                        ranking_abs_model.train(stock_prices_train, verbose=False)
                        last_ranking_retrain_t = t

                # Predict absolute returns for selected stocks
                if ranking_abs_model.is_trained and selected_stocks is not None:
                    lookback_start = max(0, t - RANKING_FEATURE_WINDOW - 30)
                    stock_prices_recent = ranking_universe_prices[selected_stocks].iloc[
                        lookback_start : t + window
                    ]
                    predictions = ranking_abs_model.predict(stock_prices_recent)
                    # Generate absolute ML views
                    ml_views = generate_ml_views(
                        predictions,
                        prediction_horizon=ranking_abs_model.prediction_horizon,
                        min_return_threshold=ML_MIN_RETURN_THRESHOLD,
                    )
                    p_view, q_view, conf_view, view_names = build_views_matrix(
                        ml_views, assets
                    )
                else:
                    p_view, q_view, conf_view, view_names = None, None, None, []

                # --- RISK MANAGEMENT (same as ranking mode) ---
                regime = detect_market_regime(returns, t)

                # Apply volatility dampener
                if conf_view is not None:
                    if regime["vol_ratio"] > RANKING_VOL_DAMPENER_THRESHOLD:
                        dampener = RANKING_VOL_DAMPENER_THRESHOLD / regime["vol_ratio"]
                        conf_view = conf_view * dampener

                # Inject defensive views during stress/crisis
                if regime["regime"] in ("stress", "crisis"):
                    def_p, def_q, def_conf, def_names = generate_defensive_views(
                        regime, assets
                    )
                    if def_p is not None:
                        if p_view is not None:
                            p_view = np.vstack([p_view, def_p])
                            q_view = np.concatenate([q_view, def_q])
                            conf_view = np.concatenate([conf_view, def_conf])
                            view_names = list(view_names) + list(def_names)
                        else:
                            p_view, q_view, conf_view = def_p, def_q, def_conf
                            view_names = list(def_names)

                # Record views history
                views_history.append({
                    "date": returns.index[t],
                    "view_names": view_names if p_view is not None else [],
                    "q_values": q_view.tolist() if q_view is not None else [],
                    "confidences": conf_view.tolist() if conf_view is not None else [],
                })

                # Black-Litterman posterior
                if p_view is not None:
                    mu_bl = black_litterman_posterior_mu(
                        sigma, market_weights, p_view, q_view, conf_view
                    )
                else:
                    mu_bl = mu

                # Use constrained optimizer with regime-adaptive risk aversion
                current_risk_aversion = (
                    RANKING_RISK_AVERSION_STRESS
                    if regime["regime"] == "crisis"
                    else RANKING_RISK_AVERSION_BASE
                )
                bl_weight = optimize_weight_ranking(
                    mu_bl,
                    sigma,
                    assets,
                    risk_aversion=current_risk_aversion,
                    min_defensive_weight=RANKING_MIN_DEFENSIVE_WEIGHT,
                    max_equity_exposure=RANKING_MAX_EQUITY_EXPOSURE,
                )
            else:
                # --- EXISTING MODES (rule_based, relative, ml, combined) ---
                # Walk-forward: retrain model if due
                if view_mode in ("ml", "combined") and ml_training_mode == "walk_forward" and last_retrain_t is not None:
                    if t - last_retrain_t >= retrain_frequency:
                        train_end = t - prediction_horizon  # embargo gap
                        feature_window = getattr(ml_model, "feature_window", DEFAULT_FEATURE_WINDOW)
                        min_samples = getattr(ml_model, "_min_train_check", MIN_TRAIN_SAMPLES)
                        if train_end >= min_samples + feature_window:
                            train_prices = prices.iloc[:train_end]
                            ml_model.train(train_prices, verbose=False)
                            last_retrain_t = t

                # Use data up to current time only (no look-ahead)
                price_window = prices.iloc[max(0, t - window - 30) : t]

                # Only generate ML views if model is trained
                effective_ml_model = ml_model
                if view_mode in ("ml", "combined") and ml_training_mode == "walk_forward" and hasattr(ml_model, "is_trained"):
                    if not ml_model.is_trained:
                        effective_ml_model = None

                p_view, q_view, conf_view, view_names = generate_dynamic_views(
                    price_window,
                    assets,
                    view_mode,
                    ml_model=effective_ml_model,
                    ml_min_return_threshold=ml_min_return_threshold,
                )

                # Volatility-based confidence dampener: reduce confidence when
                # recent volatility spikes vs historical (detects crash onset)
                if conf_view is not None and view_mode in ("ml", "combined"):
                    recent_vol = returns.iloc[max(0, t - 20) : t].std().mean()
                    hist_vol = returns.iloc[max(0, t - 120) : t].std().mean()
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
                    mu_bl = black_litterman_posterior_mu(
                        sigma, market_weights, p_view, q_view, conf_view
                    )
                else:
                    mu_bl = mu
                bl_weight = optimize_weight(mu_bl, sigma)

            rebalance_dates.append(returns.index[t])

        mvo_nav.append(mvo_nav[-1] * (1 + np.dot(mvo_weight, r_t)))
        bl_nav.append(bl_nav[-1] * (1 + np.dot(bl_weight, r_t)))
        mvo_weights_hist.append(mvo_weight.copy())
        bl_weights_hist.append(bl_weight.copy())

    nav_index = returns.index[window - 1 :]
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
        "view_mode": view_mode,
        "ml_model": ml_model,
    }


def sharpe_ratio(nav_series):
    ret = nav_series.pct_change().dropna()
    if len(ret) == 0 or ret.std() == 0:
        return np.nan
    rf_daily = (1 + RISK_FREE_RATE_ANNUAL) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    excess_ret = ret - rf_daily
    excess_vol = excess_ret.std()
    if excess_vol == 0:
        return np.nan
    return np.sqrt(TRADING_DAYS_PER_YEAR) * excess_ret.mean() / excess_vol


def max_drawdown(nav_series):
    peak = nav_series.cummax()
    drawdown = nav_series / peak - 1
    return drawdown.min()


def get_next_period_weights(
    returns,
    prices,
    as_of_date,
    window=WINDOW,
    view_mode=VIEW_MODE,
    ml_model=None,
    ml_min_return_threshold=ML_MIN_RETURN_THRESHOLD,
):
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
    
    # Generate views based on mode
    price_eligible = prices.loc[prices.index <= as_of_date]
    price_window = price_eligible.iloc[-window - 30:] if len(price_eligible) > window + 30 else price_eligible
    p_view, q_view, conf_view, view_names = generate_dynamic_views(
        price_window,
        assets,
        view_mode,
        ml_model=ml_model,
        ml_min_return_threshold=ml_min_return_threshold,
    )
    
    if p_view is not None:
        mu_bl = black_litterman_posterior_mu(
            sigma, market_weights, p_view, q_view, conf_view
        )
    else:
        mu_bl = mu

    w_mvo = optimize_weight(mu, sigma)
    w_bl = optimize_weight(mu_bl, sigma)
    return w_mvo, w_bl, hist.index[-1], view_names


def main():
    args = parse_args()
    phase = args.phase
    view_mode = args.view_mode
    start_date, end_date = resolve_period(args, PHASE_PERIODS, phase)
    selected_assets = None
    if args.assets:
        selected_assets = [item.strip() for item in args.assets.split(",") if item.strip()]

    assets = load_assets_config(
        config_path=args.assets_config,
        selected_assets=selected_assets,
    )

    print(
        f"Phase={phase} | Data mode={BACKTEST_DATA_MODE} | Period={start_date} -> {end_date}"
    )
    print(f"View mode={view_mode}")
    if view_mode in ("ml", "combined"):
        print(f"ML training mode={args.ml_training_mode}")
    print(f"Assets: {', '.join(assets.keys())}")

    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=assets,
        phase=phase,
        data_mode=BACKTEST_DATA_MODE,
        window=WINDOW,
    )
    asset_summary = summarize_asset_returns(prices, TRADING_DAYS_PER_YEAR)

    print(
        f"Khoang du lieu dung backtest: {prices.index.min().date()} -> {prices.index.max().date()} ({len(prices)} phien)"
    )

    print("\n" + "=" * 70)
    print("BANG RETURN TUNG ASSET")
    print(asset_summary.to_string(float_format=lambda x: f"{x:,.2%}"))

    print("\n" + "=" * 70)
    print(f"BLACK-LITTERMAN VIEW MODE: {view_mode.upper()}")
    if view_mode == "rule_based":
        print("  - Su dung: MA Crossover, RSI, Momentum")
    elif view_mode == "relative":
        print("  - Su dung: Momentum comparison giua cac cap assets")
    elif view_mode == "ml":
        print(f"  - Su dung: ML model predictions ({args.ml_model_type})")
    elif view_mode == "combined":
        print(
            f"  - Ket hop: rule_based ({COMBINED_VIEW_WEIGHTS[0]:.0%}),"
            f" relative ({COMBINED_VIEW_WEIGHTS[1]:.0%}),"
            f" ml ({COMBINED_VIEW_WEIGHTS[2]:.0%}),"
            f" static ({COMBINED_VIEW_WEIGHTS[3]:.0%})"
        )
    elif view_mode == "ranking":
        print(f"  - K-Medoids representative selection (K={RANKING_K}) from VN30 universe")
        print(f"  - XGBoost Ranker -> Relative Views -> BL")
        print(f"  - Retrain every {RANKING_RETRAIN_FREQUENCY} days, reselect every {RANKING_RESELECT_FREQUENCY} days")
    elif view_mode == "ranking_absolute":
        print(f"  - K={RANKING_K} representative stocks from VN30 (combinatorial selection)")
        print(f"  - XGBoost Regression -> Absolute Views -> BL")
        print(f"  - Retrain every {RANKING_RETRAIN_FREQUENCY} days, reselect every {RANKING_RESELECT_FREQUENCY} days")
        print(f"  - Risk management: defensive floor {RANKING_MIN_DEFENSIVE_WEIGHT:.0%}, equity cap {RANKING_MAX_EQUITY_EXPOSURE:.0%}")

    ml_model = None
    ml_training_mode = args.ml_training_mode
    if view_mode in ("ml", "combined"):
        print("\n" + "=" * 70)
        if ml_training_mode == "walk_forward":
            print(f"ML VIEW GENERATOR: WALK-FORWARD ({args.ml_model_type} ensemble)")
            print(f"  - Retrain every {ML_RETRAIN_FREQUENCY} trading days (expanding window)")
            # print(f"  - Ensemble size: 5 models per asset")
            print(f"  - Confidence: ensemble disagreement-based")
            # ml_model will be created inside backtest() function
        else:
            print(f"LOAD ML VIEW GENERATOR ({args.ml_model_type})")
            try:
                ml_model = load_ml_model(args.ml_model_type)
            except FileNotFoundError as e:
                print(f"\nERROR: {e}")
                return

    # Load ranking universe data if needed
    ranking_universe_prices = None
    ranking_market_prices = None
    if view_mode in ("ranking", "ranking_absolute"):
        print("\nLoading VN30 universe for ranking mode...")
        ranking_universe_prices = load_vn30_universe_prices(
            start_date, end_date, phase, WINDOW
        )
        ranking_market_prices = load_market_proxy_prices(
            start_date, end_date, phase, WINDOW
        )
        # Align indices
        common_idx = (
            prices.index
            .intersection(ranking_universe_prices.index)
            .intersection(ranking_market_prices.index)
        )
        prices = prices.loc[common_idx]
        ranking_universe_prices = ranking_universe_prices.loc[common_idx]
        ranking_market_prices = ranking_market_prices.loc[common_idx]
        print(
            f"  Loaded {len(ranking_universe_prices.columns)} VN30 stocks, "
            f"{len(ranking_universe_prices)} trading days"
        )

    result = backtest(
        prices,
        view_mode=view_mode,
        ml_model=ml_model,
        ml_training_mode=ml_training_mode,
        retrain_frequency=ML_RETRAIN_FREQUENCY,
        ranking_universe_prices=ranking_universe_prices,
        ranking_market_prices=ranking_market_prices,
    )
    ew_nav = result["ew_nav"]
    mvo_nav = result["mvo_nav"]
    bl_nav = result["bl_nav"]

    print("\n" + "=" * 70)
    print(f"KET QUA BACKTEST ({start_date} den {end_date}, theo du lieu kha dung)")
    print(
        f"EW   | NAV cuoi: {ew_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(ew_nav):6.2f} | MDD: {max_drawdown(ew_nav):7.2%}"
    )
    print(
        f"MVO  | NAV cuoi: {mvo_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(mvo_nav):6.2f} | MDD: {max_drawdown(mvo_nav):7.2%}"
    )
    print(
        f"BL   | NAV cuoi: {bl_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(bl_nav):6.2f} | MDD: {max_drawdown(bl_nav):7.2%}"
    )

    # # Show sample of dynamic views generated during backtest
    # if result.get("views_history"):
    #     print("\n" + "=" * 70)
    #     print("MAU VIEWS SINH RA TRONG QUA TRINH BACKTEST")
    #     print("=" * 70)
    #     views_hist = result["views_history"]
    #     # Show first 3 and last 3 rebalance dates
    #     sample_indices = list(range(min(3, len(views_hist)))) + list(range(max(0, len(views_hist) - 3), len(views_hist)))
    #     sample_indices = sorted(set(sample_indices))
    #     for i in sample_indices:
    #         vh = views_hist[i]
    #         print(f"\n{vh['date'].strftime('%Y-%m-%d')}:")
    #         if vh['view_names']:
    #             for name, q, conf in zip(vh['view_names'], vh['q_values'], vh['confidences']):
    #                 print(f"  - {name}: Q={q:.6f} (daily), conf={conf:.2f}")
    #         else:
    #             print("  - Khong co view (BL fallback ve mu lich su)")

    # Log view history to file
    log_path = log_view_history(
        result["views_history"],
        view_mode=view_mode,
        phase=phase,
        assets=result["assets"],
        backtest_metrics={
            "EW": {
                "final_nav": float(ew_nav.iloc[-1]),
                "sharpe": float(sharpe_ratio(ew_nav)),
                "mdd": float(max_drawdown(ew_nav)),
            },
            "MVO": {
                "final_nav": float(mvo_nav.iloc[-1]),
                "sharpe": float(sharpe_ratio(mvo_nav)),
                "mdd": float(max_drawdown(mvo_nav)),
            },
            "BL": {
                "final_nav": float(bl_nav.iloc[-1]),
                "sharpe": float(sharpe_ratio(bl_nav)),
                "mdd": float(max_drawdown(bl_nav)),
            },
        },
        ml_training_mode=ml_training_mode if view_mode in ("ml", "combined") else None,
    )


    # ## PREDICT NEXT PERIOD WEIGHTS
    # as_of_date = pd.Timestamp(end_date)
    # # Use the model from backtest (in walk_forward mode it's the trained ensemble)
    # final_ml_model = result.get("ml_model", ml_model)
    # w_mvo_next, w_bl_next, last_hist_date, next_view_names = get_next_period_weights(
    #     result["returns"],
    #     prices,
    #     as_of_date=as_of_date,
    #     window=WINDOW,
    #     view_mode=view_mode,
    #     ml_model=final_ml_model,
    # )

    # print("\n" + "=" * 70)
    # print(f"TRONG SO GOI Y CHO GIAI DOAN TIEP THEO SAU {end_date}")
    # print(f"(Uoc luong tu cua so {WINDOW} phien gan nhat den {last_hist_date.date()})")
    # print("=" * 70)
    # print("MVO:")
    # for asset, weight in zip(result["assets"], w_mvo_next):
    #     print(f"  {asset:8}: {weight:7.2%}")
    # print("BL:")
    # for asset, weight in zip(result["assets"], w_bl_next):
    #     print(f"  {asset:8}: {weight:7.2%}")
    # if next_view_names:
    #     print(f"  Views used: {', '.join(next_view_names)}")

    if not args.no_plot:
        plt.figure(figsize=(12, 6))
        plt.plot(ew_nav.index, ew_nav.values, label="EW")
        plt.plot(mvo_nav.index, mvo_nav.values, label="MVO")
        plt.plot(bl_nav.index, bl_nav.values, label=f"BL ({view_mode})")
        plt.title(f"Backtest with Assets ({phase}): EW vs MVO vs BL ({view_mode})")
        plt.ylabel("NAV (initial = 100,000)")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
