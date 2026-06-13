"""Compare ranking (relative views) vs ranking_absolute (absolute views).

Usage::

    python -m backtest._compare_ranking --phase train --no-plot
    python -m backtest._compare_ranking --phase test --no-plot
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
    print_head_to_head,
    print_result_table,
    plot_scenarios,
    run_one_mode,
    save_csv,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare ranking (relative) vs ranking_absolute (absolute) view modes."
    )
    parser.add_argument("--phase", choices=list(PHASE_PERIODS.keys()), default=BACKTEST_PHASE,
                        help="Backtest phase (train/test/full)")
    parser.add_argument("--start-date", default=None, help="Override start date YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="Override end date YYYY-MM-DD")
    parser.add_argument("--assets-config", default=None, help="Path to assets config JSON")
    parser.add_argument("--output-csv", default="reports/ranking_compare.csv",
                        help="Path to save result table CSV")
    parser.add_argument("--no-plot", action="store_true", help="Disable chart visualization")
    parser.add_argument("--plot-path", default="reports/ranking_compare.png",
                        help="Path to save NAV comparison chart")
    return parser.parse_args()


def main():
    args = parse_args()
    start_date, end_date = resolve_period(args, PHASE_PERIODS, args.phase)

    assets = load_assets_config(config_path=args.assets_config)

    print("=" * 80)
    print("COMPARE: ranking (relative) vs ranking_absolute (absolute)")
    print("=" * 80)
    print(f"Phase={args.phase} | Period={start_date} -> {end_date}")
    print(f"Assets: {', '.join(assets.keys())}")
    print(f"Config: K={RANKING_K}, retrain={RANKING_RETRAIN_FREQUENCY}, "
          f"reselect={RANKING_RESELECT_FREQUENCY}, spread={RANKING_VIEW_SPREAD}")

    prices = build_price_table(
        start_date=start_date, end_date=end_date, assets=assets,
        phase=args.phase, data_mode=bt.BACKTEST_DATA_MODE, window=bt.WINDOW,
    )

    print("\nLoading VN30 universe...")
    prices, rank_universe, rank_market = load_and_align_ranking_data(prices, args.phase)
    print(f"  Aligned: {len(prices)} rows | {len(rank_universe.columns)} VN30 stocks")

    results_by_scenario: dict = {}
    all_rows: list = []

    # [1/2] ranking
    print("\n[1/2] Running ranking (XGBoostRankingModel -> relative views)...")
    try:
        result_ranking, rows_ranking = run_one_mode(
            prices, "ranking", "ranking",
            ranking_universe_prices=rank_universe, ranking_market_prices=rank_market,
        )
        results_by_scenario["ranking"] = result_ranking
        all_rows.extend(rows_ranking)
    except Exception as e:
        print(f"ERROR in ranking mode: {type(e).__name__}: {e}")

    # [2/2] ranking_absolute
    print("\n[2/2] Running ranking_absolute (XGBoostEnsembleModel -> absolute views)...")
    try:
        result_abs, rows_abs = run_one_mode(
            prices, "ranking_absolute", "ranking_absolute",
            ranking_universe_prices=rank_universe, ranking_market_prices=rank_market,
        )
        results_by_scenario["ranking_absolute"] = result_abs
        all_rows.extend(rows_abs)
    except Exception as e:
        print(f"ERROR in ranking_absolute mode: {type(e).__name__}: {e}")

    if not all_rows:
        print("\nNo results produced. Exiting.")
        return

    # Results
    df = pd.DataFrame(all_rows)
    print_result_table(df)
    print_head_to_head(
        df, "ranking", "ranking_absolute",
        label_a="ranking", label_b="ranking_abs",
        extra_keys=[("total_generated_views", "{:.0f}")],
    )

    save_csv(df, args.output_csv)
    plot_scenarios(
        results_by_scenario,
        scenario_labels=[
            ("ranking", "BL (ranking — relative)"),
            ("ranking_absolute", "BL (ranking_absolute — absolute)"),
        ],
        output_path=args.plot_path,
        suptitle=f"Ranking (Relative) vs Ranking Absolute (Absolute) — {args.phase.upper()} phase",
        figsize_per_panel=8.0,
        show_plot=not args.no_plot,
    )


if __name__ == "__main__":
    main()
