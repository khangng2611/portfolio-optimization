"""Project-wide configuration constants."""

# ====================== SHARED ======================
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.06

# ====================== BACKTEST ======================
BACKTEST_PHASE = "test"
BACKTEST_DATA_MODE = "split"

WINDOW = 20
REBALANCE_FREQ = 5
INITIAL_NAV = 1.0

# ====================== BLACK-LITTERMAN ======================
BL_TAU = 0.05
BL_DELTA = 2.5
BL_VIEW_CONFIDENCE = 0.5

# ====================== VIEW GENERATION ======================
VIEW_MODE = "combined"

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

# Combined view weights: (rule_based, relative, ml, static)
COMBINED_VIEW_WEIGHTS = (0.4, 0.3, 0.3, 0.0)

# ====================== ML DEFAULTS ======================
ML_MODEL_TYPE = "xgboost"
ML_FEATURE_WINDOW = 20
ML_PREDICTION_HORIZON = 5
ML_MIN_RETURN_THRESHOLD = 0.005
