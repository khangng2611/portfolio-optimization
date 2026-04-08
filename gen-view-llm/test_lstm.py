"""
Test LSTM View Generator
=========================

Tests the LSTM-based view generation method (Option 2).
LSTM can capture temporal patterns and long-term dependencies in price data.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

# ====================== IMPORT LSTM GENERATOR ======================

print("=" * 70)
print("TESTING LSTM VIEW GENERATOR")
print("=" * 70)

print("\nImporting LSTMViewGenerator...")

try:
    from llm_view_generators import LSTMViewGenerator

    print("✓ LSTMViewGenerator imported successfully")
except ImportError as e:
    print(f"❌ Failed to import: {e}")
    print("\nMake sure PyTorch is installed:")
    print("  pip install torch")
    exit(1)

# ====================== LOAD TEST DATA ======================

ROOT_DIR = Path(__file__).resolve().parents[0]
DATASETS_DIR = ROOT_DIR / "datasets"
CACHE_DIR = ROOT_DIR / ".cache"

print("\nLoading test data...")

assets_data = {}

# E1VFVN30
e1_path = DATASETS_DIR / "stocks" / "test" / "E1VFVN30_test.csv"
if e1_path.exists():
    df = pd.read_csv(e1_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data["E1VFVN30"] = df["close"]
    print(f"  ✓ E1VFVN30: {len(df)} days")

# GOLD
gold_path = DATASETS_DIR / "gold" / "gold_test.csv"
if gold_path.exists():
    df = pd.read_csv(gold_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data["GOLD"] = df["sjc_sell"]
    print(f"  ✓ GOLD: {len(df)} days")

# DCDS
dcds_path = DATASETS_DIR / "funds" / "test" / "DCDS_test.csv"
if dcds_path.exists():
    df = pd.read_csv(dcds_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data["DCDS"] = df["price"]
    print(f"  ✓ DCDS: {len(df)} days")

# MBBOND
mbbond_path = DATASETS_DIR / "funds" / "test" / "MBBOND_test.csv"
if mbbond_path.exists():
    df = pd.read_csv(mbbond_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data["MBBOND"] = df["price"]
    print(f"  ✓ MBBOND: {len(df)} days")

# Combine
prices = pd.DataFrame(assets_data)

print(f"\nTest data shape: {prices.shape}")
print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")

# ====================== CHECK IF LSTM MODELS EXIST ======================

# Note: LSTMViewGenerator doesn't support save/load yet
# Models will be trained fresh each time
print("\n⚠ Note: LSTM models don't support persistence yet")
print("  Models will be trained fresh (takes a few minutes)...")

# ====================== INITIALIZE LSTM GENERATOR ======================

print("\n" + "=" * 70)
print("INITIALIZING LSTM VIEW GENERATOR")
print("=" * 70)

try:
    lstm_gen = LSTMViewGenerator(
        sequence_length=30,
        hidden_size=64,
        num_layers=2,
        learning_rate=0.001,
        epochs=50,
        batch_size=32,
    )
    print("✓ LSTM generator initialized")
    print(f"  Sequence length: {lstm_gen.sequence_length}")
    print(f"  Hidden size: {lstm_gen.hidden_size}")
    print(f"  Layers: {lstm_gen.num_layers}")
    print(f"  Epochs: {lstm_gen.epochs}")
    print(f"  Batch size: {lstm_gen.batch_size}")
except Exception as e:
    print(f"❌ Failed to initialize: {e}")
    exit(1)

# ====================== TRAIN OR LOAD MODELS ======================

# Note: LSTMViewGenerator doesn't support save/load yet, always train
print("\n" + "=" * 70)
print("TRAINING LSTM MODELS")
print("=" * 70)
print("\nLoading training data...")

# Load training data
train_data = {}

# E1VFVN30
e1_train_path = DATASETS_DIR / "stocks" / "train" / "E1VFVN30_train.csv"
if e1_train_path.exists():
    df = pd.read_csv(e1_train_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    train_data["E1VFVN30"] = df["close"]
    print(f"  ✓ E1VFVN30: {len(df)} days")

# GOLD
gold_train_path = DATASETS_DIR / "gold" / "gold_train.csv"
if gold_train_path.exists():
    df = pd.read_csv(gold_train_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    train_data["GOLD"] = df["sjc_sell"]
    print(f"  ✓ GOLD: {len(df)} days")

# DCDS
dcds_train_path = DATASETS_DIR / "funds" / "train" / "DCDS_train.csv"
if dcds_train_path.exists():
    df = pd.read_csv(dcds_train_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    train_data["DCDS"] = df["price"]
    print(f"  ✓ DCDS: {len(df)} days")

# MBBOND
mbbond_train_path = DATASETS_DIR / "funds" / "train" / "MBBOND_train.csv"
if mbbond_train_path.exists():
    df = pd.read_csv(mbbond_train_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    train_data["MBBOND"] = df["price"]
    print(f"  ✓ MBBOND: {len(df)} days")

train_prices = pd.DataFrame(train_data)

print(f"\nTraining data shape: {train_prices.shape}")
print(f"Date range: {train_prices.index[0].date()} to {train_prices.index[-1].date()}")

print("\n⏳ Training LSTM models (this may take several minutes)...")
print("=" * 70)

try:
    lstm_gen.train(train_prices, verbose=True)
    print("\n✓ LSTM models trained successfully")

    # Note: LSTMViewGenerator doesn't have save_models method yet
    # Models will need to be retrained each time
    # CACHE_DIR.mkdir(exist_ok=True)
    # lstm_gen.save_models(str(lstm_model_path))
    # print(f"✓ Models saved to: {lstm_model_path}")
except Exception as e:
    print(f"\n❌ Training failed: {e}")
    import traceback

    traceback.print_exc()
    exit(1)

# ====================== GENERATE VIEWS ======================

print("\n" + "=" * 70)
print("GENERATING VIEWS")
print("=" * 70)

try:
    views = lstm_gen.generate_views(prices, min_return_threshold=0.0)  # Lower threshold
    print(f"\n✓ Generated {len(views)} views")
except Exception as e:
    print(f"\n❌ View generation failed: {e}")
    import traceback

    traceback.print_exc()
    exit(1)

# ====================== DISPLAY RESULTS ======================

print("\n" + "=" * 70)
print("RESULTS")
print("=" * 70)

if views:
    print(f"\n✓ Generated {len(views)} LSTM views:\n")

    for i, view in enumerate(views, 1):
        asset_name = view["name"].replace("_lstm", "")

        print(f"{i}. {view['name']}")
        print(f"   Asset: {asset_name}")
        print(f"   Expected annual return: {view['view_return_annual']:.2%}")
        print(f"   Confidence: {view['confidence']:.2f}")
        print(f"   Source: {view['source']}")

        # Additional info
        if "prediction_days_ahead" in view:
            print(f"   Prediction horizon: {view['prediction_days_ahead']} days")

        if "last_price" in view:
            print(f"   Last price: {view['last_price']:,.2f}")

        if "predicted_price" in view:
            print(f"   Predicted price: {view['predicted_price']:,.2f}")

        print()
else:
    print("\n⚠ No views generated")

# ====================== VALIDATION ======================

print("=" * 70)
print("VALIDATION")
print("=" * 70)

# Get predictions directly
print("\nGetting predictions on test data...")

predictions_dict = lstm_gen.predict(prices)

if predictions_dict:
    print(f"\n✓ Got predictions for {len(predictions_dict)} assets:\n")

    for asset, (pred_return, confidence) in predictions_dict.items():
        annual_return = pred_return * (252 / lstm_gen.prediction_horizon)
        print(f"  {asset}:")
        print(
            f"    Predicted return ({lstm_gen.prediction_horizon}d): {pred_return:.4f} ({pred_return * 100:.2f}%)"
        )
        print(f"    Annualized: {annual_return:.4f} ({annual_return * 100:.2f}%)")
        print(f"    Confidence: {confidence:.2f}")
else:
    print("\n⚠ No predictions generated")

# ====================== SUMMARY ======================

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"\nAssets with views: {len(views)}")
print(f"Assets with predictions: {len(predictions_dict)}")

print("\n✓ LSTM view generation complete!")
print("\nNext steps:")
print("  1. Integrate LSTM views into backtest.py")
print("  2. Compare LSTM vs Traditional ML vs Rule-based")
print("  3. Analyze results for thesis")
