import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats  # noqa: F401  (kept for Spearman correlation utility)

import backtest as bt
from config import (
    PHASE_PERIODS,
    BACKTEST_PHASE,
    RANKING_K,
    RANKING_RETRAIN_FREQUENCY,
    RANKING_RESELECT_FREQUENCY,
    RANKING_VIEW_SPREAD,
    TRADING_DAYS_PER_YEAR,
    RISK_FREE_RATE_ANNUAL,
    VN30_LIST_PATH,
    WINDOW,
)
from utils.data_loader import build_price_table, load_assets_config


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run portfolio backtests for rule-based, ML XGBoost, and ranking views in one command."
        )
    )
    parser.add_argument(
        "--phase",
        choices=list(PHASE_PERIODS.keys()),
        default=BACKTEST_PHASE,
        help="Backtest phase (train/test/full)",
    )
    parser.add_argument("--start-date", default=None, help="Override start date YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="Override end date YYYY-MM-DD")
    parser.add_argument(
        "--assets-config",
        default=None,
        help="Path to assets config JSON (default: assets.json)",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated assets, e.g. E1VFVN30,GOLD,DCDS,MBBOND",
    )
    parser.add_argument(
        "--output-csv",
        default="reports/backtest_compare_views.csv",
        help="Path to save result table CSV",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Disable chart visualization",
    )
    parser.add_argument(
        "--plot-path",
        default="reports/backtest_compare_views.png",
        help="Path to save NAV comparison chart",
    )
    return parser.parse_args()


def resolve_period(args):
    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise ValueError("When overriding dates, both --start-date and --end-date are required")
        return args.start_date, args.end_date
    return PHASE_PERIODS[args.phase]


# ====================== EXTENDED PORTFOLIO METRICS ======================

def annual_return(nav_series: pd.Series) -> float:
    """Annualized return."""
    total_days = len(nav_series) - 1
    if total_days <= 0:
        return np.nan
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    return (1 + total_return) ** (TRADING_DAYS_PER_YEAR / total_days) - 1


def annual_volatility(nav_series: pd.Series) -> float:
    """Annualized volatility."""
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
    """Calmar ratio = annualized return / max drawdown."""
    total_days = len(nav_series) - 1
    if total_days <= 0:
        return np.nan
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    ann_ret = (1 + total_return) ** (TRADING_DAYS_PER_YEAR / total_days) - 1
    mdd = bt.max_drawdown(nav_series)
    if mdd == 0:
        return np.nan
    return ann_ret / abs(mdd)


def metric_summary(nav_series: pd.Series) -> dict:
    """Comprehensive performance metrics for a NAV series."""
    return {
        "final_nav": float(nav_series.iloc[-1]),
        "ann_return": float(annual_return(nav_series)),
        "ann_volatility": float(annual_volatility(nav_series)),
        "sharpe": float(bt.sharpe_ratio(nav_series)),
        "sortino": float(sortino_ratio(nav_series)),
        "max_drawdown": float(bt.max_drawdown(nav_series)),
        "calmar": float(calmar_ratio(nav_series)),
    }


# ====================== SCENARIO RUNNER ======================

def run_one_mode(
    prices: pd.DataFrame,
    scenario_name: str,
    view_mode: str,
    ml_model=None,
    ranking_universe_prices: pd.DataFrame = None,
    ranking_market_prices: pd.Series = None,
) -> tuple[dict, list[dict]]:
    result = bt.backtest(
        prices,
        view_mode=view_mode,
        ml_model=ml_model,
        ranking_universe_prices=ranking_universe_prices,
        ranking_market_prices=ranking_market_prices,
    )

    views_history = result.get("views_history", [])
    total_views = sum(len(v.get("view_names", [])) for v in views_history)
    rebalance_count = len(views_history)

    rows = [
        {
            "scenario": scenario_name,
            "strategy": strategy_name,
            **metric_summary(nav_series),
            "rebalance_count": rebalance_count,
            "total_generated_views": total_views,
        }
        for strategy_name, nav_series in [
            ("EW", result["ew_nav"]),
            ("MVO", result["mvo_nav"]),
            ("BL", result["bl_nav"]),
        ]
    ]
    return result, rows


# ====================== PLOTTING ======================

def plot_scenarios(results_by_scenario: dict, output_path: str, show_plot: bool = True):
    scenario_order = [
        ("rule_based", "BL (rule_based)"),
        ("ml_xgboost", "BL (ml_xgboost)"),
        ("ranking", "BL (ranking)"),
    ]
    # Only plot scenarios that actually ran
    scenario_order = [s for s in scenario_order if s[0] in results_by_scenario]
    n = len(scenario_order)
    if n == 0:
        print("No scenarios to plot.")
        return

    fig, axes = plt.subplots(1, n, figsize=(7 * n, 6), sharey=True)
    if n == 1:
        axes = [axes]

    for ax, (scenario_key, bl_label) in zip(axes, scenario_order):
        result = results_by_scenario[scenario_key]
        ax.plot(result["ew_nav"].index, result["ew_nav"].values, label="EW")
        ax.plot(result["mvo_nav"].index, result["mvo_nav"].values, label="MVO")
        ax.plot(result["bl_nav"].index, result["bl_nav"].values, label=bl_label)
        ax.set_title(scenario_key)
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("Date")

    axes[0].set_ylabel("NAV (initial = 1.0)")
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3)
    fig.suptitle("Backtest NAV Comparison Across View Generators", fontsize=14)
    plt.tight_layout(rect=[0, 0, 1, 0.92])

    out_path = Path(output_path)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    print(f"Saved comparison plot to: {out_path}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)


# ====================== MAIN ======================

def main():
    args = parse_args()
    start_date, end_date = resolve_period(args)

    selected_assets = None
    if args.assets:
        selected_assets = [item.strip() for item in args.assets.split(",") if item.strip()]

    assets = load_assets_config(
        config_path=args.assets_config,
        selected_assets=selected_assets,
    )

    print("=" * 80)
    print("COMPARE BACKTESTS: EW, MVO, BL(rule_based), BL(ml-xgb), BL(ranking)")
    print("=" * 80)
    print(f"Phase={args.phase} | Period={start_date} -> {end_date}")
    print(f"Assets: {', '.join(assets.keys())}")
    print(
        f"Ranking config: K={RANKING_K}, retrain_freq={RANKING_RETRAIN_FREQUENCY}, "
        f"reselect_freq={RANKING_RESELECT_FREQUENCY}, view_spread={RANKING_VIEW_SPREAD}"
    )

    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=assets,
        phase=args.phase,
        data_mode=bt.BACKTEST_DATA_MODE,
        window=bt.WINDOW,
    )
    print(
        f"Aligned price window: {prices.index.min().date()} -> {prices.index.max().date()} ({len(prices)} rows)"
    )

    results_by_scenario: dict = {}
    all_rows: list = []

    # ---------- [1/3] rule_based ----------
    print("\n[1/3] Running BL with rule-based views...")
    result_rule, rows_rule = run_one_mode(
        prices,
        scenario_name="rule_based",
        view_mode="rule_based",
    )
    results_by_scenario["rule_based"] = result_rule
    all_rows.extend(rows_rule)

    # ---------- [2/3] ml_xgboost ----------
    print("\nLoading ML model: xgboost")
    try:
        xgb_model = bt.load_ml_model("xgboost")
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return

    print("\n[2/3] Running BL with ML xgboost views...")
    result_xgb, rows_xgb = run_one_mode(
        prices,
        scenario_name="ml_xgboost",
        view_mode="ml",
        ml_model=xgb_model,
    )
    results_by_scenario["ml_xgboost"] = result_xgb
    all_rows.extend(rows_xgb)

    # ---------- [3/3] ranking ----------
    print("\n[3/3] Running BL with ranking views...")
    try:
        vn30_list_path = Path(VN30_LIST_PATH)
        if not vn30_list_path.is_absolute():
            vn30_list_path = Path(__file__).resolve().parent / VN30_LIST_PATH
        if not vn30_list_path.exists():
            raise FileNotFoundError(f"VN30 list not found: {vn30_list_path}")

        ranking_universe_prices = bt.load_vn30_universe_prices(
            start_date, end_date, args.phase, bt.WINDOW
        )
        ranking_market_prices = bt.load_market_proxy_prices(
            start_date, end_date, args.phase, bt.WINDOW
        )

        # Align all three indices
        common_idx = (
            prices.index
            .intersection(ranking_universe_prices.index)
            .intersection(ranking_market_prices.index)
        )
        if len(common_idx) < WINDOW + 60:
            raise ValueError(
                f"Insufficient overlap between portfolio assets and VN30 universe "
                f"(common rows = {len(common_idx)})"
            )

        prices_aligned = prices.loc[common_idx]
        ranking_universe_aligned = ranking_universe_prices.loc[common_idx]
        ranking_market_aligned = ranking_market_prices.loc[common_idx]

        print(
            f"  Aligned: {len(common_idx)} rows | "
            f"{len(ranking_universe_aligned.columns)} VN30 stocks"
        )

        result_ranking, rows_ranking = run_one_mode(
            prices_aligned,
            scenario_name="ranking",
            view_mode="ranking",
            ranking_universe_prices=ranking_universe_aligned,
            ranking_market_prices=ranking_market_aligned,
        )
        results_by_scenario["ranking"] = result_ranking
        all_rows.extend(rows_ranking)
    except Exception as e:
        print(f"WARNING: Skipping ranking scenario - {type(e).__name__}: {e}")

    # ---------- RESULT TABLE ----------
    df = pd.DataFrame(all_rows)

    print("\n" + "=" * 80)
    print("RESULT TABLE")
    print("=" * 80)
    print(
        df.to_string(
            index=False,
            formatters={
                "final_nav": lambda x: f"{x:.3f}",
                "ann_return": lambda x: f"{x:.2%}",
                "ann_volatility": lambda x: f"{x:.2%}",
                "sharpe": lambda x: f"{x:.3f}",
                "sortino": lambda x: f"{x:.3f}",
                "max_drawdown": lambda x: f"{x:.2%}",
                "calmar": lambda x: f"{x:.3f}",
            },
        )
    )

    # ---------- BL RANKING (by Sharpe) ----------
    bl_only = (
        df[df["strategy"] == "BL"]
        .sort_values("sharpe", ascending=False)
        .reset_index(drop=True)
    )

    print("\n" + "=" * 80)
    print("BL SCENARIOS RANKED (by Sharpe)")
    print("=" * 80)
    for i, row in bl_only.iterrows():
        print(
            f"{i + 1}. {row['scenario']:<12} | "
            f"NAV={row['final_nav']:.3f} | "
            f"AnnRet={row['ann_return']:.2%} | "
            f"Vol={row['ann_volatility']:.2%} | "
            f"Sharpe={row['sharpe']:.3f} | "
            f"Sortino={row['sortino']:.3f} | "
            f"MDD={row['max_drawdown']:.2%} | "
            f"Calmar={row['calmar']:.3f}"
        )

    # Side-by-side baseline (ml_xgboost) vs new (ranking)
    if "ml_xgboost" in results_by_scenario and "ranking" in results_by_scenario:
        print("\n" + "=" * 80)
        print("BASELINE (ml_xgboost) vs NEW (ranking) - BL strategy")
        print("=" * 80)
        baseline = bl_only[bl_only["scenario"] == "ml_xgboost"].iloc[0]
        new = bl_only[bl_only["scenario"] == "ranking"].iloc[0]
        metric_keys = [
            ("final_nav", "{:.3f}"),
            ("ann_return", "{:.2%}"),
            ("ann_volatility", "{:.2%}"),
            ("sharpe", "{:.3f}"),
            ("sortino", "{:.3f}"),
            ("max_drawdown", "{:.2%}"),
            ("calmar", "{:.3f}"),
        ]
        print(f"  {'Metric':<16} {'ml_xgboost':>14} {'ranking':>14} {'Δ':>14}")
        for key, fmt in metric_keys:
            b_val = baseline[key]
            n_val = new[key]
            delta = n_val - b_val
            print(
                f"  {key:<16} {fmt.format(b_val):>14} "
                f"{fmt.format(n_val):>14} {fmt.format(delta):>14}"
            )

    out_path = Path(args.output_csv)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\nSaved comparison CSV to: {out_path}")

    plot_scenarios(
        results_by_scenario=results_by_scenario,
        output_path=args.plot_path,
        show_plot=not args.no_plot,
    )


if __name__ == "__main__":
    main()
