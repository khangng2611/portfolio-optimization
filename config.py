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

ASSETS_CONFIG_FILENAME = "assets_1.json"

WINDOW = 20
REBALANCE_FREQ = 5
INITIAL_NAV = 1.0
MAX_POSITION_SIZE = 0.40            # Max weight per asset (diversification constraint)

# ====================== BLACK-LITTERMAN ======================
BL_TAU = 0.05
BL_DELTA = 2.5
BL_VIEW_CONFIDENCE = 0.5

# ====================== VIEW GENERATION ======================
# View generation mode: "rule_based", "relative", "ml", "combined", "ranking", "ranking_absolute"
VIEW_MODE = "ranking_absolute" 

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

DEFAULT_FEATURE_WINDOW = 30
DEFAULT_PREDICTION_HORIZON = 5
ML_MIN_RETURN_THRESHOLD = 0.005

# ML Training mode: "pretrained" (load from cache) or "walk_forward" (retrain during backtest)
ML_TRAINING_MODE = "walk_forward"
RETRAIN_FREQUENCY = 10

# ====================== RANKING MODE ======================
RANKING_K = 5                          # Number of representative stocks to select
RANKING_PREDICTION_HORIZON = 5         # Forward-looking days for ranking labels
RANKING_FEATURE_WINDOW = 40            # Lookback window for feature computation
RANKING_RETRAIN_FREQUENCY = 10         # Retrain ranking model every N days
RANKING_RESELECT_FREQUENCY = 20        # Re-run K-Medoids every N days
RANKING_VIEW_SPREAD = 0.20             # Annual spread for relative views
VN30_LIST_PATH = "datasets/vn30_list.txt"

# ====================== RANKING RISK MANAGEMENT ======================
RANKING_MIN_DEFENSIVE_WEIGHT = 0.15    # Min in defensive assets
RANKING_MAX_EQUITY_EXPOSURE = 0.70     # Max 70% total in stocks
RANKING_VOL_DAMPENER_THRESHOLD = 1.3   # Vol ratio threshold for confidence reduction
RANKING_VOL_DAMPENER_SEVERE = 1.8      # Severe vol -> more aggressive dampening
RANKING_DRAWDOWN_LOOKBACK = 60         # Days to compute recent drawdown
RANKING_DRAWDOWN_STRESS_THRESHOLD = -0.10     # 10% drawdown triggers stress mode
RANKING_DRAWDOWN_CRISIS_THRESHOLD = -0.20     # 20% drawdown triggers crisis mode
RANKING_DEFENSIVE_CONFIDENCE = 0.80    # Confidence for defensive views in stress
RANKING_RISK_AVERSION_BASE = 1.5       # Higher risk aversion for ranking mode (vs 0.5 default)
RANKING_RISK_AVERSION_STRESS = 5.0     # Even higher during stress regime
RANKING_DEFAULT_DEFENSIVE_ASSETS = ["VFF"]
