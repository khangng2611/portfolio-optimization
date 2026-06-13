"""
Compare ranking (relative views) vs ranking_absolute (absolute views) side-by-side.

Both modes share the same infrastructure:
  - Combinatorial Stock Selection (K=5, reselect every 60 sessions)
  - Risk Management Layer (regime detection, defensive views, vol dampener)
  - Constrained BL optimizer (defensive floor, equity cap)

The ONLY difference is the view generator:
  - ranking:          XGBoostRankingModel (LambdaMART) → pairwise relative views
  - ranking_absolute: XGBoostEnsembleModel (5 regressors) → per-asset absolute views

Usage:
    python run_compare_ranking.py --phase train --no-plot
    python run_compare_ranking.py --phase test --plot-path reports/ranking_compare_test.png
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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
        description="Compare ranking (relative) vs ranking_absolute (absolute) view modes."
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
        help="Path to assets config JSON (default: from config.py)",
    )
    parser.add_argument(
        "--output-csv",
        default="reports/ranking_compare.csv",
        help="Path to save result table CSV",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Disable chart visualization",
    )
    parser.add_argument(
        "--plot-path",
        default="reports/ranking_compare.png",
        help="Path to save NAV comparison chart",
    )
    return parser.parse_args()


def resolve_period(args):
    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise ValueError("Both --start-date and --end-date required when overriding")
        return args.start_date, args.end_date
    return PHASE_PERIODS[args.phase]


# ====================== METRICS ======================

def annual_return(nav_series: pd.Series) -> float:
    total_days = len(nav_series) - 1
    if total_days <= 0:
        return np.nan
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    return (1 + total_return) ** (TRADING_DAYS_PER_YEAR / total_days) - 1


def annual_volatility(nav_series: pd.Series) -> float:
    ret = nav_series.pct_change().dropna()
    if len(ret) == 0:
        return np.nan
    return ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR)


def sortino_ratio(nav_series: pd.Series) -> float:
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
    ranking_universe_prices: pd.DataFrame,
    ranking_market_prices: pd.Series,
) -> tuple[dict, list[dict]]:
    result = bt.backtest(
        prices,
        view_mode=view_mode,
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

def plot_comparison(results_by_scenario: dict, output_path: str, phase: str, show_plot: bool = True):
    scenario_order = [
        ("ranking", "BL (ranking — relative)"),
        ("ranking_absolute", "BL (ranking_absolute — absolute)"),
    ]
    scenario_order = [s for s in scenario_order if s[0] in results_by_scenario]
    n = len(scenario_order)
    if n == 0:
        print("No scenarios to plot.")
        return

    fig, axes = plt.subplots(1, n, figsize=(8 * n, 6), sharey=True)
    if n == 1:
        axes = [axes]

    colors = {"EW": "#7f8c8d", "MVO": "#3498db", "BL": "#e74c3c"}

    for ax, (scenario_key, bl_label) in zip(axes, scenario_order):
        result = results_by_scenario[scenario_key]
        ax.plot(result["ew_nav"].index, result["ew_nav"].values,
                label="EW", color=colors["EW"], alpha=0.7)
        ax.plot(result["mvo_nav"].index, result["mvo_nav"].values,
                label="MVO", color=colors["MVO"], alpha=0.7)
        ax.plot(result["bl_nav"].index, result["bl_nav"].values,
                label=bl_label, color=colors["BL"], linewidth=2)
        ax.set_title(scenario_key, fontsize=12, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("Date")

    axes[0].set_ylabel("NAV (initial = 1.0)")
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=10)
    fig.suptitle(
        f"Ranking (Relative Views) vs Ranking Absolute (Absolute Views) — {phase.upper()} phase",
        fontsize=13,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.92])

    out_path = Path(output_path)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    print(f"\nSaved comparison plot to: {out_path}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)


# ====================== MAIN ======================

def main():
    args = parse_args()
    start_date, end_date = resolve_period(args)

    assets = load_assets_config(config_path=args.assets_config)

    print("=" * 80)
    print("COMPARE: ranking (relative) vs ranking_absolute (absolute)")
    print("=" * 80)
    print(f"Phase={args.phase} | Period={start_date} -> {end_date}")
    print(f"Assets: {', '.join(assets.keys())}")
    print(
        f"Config: K={RANKING_K}, retrain={RANKING_RETRAIN_FREQUENCY}, "
        f"reselect={RANKING_RESELECT_FREQUENCY}, spread={RANKING_VIEW_SPREAD}"
    )

    # Build portfolio price table
    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=assets,
        phase=args.phase,
        data_mode=bt.BACKTEST_DATA_MODE,
        window=bt.WINDOW,
    )

    # Load VN30 universe (shared by both modes)
    vn30_list_path = Path(VN30_LIST_PATH)
    if not vn30_list_path.is_absolute():
        vn30_list_path = Path(__file__).resolve().parent / VN30_LIST_PATH
    if not vn30_list_path.exists():
        raise FileNotFoundError(f"VN30 list not found: {vn30_list_path}")

    print("\nLoading VN30 universe...")
    ranking_universe_prices = bt.load_vn30_universe_prices(
        start_date, end_date, args.phase, bt.WINDOW
    )
    ranking_market_prices = bt.load_market_proxy_prices(
        start_date, end_date, args.phase, bt.WINDOW
    )

    # Align all indices
    common_idx = (
        prices.index
        .intersection(ranking_universe_prices.index)
        .intersection(ranking_market_prices.index)
    )
    if len(common_idx) < WINDOW + 60:
        raise ValueError(
            f"Insufficient data overlap (common rows = {len(common_idx)})"
        )

    prices = prices.loc[common_idx]
    ranking_universe_prices = ranking_universe_prices.loc[common_idx]
    ranking_market_prices = ranking_market_prices.loc[common_idx]
    print(
        f"  Aligned: {len(common_idx)} rows | "
        f"{len(ranking_universe_prices.columns)} VN30 stocks"
    )

    results_by_scenario: dict = {}
    all_rows: list = []

    # ---------- [1/2] ranking (relative views) ----------
    print("\n[1/2] Running ranking (XGBoostRankingModel → relative views)...")
    try:
        result_ranking, rows_ranking = run_one_mode(
            prices,
            scenario_name="ranking",
            view_mode="ranking",
            ranking_universe_prices=ranking_universe_prices,
            ranking_market_prices=ranking_market_prices,
        )
        results_by_scenario["ranking"] = result_ranking
        all_rows.extend(rows_ranking)
    except Exception as e:
        print(f"ERROR in ranking mode: {type(e).__name__}: {e}")

    # ---------- [2/2] ranking_absolute (absolute views) ----------
    print("\n[2/2] Running ranking_absolute (XGBoostEnsembleModel → absolute views)...")
    try:
        result_abs, rows_abs = run_one_mode(
            prices,
            scenario_name="ranking_absolute",
            view_mode="ranking_absolute",
            ranking_universe_prices=ranking_universe_prices,
            ranking_market_prices=ranking_market_prices,
        )
        results_by_scenario["ranking_absolute"] = result_abs
        all_rows.extend(rows_abs)
    except Exception as e:
        print(f"ERROR in ranking_absolute mode: {type(e).__name__}: {e}")

    if not all_rows:
        print("\nNo results produced. Exiting.")
        return

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

    # ---------- BL HEAD-TO-HEAD ----------
    bl_only = df[df["strategy"] == "BL"].copy()
    if len(bl_only) == 2:
        print("\n" + "=" * 80)
        print("HEAD-TO-HEAD: BL (ranking) vs BL (ranking_absolute)")
        print("=" * 80)
        ranking_row = bl_only[bl_only["scenario"] == "ranking"].iloc[0]
        abs_row = bl_only[bl_only["scenario"] == "ranking_absolute"].iloc[0]

        metric_keys = [
            ("final_nav", "{:.3f}"),
            ("ann_return", "{:.2%}"),
            ("ann_volatility", "{:.2%}"),
            ("sharpe", "{:.3f}"),
            ("sortino", "{:.3f}"),
            ("max_drawdown", "{:.2%}"),
            ("calmar", "{:.3f}"),
            ("total_generated_views", "{:.0f}"),
        ]
        print(f"  {'Metric':<22} {'ranking':>14} {'ranking_abs':>14} {'Delta':>14}")
        print(f"  {'-'*22} {'-'*14} {'-'*14} {'-'*14}")
        for key, fmt in metric_keys:
            r_val = ranking_row[key]
            a_val = abs_row[key]
            delta = r_val - a_val
            print(
                f"  {key:<22} {fmt.format(r_val):>14} "
                f"{fmt.format(a_val):>14} {fmt.format(delta):>14}"
            )

        # Determine winner
        winner = "ranking" if ranking_row["sharpe"] >= abs_row["sharpe"] else "ranking_absolute"
        print(f"\n  >>> Winner (by Sharpe): {winner}")

    # ---------- SAVE CSV ----------
    out_path = Path(args.output_csv)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\nSaved CSV to: {out_path}")

    # ---------- PLOT ----------
    plot_comparison(
        results_by_scenario=results_by_scenario,
        output_path=args.plot_path,
        phase=args.phase,
        show_plot=not args.no_plot,
    )


if __name__ == "__main__":
    main()
