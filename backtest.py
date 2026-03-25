import argparse
from datetime import datetime
from pathlib import Path

import cvxpy as cp
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from view_generators import (
    generate_rule_based_views,
    generate_relative_views,
    generate_ml_views,
    build_views_matrix,
    combine_views,
)

# ====================== CONFIG ======================
TRAIN_START_DATE = "2020-01-01"
SPLIT_DATE = "2023-10-01"
TEST_END_DATE = datetime.now().strftime("%Y-%m-%d")
BACKTEST_PHASE = "train"
BACKTEST_DATA_MODE = "split"

WINDOW = 20
REBALANCE_FREQ = 5
INITIAL_NAV = 100000.0
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.06

BL_TAU = 0.05
BL_DELTA = 2.5
BL_VIEW_CONFIDENCE = 0.5

# View generation mode: "static", "rule_based", "relative", "ml", "combined"
VIEW_MODE = "rule_based"

# Static views (used when VIEW_MODE = "static")
STATIC_VIEWS = [
    {
        "name": "GOLD_over_E1VFVN30",
        "legs": {"GOLD": 1.0, "E1VFVN30": -1.0},
        "view_return_annual": 0.06,
        "confidence": 0.70,
    },
    {
        "name": "MBBOND_over_DCDS",
        "legs": {"MBBOND": 1.0, "DCDS": -1.0},
        "view_return_annual": 0.015,
        "confidence": 0.60,
    },
]

# Combined view weights: (rule_based, relative, ml)
COMBINED_VIEW_WEIGHTS = (0.4, 0.4, 0.2)

ROOT_DIR = Path(__file__).resolve().parents[0]
DATASETS_DIR = ROOT_DIR / "datasets"

ASSETS = {
    "E1VFVN30": {
        "full_path": DATASETS_DIR / "stocks" / "full" / "E1VFVN30.csv",
        "train_path": DATASETS_DIR / "stocks" / "train" / "E1VFVN30_train.csv",
        "test_path": DATASETS_DIR / "stocks" / "test" / "E1VFVN30_test.csv",
        "date_col": "date",
        "price_col": "close",
    },
    "GOLD": {
        "full_path": DATASETS_DIR / "gold" / "gold_test.csv",
        "train_path": DATASETS_DIR / "gold" / "gold_train.csv",
        "test_path": DATASETS_DIR / "gold" / "gold_test.csv",
        "date_col": "date",
        "price_col": "sjc_sell",
    },
    "DCDS": {
        "full_path": DATASETS_DIR / "funds" / "full" / "DCDS.csv",
        "train_path": DATASETS_DIR / "funds" / "train" / "DCDS_train.csv",
        "test_path": DATASETS_DIR / "funds" / "test" / "DCDS_test.csv",
        "date_col": "date",
        "price_col": "price",
    },
    "MBBOND": {
        "full_path": DATASETS_DIR / "funds" / "full" / "MBBOND.csv",
        "train_path": DATASETS_DIR / "funds" / "train" / "MBBOND_train.csv",
        "test_path": DATASETS_DIR / "funds" / "test" / "MBBOND_test.csv",
        "date_col": "date",
        "price_col": "price",
    },
}

PHASE_PERIODS = {
    "train": (TRAIN_START_DATE, SPLIT_DATE),
    "test": (SPLIT_DATE, TEST_END_DATE),
    "full": (TRAIN_START_DATE, TEST_END_DATE),
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backtest EW/MVO/BL on TRAIN data only"
    )
    parser.add_argument(
        "--start-date", default=None, help="Override start date YYYY-MM-DD"
    )
    parser.add_argument("--end-date", default=None, help="Override end date YYYY-MM-DD")
    parser.add_argument(
        "--no-plot", action="store_true", help="Disable NAV comparison plot"
    )
    return parser.parse_args()


def resolve_period(args):
    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise ValueError(
                "When overriding dates, both --start-date and --end-date are required"
            )
        return args.start_date, args.end_date
    return PHASE_PERIODS[BACKTEST_PHASE]


