"""Configuration constants for the ranking-based view generation module."""

from pathlib import Path

# Paths
RANKING_MODULE_DIR = Path(__file__).resolve().parent
RANKING_CACHE_DIR = RANKING_MODULE_DIR / ".cache"

# ====================== K-MEDOIDS SETTINGS ======================
KMEDOIDS_MAX_ITER = 100  # Maximum iterations for PAM algorithm

# ====================== XGBOOST RANKER HYPERPARAMETERS ======================
DEFAULT_RANKER_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "tree_method": "hist",
    "objective": "rank:pairwise",
}

# ====================== FEATURE ENGINEERING ======================
RANKING_MOMENTUM_PERIODS = [5, 20, 60]
RANKING_VOLATILITY_WINDOWS = [20, 60]
RANKING_RSI_PERIOD = 14
RANKING_MACD_FAST = 12
RANKING_MACD_SLOW = 26
RANKING_MACD_SIGNAL = 9
RANKING_BOLLINGER_PERIOD = 20
RANKING_BOLLINGER_STD = 2.0

# ====================== ENSEMBLE SETTINGS ======================
RANKING_ENSEMBLE_SIZE = 5
RANKING_ENSEMBLE_BASE_SEED = 42

# ====================== TRAINING SETTINGS ======================
RANKING_MIN_TRAIN_SAMPLES = 100
RANKING_VALIDATION_SPLIT_RATIO = 0.2
RANKING_EARLY_STOPPING_ROUNDS = 10

# ====================== CONFIDENCE SETTINGS ======================
RANKING_CONF_BASE = 0.50
RANKING_CONF_MIN = 0.25
RANKING_CONF_MAX = 0.75
RANKING_MARGIN_SCALE = 2.0  # Scale factor for margin-based confidence boost
RANKING_DISAGREEMENT_SCALE = 5.0  # Scale factor for ensemble disagreement penalty
