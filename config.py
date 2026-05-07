"""Project-wide configuration constants."""

# ====================== SHARED ======================
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.06

# ====================== DATA SPLIT ======================
TRAIN_START_DATE = "2020-01-01"
SPLIT_DATE = "2023-10-01"
TEST_END_DATE = "2026-03-01"

PHASE_PERIODS = {
    "train": (TRAIN_START_DATE, SPLIT_DATE),
    "test": (SPLIT_DATE, TEST_END_DATE),
    "full": (TRAIN_START_DATE, TEST_END_DATE),
}

# ====================== BACKTEST ======================
BACKTEST_PHASE = "train"
BACKTEST_DATA_MODE = "split"

ASSETS_CONFIG_FILENAME = "assets_0.json"

WINDOW = 20
REBALANCE_FREQ = 5
INITIAL_NAV = 1.0
MAX_POSITION_SIZE = 0.40            # Max weight per asset (diversification constraint)

# ====================== BLACK-LITTERMAN ======================
BL_TAU = 0.05
BL_DELTA = 2.5
BL_VIEW_CONFIDENCE = 0.5

# ====================== VIEW GENERATION ======================
# View generation mode: "rule_based", "relative", "ml", "combined"
VIEW_MODE = "ml" 

# Combined view weights: (rule_based, relative, ml, static)
COMBINED_VIEW_WEIGHTS = (0.3, 0.3, 0.4, 0.0)

# Static views (used as part of combined view mode)
STATIC_VIEWS = [
    {
        "name": "GOLD_over_E1VFVN30",
        "legs": {"GOLD": 1.0, "E1VFVN30": -1.0},
        "view_return_annual": 0.06,
        "confidence": 0.70,
    },
    {
        "name": "MBBOND_over_DCDS",
        "legs": {"MBBOND": 1.0, "DCDS": -1.0},
        "view_return_annual": 0.015,
        "confidence": 0.60,
    },
]

# ====================== ML DEFAULTS ======================
ML_MODEL_TYPE = "xgboost"
ML_FEATURE_WINDOW = 20
ML_PREDICTION_HORIZON = 5
ML_MIN_RETURN_THRESHOLD = 0.005

# ML Training mode: "pretrained" (load from cache) or "walk_forward" (retrain during backtest)
ML_TRAINING_MODE = "walk_forward"
ML_RETRAIN_FREQUENCY = 20