def resolve_asset_path(cfg, phase, data_mode):
    if data_mode == "split" and phase in ("train", "test"):
        key = f"{phase}_path"
        p = cfg.get(key)
        if p is not None and Path(p).exists():
            return p
    return cfg["full_path"]


def load_asset_series(asset_name, cfg, phase, data_mode, start_date, end_date):
    if data_mode == "split" and phase == "full":
        train_path = cfg.get("train_path")
        test_path = cfg.get("test_path")
        if (
            train_path is not None
            and test_path is not None
            and Path(train_path).exists()
            and Path(test_path).exists()
        ):
            df_train = pd.read_csv(train_path)
            df_test = pd.read_csv(test_path)
            df = pd.concat([df_train, df_test], ignore_index=True)
        else:
            path = resolve_asset_path(cfg, phase, data_mode)
            df = pd.read_csv(path)
    else:
        path = resolve_asset_path(cfg, phase, data_mode)
        df = pd.read_csv(path)

    df[cfg["date_col"]] = pd.to_datetime(df[cfg["date_col"]], errors="coerce")
    df = df.dropna(subset=[cfg["date_col"], cfg["price_col"]])

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    s = (
        df[(df[cfg["date_col"]] >= start_ts) & (df[cfg["date_col"]] <= end_ts)][
            [cfg["date_col"], cfg["price_col"]]
        ]
        .drop_duplicates(subset=[cfg["date_col"]], keep="last")
        .sort_values(cfg["date_col"])
        .set_index(cfg["date_col"])[cfg["price_col"]]
        .astype(float)
    )
    s.name = asset_name
    return s


def build_price_table(start_date, end_date, phase="full", data_mode="split"):
    calendar = pd.date_range(start=start_date, end=end_date, freq="B")
    data = {}

    for asset, cfg in ASSETS.items():
        series = load_asset_series(asset, cfg, phase, data_mode, start_date, end_date)
        series = series.reindex(calendar).ffill()
        data[asset] = series

    prices = pd.DataFrame(data, index=calendar)
    prices = prices.dropna(how="any")
    if len(prices) <= WINDOW:
        raise ValueError(
            f"Khong du du lieu sau khi dong bo: {len(prices)} dong, can > WINDOW={WINDOW}"
        )
    return prices


def optimize_weight(mu, sigma, risk_aversion=0.5):
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
    constraints = [cp.sum(w) == 1, w >= 0]
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


def build_static_views(assets, trading_days_per_year=TRADING_DAYS_PER_YEAR):
    """Build views from STATIC_VIEWS config (legacy hardcoded views)."""
    asset_to_idx = {asset: i for i, asset in enumerate(assets)}
    p_rows = []
    q_vals = []
    conf_vals = []
    active_names = []

    for view in STATIC_VIEWS:
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
        conf_vals.append(view.get("confidence", BL_VIEW_CONFIDENCE))
        active_names.append(view["name"])

    if len(p_rows) == 0:
        return None, None, None, []

    p = np.array(p_rows, dtype=float)
    q = np.array(q_vals, dtype=float)
    conf = np.array(conf_vals, dtype=float)
    return p, q, conf, active_names


