import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

import backtest as bt
from utils.data_loader import PHASE_PERIODS, build_price_table, load_assets_config


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run portfolio backtests for rule-based views and ML XGBoost views in one command."
        )
    )
    parser.add_argument(
        "--phase",
        choices=list(PHASE_PERIODS.keys()),
        default="test",
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


def metric_summary(nav_series: pd.Series) -> tuple[float, float, float]:
    return (
        float(nav_series.iloc[-1]),
        float(bt.sharpe_ratio(nav_series)),
        float(bt.max_drawdown(nav_series)),
    )


def run_one_mode(
    prices: pd.DataFrame,
    scenario_name: str,
    view_mode: str,
    ml_predictor=None,
) -> tuple[dict, list[dict]]:
    result = bt.backtest(
        prices,
        view_mode=view_mode,
        ml_predictor=ml_predictor,
    )

    ew_final, ew_sharpe, ew_mdd = metric_summary(result["ew_nav"])
    mvo_final, mvo_sharpe, mvo_mdd = metric_summary(result["mvo_nav"])
    bl_final, bl_sharpe, bl_mdd = metric_summary(result["bl_nav"])

    views_history = result.get("views_history", [])
    total_views = sum(len(v.get("view_names", [])) for v in views_history)
    rebalance_count = len(views_history)

    rows = [
        {
            "scenario": scenario_name,
            "strategy": "EW",
            "final_nav": ew_final,
            "sharpe": ew_sharpe,
            "max_drawdown": ew_mdd,
            "rebalance_count": rebalance_count,
            "total_generated_views": total_views,
        },
        {
            "scenario": scenario_name,
            "strategy": "MVO",
            "final_nav": mvo_final,
            "sharpe": mvo_sharpe,
            "max_drawdown": mvo_mdd,
            "rebalance_count": rebalance_count,
            "total_generated_views": total_views,
        },
        {
            "scenario": scenario_name,
            "strategy": "BL",
            "final_nav": bl_final,
            "sharpe": bl_sharpe,
            "max_drawdown": bl_mdd,
            "rebalance_count": rebalance_count,
            "total_generated_views": total_views,
        },
    ]
    return result, rows


def plot_scenarios(results_by_scenario: dict, output_path: str, show_plot: bool = True):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

    scenario_order = [
        ("rule_based", "BL (rule_based)"),
        ("ml_xgboost", "BL (ml_xgboost)"),
    ]

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
    print("COMPARE BACKTESTS: EW, MVO, BL(rule_based), BL(ml-xgb)")
    print("=" * 80)
    print(f"Phase={args.phase} | Period={start_date} -> {end_date}")
    print(f"Assets: {', '.join(assets.keys())}")

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

    results_by_scenario = {}

    print("\n[1/2] Running BL with rule-based views...")
    result_rule, rows_rule = run_one_mode(
        prices,
        scenario_name="rule_based",
        view_mode="rule_based",
    )
    results_by_scenario["rule_based"] = result_rule

    print("\nLoading ML predictor: xgboost")
    try:
        xgb_predictor = bt.load_ml_view_generator("xgboost")
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return

    print("\n[2/2] Running BL with ML xgboost views...")
    result_xgb, rows_xgb = run_one_mode(
        prices,
        scenario_name="ml_xgboost",
        view_mode="ml",
        ml_predictor=xgb_predictor,
    )
    results_by_scenario["ml_xgboost"] = result_xgb

    df = pd.DataFrame(rows_rule + rows_xgb)

    print("\n" + "=" * 80)
    print("RESULT TABLE")
    print("=" * 80)
    print(
        df.to_string(
            index=False,
            formatters={
                "final_nav": lambda x: f"{x:.3f}",
                "sharpe": lambda x: f"{x:.3f}",
                "max_drawdown": lambda x: f"{x:.2%}",
            },
        )
    )

    bl_only = (
        df[df["strategy"] == "BL"]
        .sort_values("final_nav", ascending=False)
        .reset_index(drop=True)
    )

    print("\n" + "=" * 80)
    print("BL RANKING (by final NAV)")
    print("=" * 80)
    for i, row in bl_only.iterrows():
        print(
            f"{i + 1}. {row['scenario']}: NAV={row['final_nav']:.3f}, "
            f"Sharpe={row['sharpe']:.3f}, MDD={row['max_drawdown']:.2%}"
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
