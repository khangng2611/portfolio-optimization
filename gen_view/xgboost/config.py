"""XGBoost module configuration constants."""

from pathlib import Path

# Paths
MODEL_DIR = Path(__file__).resolve().parent
CACHE_DIR = MODEL_DIR / ".cache"

# Model architecture defaults
DEFAULT_FEATURE_WINDOW = 20
DEFAULT_PREDICTION_HORIZON = 5

# XGBoost hyperparameters
DEFAULT_XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "random_state": 42,
}

# Feature engineering periods
MOMENTUM_PERIODS = [5, 10, 20]
RSI_PERIOD = 14
MA_SHORT_PERIOD = 10
MA_LONG_PERIOD = 30
VOLATILITY_WINDOW = 20
PRICE_STD_WINDOW = 20
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Training thresholds
MIN_DATA_SAMPLES = 50
MIN_VALID_SAMPLES = 50

# Prediction confidence heuristic (legacy single-model)
CONFIDENCE_MIN = 0.3
CONFIDENCE_MAX = 0.9
CONFIDENCE_BASE = 0.6
CONFIDENCE_VAR_SCALE = 5.0

# ====================== ENSEMBLE SETTINGS ======================
ENSEMBLE_SIZE = 5
ENSEMBLE_BASE_SEED = 42

# ====================== WALK-FORWARD SETTINGS ======================
RETRAIN_FREQUENCY = 20              # retrain every N trading days (~monthly)
MIN_TRAIN_SAMPLES = 100             # min observations before first train
VALIDATION_SPLIT_RATIO = 0.2        # last 20% for early stopping
EARLY_STOPPING_ROUNDS = 10

# ====================== ENSEMBLE CONFIDENCE ======================
ENSEMBLE_CONF_SCALE = 0.005         # normalizer for prediction std (typical 5-day return std)
ENSEMBLE_CONF_MIN = 0.25
ENSEMBLE_CONF_MAX = 0.70