def generate_dynamic_views(price_window: pd.DataFrame, assets: list, mode: str = VIEW_MODE):
    """
    Generate views dynamically based on the selected mode.
    
    Parameters
    ----------
    price_window : pd.DataFrame
        Price data for the lookback window (used for indicator calculation)
    assets : list
        List of asset names
    mode : str
        View generation mode: "static", "rule_based", "relative", "ml", "combined"
    
    Returns
    -------
    tuple
        (P matrix, Q vector, confidence vector, view names)
    """
    if mode == "static":
        return build_static_views(assets)
    
    views = []
    
    if mode == "rule_based":
        views = generate_rule_based_views(price_window)
    elif mode == "relative":
        views = generate_relative_views(price_window)
    elif mode == "ml":
        views = generate_ml_views(price_window, model=None)  # Fallback mode
    elif mode == "combined":
        rule_views = generate_rule_based_views(price_window)
        rel_views = generate_relative_views(price_window)
        ml_views = generate_ml_views(price_window, model=None)
        views = combine_views(rule_views, rel_views, ml_views, COMBINED_VIEW_WEIGHTS)
    else:
        # Unknown mode, fallback to static
        return build_static_views(assets)
    
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
    prices, window=WINDOW, rebalance_freq=REBALANCE_FREQ, initial_nav=INITIAL_NAV, view_mode=VIEW_MODE
):
    returns = prices.pct_change().dropna()
    assets = list(prices.columns)
    m = len(assets)
    
    # For static mode, compute views once upfront
    if view_mode == "static":
        p_view, q_view, conf_view, _ = build_static_views(assets)
    else:
        p_view, q_view, conf_view = None, None, None

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
            
            # Generate views dynamically (except for static mode which is precomputed)
            if view_mode != "static":
                # Get price window for indicator calculation
                # Use prices up to current point (not returns)
                price_window = prices.iloc[max(0, t - window - 30) : t + window]
                p_view, q_view, conf_view, view_names = generate_dynamic_views(
                    price_window, assets, view_mode
                )
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


def get_next_period_weights(returns, prices, as_of_date, window=WINDOW, view_mode=VIEW_MODE):
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
    if view_mode == "static":
        p_view, q_view, conf_view, view_names = build_static_views(assets)
    else:
        # Get price window for dynamic view generation
        price_eligible = prices.loc[prices.index <= as_of_date]
        price_window = price_eligible.iloc[-window - 30:] if len(price_eligible) > window + 30 else price_eligible
        p_view, q_view, conf_view, view_names = generate_dynamic_views(price_window, assets, view_mode)
    
    if p_view is not None:
        mu_bl = black_litterman_posterior_mu(
            sigma, market_weights, p_view, q_view, conf_view
        )
    else:
        mu_bl = mu

    w_mvo = optimize_weight(mu, sigma)
    w_bl = optimize_weight(mu_bl, sigma)
    return w_mvo, w_bl, hist.index[-1], view_names


def summarize_asset_returns(prices):
    returns = prices.pct_change().dropna()
    total_return = prices.iloc[-1] / prices.iloc[0] - 1
    annualized_return = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / len(returns)) - 1
    annualized_vol = returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    return pd.DataFrame(
        {
            "Total Return": total_return,
            "Annualized Return": annualized_return,
            "Annualized Vol": annualized_vol,
        }
    )


