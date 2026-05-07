"""
Train Traditional ML Models Script
==================================

Train XGBoost models once, then reuse in backtests.

Usage:
    python gen_view/xgboost/model_train.py --method xgboost --validate
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import PHASE_PERIODS
from utils.data_loader import build_price_table, load_assets_config
from gen_view.xgboost.xgboost_core import XGBoostCoreModel, XGBoostEnsembleModel
from gen_view.view_generators import generate_ml_views


from gen_view.xgboost.config import (
    CACHE_DIR,
    DEFAULT_FEATURE_WINDOW,
    DEFAULT_PREDICTION_HORIZON,
    DEFAULT_XGB_PARAMS,
    ENSEMBLE_SIZE,
    ENSEMBLE_BASE_SEED,
)

CACHE_DIR.mkdir(exist_ok=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Train ML models")
    parser.add_argument(
        "--method",
        type=str,
        default="xgboost",
        choices=["all", "xgboost", "xgb"],
        help="Which method to train (all maps to xgboost for backward compatibility)",
    )
    parser.add_argument(
        "--assets-config",
        type=str,
        default=None,
        help="Path to assets config JSON (default: assets.json)",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated assets, e.g. E1VFVN30,GOLD,DCDS,MBBOND",
    )
    parser.add_argument(
        "--train-phase",
        choices=["train", "full"],
        default="train",
        help="Data phase used for training",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate models after training",
    )
    parser.add_argument(
        "--ensemble",
        action="store_true",
        help="Train ensemble model (5 models per asset with different seeds)",
    )
    return parser.parse_args()


def load_training_data(args) -> pd.DataFrame:
    start_date, end_date = PHASE_PERIODS[args.train_phase]

    selected_assets = None
    if args.assets:
        selected_assets = [item.strip() for item in args.assets.split(",") if item.strip()]

    assets = load_assets_config(
        config_path=args.assets_config,
        selected_assets=selected_assets,
    )

    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=assets,
        phase=args.train_phase,
        data_mode="split",
        window=20,
    )

    print("Loading training data from assets.json...")
    for asset in prices.columns:
        series = prices[asset].dropna()
        print(
            f"  - {asset}: {len(series)} days ({series.index[0].date()} to {series.index[-1].date()})"
        )

    print(f"\nTotal training data shape: {prices.shape}")
    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")
    return prices


def train_xgboost(prices: pd.DataFrame, verbose: bool = True):
    print("\n" + "=" * 70)
    print("TRAINING XGBOOST")
    print("=" * 70)

    try:
        model = XGBoostCoreModel(
            feature_window=DEFAULT_FEATURE_WINDOW,
            prediction_horizon=DEFAULT_PREDICTION_HORIZON,
            model_params=DEFAULT_XGB_PARAMS.copy(),
        )
        model.train(prices, verbose=verbose)

        model_path = CACHE_DIR / "xgboost_models.pkl"
        model.save(model_path)

        print(f"\nSaved XGBoost model to: {model_path}")
        return model
    except ImportError:
        print("\nERROR: XGBoost is not installed.")
        print("Install with: pip install xgboost")
        return None


def train_xgboost_ensemble(prices: pd.DataFrame, verbose: bool = True):
    print("\n" + "=" * 70)
    print(f"TRAINING XGBOOST ENSEMBLE ({ENSEMBLE_SIZE} models per asset)")
    print("=" * 70)

    try:
        model = XGBoostEnsembleModel(
            feature_window=DEFAULT_FEATURE_WINDOW,
            prediction_horizon=DEFAULT_PREDICTION_HORIZON,
            model_params=DEFAULT_XGB_PARAMS.copy(),
            n_ensemble=ENSEMBLE_SIZE,
            base_seed=ENSEMBLE_BASE_SEED,
        )
        model.train(prices, verbose=verbose)

        model_path = CACHE_DIR / "xgboost_ensemble.pkl"
        model.save(model_path)

        print(f"\nSaved ensemble model to: {model_path}")
        return model
    except ImportError:
        print("\nERROR: XGBoost or scikit-learn is not installed.")
        print("Install with: pip install xgboost scikit-learn")
        return None


def validate_model(generator, prices: pd.DataFrame, method_name: str):
    print(f"\n--- Validating {method_name} ---")

    predictions = generator.predict(prices)
    if not predictions:
        print(f"  WARNING: No predictions for {method_name}")
        return

    views = generate_ml_views(predictions, generator.prediction_horizon)
    if not views:
        print(f"  WARNING: No views generated for {method_name}")
        return

    print(f"  Generated {len(views)} views:")
    for view in views:
        print(
            f"    {view['name']}: {view['view_return_annual']:.2%} (conf: {view['confidence']:.2f})"
        )


def main():
    args = parse_args()

    print("=" * 70)
    print("TRADITIONAL ML MODEL TRAINING FOR PORTFOLIO OPTIMIZATION")
    print("=" * 70)

    try:
        prices = load_training_data(args)
    except Exception as e:
        print(f"\nERROR loading data: {e}")
        return

    if prices.empty:
        print("\nERROR: No training data loaded. Check assets.json and datasets.")
        return

    method = args.method.lower()
    trained_generators = []

    if method in ["all", "xgb", "xgboost"]:
        xgb_gen = train_xgboost(prices, verbose=True)
        if xgb_gen:
            trained_generators.append(("XGBoost", xgb_gen))

        # Also train ensemble if --ensemble flag is set
        if args.ensemble:
            ens_gen = train_xgboost_ensemble(prices, verbose=True)
            if ens_gen:
                trained_generators.append(("XGBoost Ensemble", ens_gen))

    if args.validate and trained_generators:
        print("\n" + "=" * 70)
        print("VALIDATION")
        print("=" * 70)
        val_prices = prices.iloc[-60:]
        for name, generator in trained_generators:
            validate_model(generator, val_prices, name)

    print("\n" + "=" * 70)
    print("TRAINING SUMMARY")
    print("=" * 70)
    print(f"\n Training complete. Trained {len(trained_generators)} model(s)")
    print(f"Models saved to: {CACHE_DIR}")
    print("\nNext steps:")
    print("  1. Run backtest with pretrained model:")
    print("     python backtest.py --phase test --view-mode ml --ml-training-mode pretrained")
    print("  2. Run backtest with walk-forward (no pre-train needed):")
    print("     python backtest.py --phase train --view-mode ml --ml-training-mode walk_forward")
    print("  3. Compare all modes:")
    print("     python run_compare_backtests.py --phase test")


if __name__ == "__main__":
    main()
