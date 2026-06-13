"""Backtest CLI entry point.

Run with::

    python -m backtest._main --phase train --view-mode ranking_absolute --no-plot

Or equivalently via the package::

    python -c "from backtest._main import main; main()"
"""

import pandas as pd

from config import (
    BACKTEST_DATA_MODE,
    COMBINED_VIEW_WEIGHTS,
    RETRAIN_FREQUENCY,
    PHASE_PERIODS,
    RANKING_K,
    RANKING_MAX_EQUITY_EXPOSURE,
    RANKING_MIN_DEFENSIVE_WEIGHT,
    RANKING_RESELECT_FREQUENCY,
    RANKING_RETRAIN_FREQUENCY,
    SPLIT_DATE,
    TRAIN_START_DATE,
    TRADING_DAYS_PER_YEAR,
    WINDOW,
)
from utils.data_loader import (
    build_price_table,
    load_assets_config,
    resolve_period,
    summarize_asset_returns,
)
from utils.view_logger import log_view_history

from backtest._cli import parse_args
from backtest._data_helpers import (
    load_market_proxy_prices,
    load_ml_model,
    load_vn30_universe_prices,
)
from backtest._loop import backtest
from backtest._metrics import max_drawdown, sharpe_ratio


def main():
    args = parse_args()
    phase = args.phase
    view_mode = args.view_mode
    ml_training_mode = args.ml_training_mode
    start_date, end_date = resolve_period(args, PHASE_PERIODS, phase)

    # --- Walk-forward warm-up: load train history for model warm-up ---
    needs_warmup = (
        phase == "test"
        and (
            (view_mode in ("ml", "combined") and ml_training_mode == "walk_forward")
            or view_mode in ("ranking", "ranking_absolute")
        )
    )
    load_start_date = start_date
    load_phase = phase
    if needs_warmup:
        load_start_date = TRAIN_START_DATE
        load_phase = "full"

    selected_assets = None
    if args.assets:
        selected_assets = [item.strip() for item in args.assets.split(",") if item.strip()]

    assets = load_assets_config(
        config_path=args.assets_config,
        selected_assets=selected_assets,
    )

    print(f"Phase={phase} | Data mode={BACKTEST_DATA_MODE} | Period={start_date} -> {end_date}")
    if needs_warmup:
        print(f"  [WARM-UP] Loading data from {TRAIN_START_DATE} for model training history")
    print(f"View mode={view_mode}")
    if view_mode in ("ml", "combined"):
        print(f"ML training mode={ml_training_mode}")
    print(f"Assets: {', '.join(assets.keys())}")

    prices = build_price_table(
        start_date=load_start_date,
        end_date=end_date,
        assets=assets,
        phase=load_phase,
        data_mode=BACKTEST_DATA_MODE,
        window=WINDOW,
    )
    asset_summary = summarize_asset_returns(prices, TRADING_DAYS_PER_YEAR)

    eval_label = f"{start_date} -> {end_date}"
    if needs_warmup:
        eval_label = f"{TRAIN_START_DATE} -> {end_date} (eval from {start_date})"
    print(f"Khoang du lieu dung backtest: {prices.index.min().date()} -> {prices.index.max().date()} ({len(prices)} phien)")

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
        print("  - XGBoost Ranker -> Relative Views -> BL")
        print(f"  - Retrain every {RANKING_RETRAIN_FREQUENCY} days, reselect every {RANKING_RESELECT_FREQUENCY} days")
    elif view_mode == "ranking_absolute":
        print(f"  - K={RANKING_K} representative stocks from VN30 (combinatorial selection)")
        print("  - XGBoost Regression -> Absolute Views -> BL")
        print(f"  - Retrain every {RETRAIN_FREQUENCY} days, reselect every {RANKING_RESELECT_FREQUENCY} days")
        print(f"  - Risk management: defensive floor {RANKING_MIN_DEFENSIVE_WEIGHT:.0%}, equity cap {RANKING_MAX_EQUITY_EXPOSURE:.0%}")

    ml_model = None
    ml_training_mode = args.ml_training_mode
    if view_mode in ("ml", "combined"):
        print("\n" + "=" * 70)
        if ml_training_mode == "walk_forward":
            print(f"ML VIEW GENERATOR: WALK-FORWARD ({args.ml_model_type} ensemble)")
            print(f"  - Retrain every {RETRAIN_FREQUENCY} trading days (expanding window)")
            print("  - Confidence: ensemble disagreement-based")
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
        ranking_universe_prices = load_vn30_universe_prices(load_start_date, end_date, load_phase, WINDOW)
        ranking_market_prices = load_market_proxy_prices(load_start_date, end_date, load_phase, WINDOW)
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

    # --- Compute warm-up end index ---
    warmup_end_index = 0
    if needs_warmup:
        split_ts = pd.Timestamp(SPLIT_DATE)
        mask = prices.index >= split_ts
        if mask.any():
            # Index in the returns series (returns = prices.pct_change().dropna(),
            # so returns.index = prices.index[1:])
            warmup_end_index = int(mask.argmax()) - 1  # -1 to align with returns
            warmup_end_index = max(0, warmup_end_index)
            print(f"\n  Warm-up: {len(prices.iloc[:warmup_end_index])} sessions for training, "
                  f"{len(prices.iloc[warmup_end_index:])} sessions for evaluation")
        else:
            needs_warmup = False  # all data is before split, no warm-up needed

    result = backtest(
        prices,
        view_mode=view_mode,
        ml_model=ml_model,
        ml_training_mode=ml_training_mode,
        retrain_frequency=RETRAIN_FREQUENCY,
        ranking_universe_prices=ranking_universe_prices,
        ranking_market_prices=ranking_market_prices,
        warmup_end_index=warmup_end_index,
    )
    ew_nav = result["ew_nav"]
    mvo_nav = result["mvo_nav"]
    bl_nav = result["bl_nav"]

    print("\n" + "=" * 70)
    print(f"KET QUA BACKTEST ({eval_label}, theo du lieu kha dung)")
    print(f"EW   | NAV cuoi: {ew_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(ew_nav):6.2f} | MDD: {max_drawdown(ew_nav):7.2%}")
    print(f"MVO  | NAV cuoi: {mvo_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(mvo_nav):6.2f} | MDD: {max_drawdown(mvo_nav):7.2%}")
    print(f"BL   | NAV cuoi: {bl_nav.iloc[-1]:8.2f} | Sharpe: {sharpe_ratio(bl_nav):6.2f} | MDD: {max_drawdown(bl_nav):7.2%}")

    # Log view history + save NAV plot (plot saved by view_logger, no interactive duplicate)
    log_path, plot_path = log_view_history(
        result["views_history"],
        view_mode=view_mode,
        phase=phase,
        assets=result["assets"],
        backtest_metrics={
            "EW":  {"final_nav": float(ew_nav.iloc[-1]), "sharpe": float(sharpe_ratio(ew_nav)), "mdd": float(max_drawdown(ew_nav))},
            "MVO": {"final_nav": float(mvo_nav.iloc[-1]), "sharpe": float(sharpe_ratio(mvo_nav)), "mdd": float(max_drawdown(mvo_nav))},
            "BL":  {"final_nav": float(bl_nav.iloc[-1]), "sharpe": float(sharpe_ratio(bl_nav)), "mdd": float(max_drawdown(bl_nav))},
        },
        ml_training_mode=ml_training_mode if view_mode in ("ml", "combined") else None,
        weights_history=result.get("rebalance_weights_history"),
        ew_nav=ew_nav if not args.no_plot else None,
        mvo_nav=mvo_nav if not args.no_plot else None,
        bl_nav=bl_nav if not args.no_plot else None,
    )

    if plot_path is not None:
        print(f"\nPlot saved: {plot_path}")


if __name__ == "__main__":
    main()