def main():
    args = parse_args()
    start_date, end_date = resolve_period(args)

    print("Dang load va dong bo du lieu 4 tai san...")
    print(
        f"Phase={BACKTEST_PHASE} | Data mode={BACKTEST_DATA_MODE} | Period={start_date} -> {end_date}"
    )
    print(f"View mode={VIEW_MODE}")

    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        phase=BACKTEST_PHASE,
        data_mode=BACKTEST_DATA_MODE,
    )
    asset_summary = summarize_asset_returns(prices)

    print(
        f"Khoang du lieu dung backtest: {prices.index.min().date()} -> {prices.index.max().date()} ({len(prices)} phien)"
    )

    print("\n" + "=" * 70)
    print("BANG RETURN TUNG ASSET")
    print("=" * 70)
    print(asset_summary.to_string(float_format=lambda x: f"{x:,.2%}"))

    print("\n" + "=" * 70)
    print(f"BLACK-LITTERMAN VIEW MODE: {VIEW_MODE.upper()}")
    print("=" * 70)
    if VIEW_MODE == "static":
        _, _, _, active_view_names = build_static_views(list(prices.columns))
        if len(active_view_names) == 0:
            print("Khong co view hop le voi tap assets hien tai -> BL fallback ve mu lich su")
        else:
            print("Static views:")
            for name in active_view_names:
                print(f"  - {name}")
    else:
        print(f"Views duoc sinh dong tai moi lan rebalance dua tren {VIEW_MODE} indicators")
        if VIEW_MODE == "rule_based":
            print("  - Su dung: MA Crossover, RSI, Momentum")
        elif VIEW_MODE == "relative":
            print("  - Su dung: Momentum comparison giua cac cap assets")
        elif VIEW_MODE == "ml":
            print("  - Su dung: ML model predictions (fallback: simple momentum)")
        elif VIEW_MODE == "combined":
            print(f"  - Ket hop: rule_based ({COMBINED_VIEW_WEIGHTS[0]:.0%}), relative ({COMBINED_VIEW_WEIGHTS[1]:.0%}), ml ({COMBINED_VIEW_WEIGHTS[2]:.0%})")

    result = backtest(prices, view_mode=VIEW_MODE)
    ew_nav = result["ew_nav"]
    mvo_nav = result["mvo_nav"]
    bl_nav = result["bl_nav"]

    print("\n" + "=" * 70)
    print(f"KET QUA BACKTEST ({start_date} den {end_date}, theo du lieu kha dung)")
    print("=" * 70)
    print(
        f"EW   | NAV cuoi: {ew_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(ew_nav):6.2f} | MDD: {max_drawdown(ew_nav):7.2%}"
    )
    print(
        f"MVO  | NAV cuoi: {mvo_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(mvo_nav):6.2f} | MDD: {max_drawdown(mvo_nav):7.2%}"
    )
    print(
        f"BL   | NAV cuoi: {bl_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(bl_nav):6.2f} | MDD: {max_drawdown(bl_nav):7.2%}"
    )

    # Show sample of dynamic views generated during backtest
    if VIEW_MODE != "static" and result.get("views_history"):
        print("\n" + "=" * 70)
        print("MAU VIEWS SINH RA TRONG QUA TRINH BACKTEST")
        print("=" * 70)
        views_hist = result["views_history"]
        # Show first 3 and last 3 rebalance dates
        sample_indices = list(range(min(3, len(views_hist)))) + list(range(max(0, len(views_hist) - 3), len(views_hist)))
        sample_indices = sorted(set(sample_indices))
        for i in sample_indices:
            vh = views_hist[i]
            print(f"\n{vh['date'].strftime('%Y-%m-%d')}:")
            if vh['view_names']:
                for name, q, conf in zip(vh['view_names'], vh['q_values'], vh['confidences']):
                    print(f"  - {name}: Q={q:.6f} (daily), conf={conf:.2f}")
            else:
                print("  - Khong co view (BL fallback ve mu lich su)")

    as_of_date = pd.Timestamp(end_date)
    w_mvo_next, w_bl_next, last_hist_date, next_view_names = get_next_period_weights(
        result["returns"], prices, as_of_date=as_of_date, window=WINDOW, view_mode=VIEW_MODE
    )

    print("\n" + "=" * 70)
    print(f"TRONG SO GOI Y CHO GIAI DOAN TIEP THEO SAU {end_date}")
    print(f"(Uoc luong tu cua so {WINDOW} phien gan nhat den {last_hist_date.date()})")
    print("=" * 70)
    print("MVO:")
    for asset, weight in zip(result["assets"], w_mvo_next):
        print(f"  {asset:8}: {weight:7.2%}")
    print("BL:")
    for asset, weight in zip(result["assets"], w_bl_next):
        print(f"  {asset:8}: {weight:7.2%}")
    if next_view_names:
        print(f"  Views used: {', '.join(next_view_names)}")

    if not args.no_plot:
        plt.figure(figsize=(12, 6))
        plt.plot(ew_nav.index, ew_nav.values, label="EW")
        plt.plot(mvo_nav.index, mvo_nav.values, label="MVO")
        plt.plot(bl_nav.index, bl_nav.values, label=f"BL ({VIEW_MODE})")
        plt.title(f"Backtest 4 Assets ({BACKTEST_PHASE}): EW vs MVO vs BL ({VIEW_MODE})")
        plt.ylabel("NAV (initial = 100,000)")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
