"""
Train ML/LSTM Models Script
============================

Script đơn giản để train tất cả ML models cho portfolio optimization.
Run script này TRƯỚC KHI chạy backtest với VIEW_MODE = "ml_*"

Usage:
    python train_ml_models.py --method all
    python train_ml_models.py --method rf
    python train_ml_models.py --method xgboost
    python train_ml_models.py --method lstm

Author: Nguyen Khang
"""

import argparse
from pathlib import Path

import pandas as pd

from llm_view_generators import (
    TraditionalMLViewGenerator,
    LSTMViewGenerator,
)

# ====================== CONFIG ======================
ROOT_DIR = Path(__file__).resolve().parents[0]
DATASETS_DIR = ROOT_DIR / "datasets"
CACHE_DIR = ROOT_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

TRAIN_START = "2020-01-01"
TRAIN_END = "2023-10-01"

ASSETS = {
    "E1VFVN30": {
        "train_path": DATASETS_DIR / "stocks" / "train" / "E1VFVN30_train.csv",
        "date_col": "date",
        "price_col": "close",
    },
    "GOLD": {
        "train_path": DATASETS_DIR / "gold" / "gold_train.csv",
        "date_col": "date",
        "price_col": "sjc_sell",
    },
    "DCDS": {
        "train_path": DATASETS_DIR / "funds" / "train" / "DCDS_train.csv",
        "date_col": "date",
        "price_col": "price",
    },
    "MBBOND": {
        "train_path": DATASETS_DIR / "funds" / "train" / "MBBOND_train.csv",
        "date_col": "date",
        "price_col": "price",
    },
}


# ====================== LOAD DATA ======================


def load_training_data() -> pd.DataFrame:
    """
    Load training data for all assets.

    Returns
    -------
    pd.DataFrame
        Price data with assets as columns
    """
    print("Loading training data...")

    all_prices = {}

    for asset_name, config in ASSETS.items():
        train_path = config["train_path"]

        if not train_path.exists():
            print(f"  WARNING: {asset_name} train file not found: {train_path}")
            continue

        df = pd.read_csv(train_path)

        # Parse date column
        df[config["date_col"]] = pd.to_datetime(df[config["date_col"]])
        df = df.set_index(config["date_col"])

        # Extract price column
        prices = df[config["price_col"]]

        # Filter date range
        prices = prices.loc[TRAIN_START:TRAIN_END]

        all_prices[asset_name] = prices

        print(
            f"  ✓ {asset_name}: {len(prices)} days ({prices.index[0].date()} to {prices.index[-1].date()})"
        )

    # Combine into single DataFrame
    price_df = pd.DataFrame(all_prices)

    print(f"\nTotal training data shape: {price_df.shape}")
    print(f"Date range: {price_df.index[0].date()} to {price_df.index[-1].date()}")

    return price_df


# ====================== TRAINING FUNCTIONS ======================


def train_random_forest(prices: pd.DataFrame, verbose: bool = True):
    """Train Random Forest model."""
    print("\n" + "=" * 70)
    print("TRAINING RANDOM FOREST")
    print("=" * 70)

    generator = TraditionalMLViewGenerator(
        model_type="random_forest",
        feature_window=20,
        prediction_horizon=5,
        model_params={
            "n_estimators": 100,
            "max_depth": 10,
            "min_samples_split": 20,
            "min_samples_leaf": 10,
            "random_state": 42,
        },
    )

    generator.train(prices, verbose=verbose)

    # Save model
    model_path = CACHE_DIR / "random_forest_models.pkl"
    generator.save(model_path)

    print(f"\n✓ Random Forest training complete!")
    print(f"  Saved to: {model_path}")

    return generator


def train_xgboost(prices: pd.DataFrame, verbose: bool = True):
    """Train XGBoost model."""
    print("\n" + "=" * 70)
    print("TRAINING XGBOOST")
    print("=" * 70)

    try:
        generator = TraditionalMLViewGenerator(
            model_type="xgboost",
            feature_window=20,
            prediction_horizon=5,
            model_params={
                "n_estimators": 100,
                "max_depth": 6,
                "learning_rate": 0.1,
                "random_state": 42,
            },
        )

        generator.train(prices, verbose=verbose)

        # Save model
        model_path = CACHE_DIR / "xgboost_models.pkl"
        generator.save(model_path)

        print(f"\n✓ XGBoost training complete!")
        print(f"  Saved to: {model_path}")

        return generator

    except ImportError:
        print("\nERROR: XGBoost not installed.")
        print("Install with: pip install xgboost")
        return None


