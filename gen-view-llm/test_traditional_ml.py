"""
Test Traditional ML View Generators
====================================

Test Random Forest và XGBoost (không cần API key, miễn phí 100%)
"""

import pandas as pd
from pathlib import Path

from llm_view_generators import TraditionalMLViewGenerator

# ====================== LOAD DATA ======================

ROOT_DIR = Path(__file__).resolve().parents[0]
DATASETS_DIR = ROOT_DIR / "datasets"

print("=" * 70)
print("TESTING TRADITIONAL ML VIEW GENERATORS")
print("=" * 70)

print("\nLoading data...")

# Load train data (2020-2023)
assets_data_train = {}

# E1VFVN30
e1_path = DATASETS_DIR / "stocks" / "train" / "E1VFVN30_train.csv"
if e1_path.exists():
    df = pd.read_csv(e1_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data_train["E1VFVN30"] = df["close"]
    print(f"  ✓ E1VFVN30 (train): {len(df)} days")

# GOLD
gold_path = DATASETS_DIR / "gold" / "gold_train.csv"
if gold_path.exists():
    df = pd.read_csv(gold_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data_train["GOLD"] = df["sjc_sell"]
    print(f"  ✓ GOLD (train): {len(df)} days")

# DCDS
dcds_path = DATASETS_DIR / "funds" / "train" / "DCDS_train.csv"
if dcds_path.exists():
    df = pd.read_csv(dcds_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data_train["DCDS"] = df["price"]
    print(f"  ✓ DCDS (train): {len(df)} days")

# MBBOND
mbbond_path = DATASETS_DIR / "funds" / "train" / "MBBOND_train.csv"
if mbbond_path.exists():
    df = pd.read_csv(mbbond_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data_train["MBBOND"] = df["price"]
    print(f"  ✓ MBBOND (train): {len(df)} days")

train_prices = pd.DataFrame(assets_data_train)

print(f"\nTrain data shape: {train_prices.shape}")
print(f"Date range: {train_prices.index[0].date()} to {train_prices.index[-1].date()}")

# Load test data
assets_data_test = {}

# E1VFVN30
e1_path = DATASETS_DIR / "stocks" / "test" / "E1VFVN30_test.csv"
if e1_path.exists():
    df = pd.read_csv(e1_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data_test["E1VFVN30"] = df["close"]

# GOLD
gold_path = DATASETS_DIR / "gold" / "gold_test.csv"
if gold_path.exists():
    df = pd.read_csv(gold_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data_test["GOLD"] = df["sjc_sell"]

# DCDS
dcds_path = DATASETS_DIR / "funds" / "test" / "DCDS_test.csv"
if dcds_path.exists():
    df = pd.read_csv(dcds_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data_test["DCDS"] = df["price"]

# MBBOND
mbbond_path = DATASETS_DIR / "funds" / "test" / "MBBOND_test.csv"
if mbbond_path.exists():
    df = pd.read_csv(mbbond_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data_test["MBBOND"] = df["price"]

test_prices = pd.DataFrame(assets_data_test)
test_prices = test_prices.tail(60)  # Last 60 days for testing

print(f"Test data shape: {test_prices.shape}")
print(f"Date range: {test_prices.index[0].date()} to {test_prices.index[-1].date()}")

# ====================== TEST RANDOM FOREST ======================

print("\n" + "=" * 70)
print("OPTION 1: RANDOM FOREST")
print("=" * 70)

rf_gen = TraditionalMLViewGenerator(
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

print("\nTraining Random Forest...")
rf_gen.train(train_prices, verbose=True)

print("\nGenerating views on test data...")
rf_views = rf_gen.generate_views(test_prices)

print(f"\n✓ Generated {len(rf_views)} views:")
for i, view in enumerate(rf_views, 1):
    print(f"\n{i}. {view['name']}")
    print(f"   Expected annual return: {view['view_return_annual']:.2%}")
    print(f"   Confidence: {view['confidence']:.2f}")
    if "predicted_return_horizon" in view:
        print(f"   Predicted return (5 days): {view['predicted_return_horizon']:.2%}")

# Save model
print("\nSaving model...")
rf_gen.save(".cache/rf_models.pkl")
print("✓ Model saved to .cache/rf_models.pkl")

# ====================== TEST XGBOOST ======================

print("\n" + "=" * 70)
print("OPTION 2: XGBOOST")
print("=" * 70)

try:
    xgb_gen = TraditionalMLViewGenerator(
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

    print("\nTraining XGBoost...")
    xgb_gen.train(train_prices, verbose=True)

    print("\nGenerating views on test data...")
    xgb_views = xgb_gen.generate_views(test_prices)

    print(f"\n✓ Generated {len(xgb_views)} views:")
    for i, view in enumerate(xgb_views, 1):
        print(f"\n{i}. {view['name']}")
        print(f"   Expected annual return: {view['view_return_annual']:.2%}")
        print(f"   Confidence: {view['confidence']:.2f}")

    # Save model
    print("\nSaving model...")
    xgb_gen.save(".cache/xgb_models.pkl")
    print("✓ Model saved to .cache/xgb_models.pkl")

except ImportError:
    print("\n⚠ XGBoost not installed. Skipping.")
    print("Install with: pip install xgboost")

# ====================== SUMMARY ======================

print("\n" + "=" * 70)
print("TEST COMPLETE!")
print("=" * 70)

print("\n✓ Random Forest trained and saved")
print("✓ Views generated successfully")
print("\nModels saved to .cache/ directory")
print("\nNext steps:")
print("1. Review the generated views - do they make sense?")
print("2. Test LSTM: python test_lstm.py")
print("3. When OpenAI quota is ready: python test_llm.py")
print("4. Integrate into backtest.py")
