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
        choices=["rule_based", "relative", "ml", "combined"],
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

            # Cap BL deviation from MVO: BL can tilt towards its view
            # but not deviate too far from MVO's market-based allocation.
            # This protects against catastrophic wrong views while preserving alpha.
            BL_DEVIATION_ALPHA = 0.25  # BL keeps 25% of its deviation from MVO
            bl_weight = mvo_weight + BL_DEVIATION_ALPHA * (bl_weight - mvo_weight)
            # Re-normalize to sum to 1 and clip negatives
            bl_weight = np.maximum(bl_weight, 0)
            bl_weight = bl_weight / bl_weight.sum()

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

    result = backtest(
        prices,
        view_mode=view_mode,
        ml_model=ml_model,
        ml_training_mode=ml_training_mode,
        retrain_frequency=ML_RETRAIN_FREQUENCY,
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