def train_lstm(prices: pd.DataFrame, verbose: bool = True):
    """Train LSTM model."""
    print("\n" + "=" * 70)
    print("TRAINING LSTM")
    print("=" * 70)

    generator = LSTMViewGenerator(
        sequence_length=60,
        prediction_horizon=5,
        hidden_size=64,
        num_layers=2,
        dropout=0.2,
        learning_rate=0.001,
        epochs=50,
        batch_size=32,
        device="cpu",  # Change to "cuda" if GPU available
    )

    if not generator.torch_available:
        print("\nERROR: PyTorch not installed.")
        print("Install with: pip install torch")
        return None

    generator.train(prices, verbose=verbose)

    # Save model
    model_path = CACHE_DIR / "lstm_models.pt"
    generator.save(model_path)

    print(f"\n✓ LSTM training complete!")
    print(f"  Saved to: {model_path}")

    return generator


# ====================== VALIDATION ======================


def validate_model(generator, prices: pd.DataFrame, method_name: str):
    """
    Validate trained model by generating predictions.

    Parameters
    ----------
    generator : object
        Trained model generator
    prices : pd.DataFrame
        Validation data
    method_name : str
        Name of method for display
    """
    print(f"\n--- Validating {method_name} ---")

    # Generate views
    views = generator.generate_views(prices)

    if not views:
        print(f"  WARNING: No views generated for {method_name}")
        return

    print(f"  Generated {len(views)} views:")
    for view in views:
        print(
            f"    {view['name']}: {view['view_return_annual']:.2%} (conf: {view['confidence']:.2f})"
        )

    # Test predictions
    predictions = generator.predict(prices)

    if predictions:
        print(f"\n  Predictions summary:")
        for asset, (pred_return, confidence) in predictions.items():
            print(f"    {asset}: return={pred_return:.2%}, confidence={confidence:.2f}")


# ====================== MAIN ======================


def main():
    parser = argparse.ArgumentParser(description="Train ML/LSTM models")
    parser.add_argument(
        "--method",
        type=str,
        default="all",
        choices=["all", "rf", "random_forest", "xgboost", "xgb", "lstm"],
        help="Which method to train (default: all)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate models after training",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("ML/LSTM MODEL TRAINING FOR PORTFOLIO OPTIMIZATION")
    print("=" * 70)

    # Load data
    try:
        prices = load_training_data()
    except Exception as e:
        print(f"\nERROR loading data: {e}")
        print("\nMake sure you have run the data crawlers first:")
        print("  python crawl/crawl_stocks.py")
        print("  python crawl/crawl_gold.py")
        print("  python crawl/crawl_funds.py")
        return

    if prices.empty:
        print("\nERROR: No training data loaded. Check your data files.")
        return

    # Train models based on method
    method = args.method.lower()
    trained_generators = []

    if method in ["all", "rf", "random_forest"]:
        rf_gen = train_random_forest(prices, verbose=True)
        if rf_gen:
            trained_generators.append(("Random Forest", rf_gen))

    if method in ["all", "xgb", "xgboost"]:
        xgb_gen = train_xgboost(prices, verbose=True)
        if xgb_gen:
            trained_generators.append(("XGBoost", xgb_gen))

    if method in ["all", "lstm"]:
        lstm_gen = train_lstm(prices, verbose=True)
        if lstm_gen:
            trained_generators.append(("LSTM", lstm_gen))

    # Validation
    if args.validate and trained_generators:
        print("\n" + "=" * 70)
        print("VALIDATION")
        print("=" * 70)

        # Use last 50 days for validation
        val_prices = prices.iloc[-50:]

        for name, generator in trained_generators:
            validate_model(generator, val_prices, name)

    # Summary
    print("\n" + "=" * 70)
    print("TRAINING SUMMARY")
    print("=" * 70)
    print(f"\n✓ Training complete!")
    print(f"  Trained {len(trained_generators)} model(s)")
    print(f"  Models saved to: {CACHE_DIR}")
    print("\nNext steps:")
    print("  1. Run backtest with: python backtest.py --phase test")
    print("  2. In backtest.py, set VIEW_MODE to one of:")
    print("     - 'ml_only' (use Random Forest/XGBoost)")
    print("     - 'lstm_only' (use LSTM)")
    print("     - 'ml_ensemble' (combine all methods)")
    print("\nExample:")
    print("  # Edit backtest.py")
    print("  VIEW_MODE = 'ml_only'")
    print("  ")
    print("  # Then run")
    print("  python backtest.py --phase test")


if __name__ == "__main__":
    main()
