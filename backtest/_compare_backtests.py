"""Compare backtests: rule_based, ML xgboost, and ranking views in one command.

Usage::

    python -m backtest._compare_backtests --phase train --no-plot
    python -m backtest._compare_backtests --phase test --no-plot
"""

import argparse
from pathlib import Path

import pandas as pd

import backtest as bt
from config import (
    BACKTEST_PHASE,
    PHASE_PERIODS,
    RANKING_K,
    RANKING_RESELECT_FREQUENCY,
    RANKING_RETRAIN_FREQUENCY,
    RANKING_VIEW_SPREAD,
)
from utils.data_loader import build_price_table, load_assets_config, resolve_period

from backtest._compare import (
    load_and_align_ranking_data,
    print_bl_ranked,
    print_head_to_head,
    print_result_table,
    plot_scenarios,
    run_one_mode,
    save_csv,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run portfolio backtests for rule-based, ML XGBoost, and ranking views in one command."
    )
    parser.add_argument("--phase", choices=list(PHASE_PERIODS.keys()), default=BACKTEST_PHASE,
                        help="Backtest phase (train/test/full)")
    parser.add_argument("--start-date", default=None, help="Override start date YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="Override end date YYYY-MM-DD")
    parser.add_argument("--assets-config", default=None, help="Path to assets config JSON")
    parser.add_argument("--assets", default=None, help="Comma-separated assets")
    parser.add_argument("--output-csv", default="reports/backtest_compare_views.csv",
                        help="Path to save result table CSV")
    parser.add_argument("--no-plot", action="store_true", help="Disable chart visualization")
    parser.add_argument("--plot-path", default="reports/backtest_compare_views.png",
                        help="Path to save NAV comparison chart")
    return parser.parse_args()


def main():
    args = parse_args()
    start_date, end_date = resolve_period(args, PHASE_PERIODS, args.phase)

    selected_assets = None
    if args.assets:
        selected_assets = [a.strip() for a in args.assets.split(",") if a.strip()]
    assets = load_assets_config(config_path=args.assets_config, selected_assets=selected_assets)

    print("=" * 80)
    print("COMPARE BACKTESTS: EW, MVO, BL(rule_based), BL(ml-xgb), BL(ranking)")
    print("=" * 80)
    print(f"Phase={args.phase} | Period={start_date} -> {end_date}")
    print(f"Assets: {', '.join(assets.keys())}")
    print(f"Ranking config: K={RANKING_K}, retrain_freq={RANKING_RETRAIN_FREQUENCY}, "
          f"reselect_freq={RANKING_RESELECT_FREQUENCY}, view_spread={RANKING_VIEW_SPREAD}")

    prices = build_price_table(
        start_date=start_date, end_date=end_date, assets=assets,
        phase=args.phase, data_mode=bt.BACKTEST_DATA_MODE, window=bt.WINDOW,
    )
    print(f"Aligned price window: {prices.index.min().date()} -> {prices.index.max().date()} ({len(prices)} rows)")

    results_by_scenario: dict = {}
    all_rows: list = []

    # [1/3] rule_based
    print("\n[1/3] Running BL with rule-based views...")
    result_rule, rows_rule = run_one_mode(prices, "rule_based", "rule_based")
    results_by_scenario["rule_based"] = result_rule
    all_rows.extend(rows_rule)

    # [2/3] ml_xgboost
    print("\nLoading ML model: xgboost")
    try:
        xgb_model = bt.load_ml_model("xgboost", args.assets_config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return

    print("\n[2/3] Running BL with ML xgboost views...")
    result_xgb, rows_xgb = run_one_mode(prices, "ml_xgboost", "ml", ml_model=xgb_model)
    results_by_scenario["ml_xgboost"] = result_xgb
    all_rows.extend(rows_xgb)

    # [3/3] ranking
    print("\n[3/3] Running BL with ranking views...")
    try:
        prices_aligned, rank_universe, rank_market = load_and_align_ranking_data(prices, args.phase, args.assets_config)
        print(f"  Aligned: {len(prices_aligned)} rows | {len(rank_universe.columns)} VN30 stocks")
        result_ranking, rows_ranking = run_one_mode(
            prices_aligned, "ranking", "ranking",
            ranking_universe_prices=rank_universe, ranking_market_prices=rank_market,
        )
        results_by_scenario["ranking"] = result_ranking
        all_rows.extend(rows_ranking)
    except Exception as e:
        print(f"WARNING: Skipping ranking scenario - {type(e).__name__}: {e}")

    # Results
    df = pd.DataFrame(all_rows)
    print_result_table(df)
    bl_only = print_bl_ranked(df)

    if "ml_xgboost" in results_by_scenario and "ranking" in results_by_scenario:
        print("\n" + "=" * 80)
        print("BASELINE (ml_xgboost) vs NEW (ranking) - BL strategy")
        print("=" * 80)
        print_head_to_head(df, "ml_xgboost", "ranking")

    save_csv(df, args.output_csv)
    plot_scenarios(
        results_by_scenario,
        scenario_labels=[
            ("rule_based", "BL (rule_based)"),
            ("ml_xgboost", "BL (ml_xgboost)"),
            ("ranking", "BL (ranking)"),
        ],
        output_path=args.plot_path,
        suptitle="Backtest NAV Comparison Across View Generators",
        show_plot=not args.no_plot,
    )


if __name__ == "__main__":
    main()
