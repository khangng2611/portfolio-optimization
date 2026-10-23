"""Project-wide configuration constants."""

# ====================== SHARED ======================
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.06

# ====================== DATA SPLIT ======================
TRAIN_START_DATE = "2020-01-01"
SPLIT_DATE = "2023-10-01"
# TEST_END_DATE = "2026-03-01"
TEST_END_DATE = "2026-07-01"

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
MAX_POSITION_SIZE = 0.5            # Max weight per asset (diversification constraint)
MIN_WEIGHT_THRESHOLD = 0.01         # Post-solve: zero out weights below 1% and redistribute

# ====================== BLACK-LITTERMAN ======================
BL_TAU = 0.05
BL_DELTA = 2.5
BL_VIEW_DEFAULT_CONFIDENCE_WHEN_NULL = 0.5

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
ML_MIN_ALLOWED_PREDICTION_RETURN = 0.001
ML_MAX_ANNUAL_VIEW_THRESHOLD = 0.5     # max annual view magnitude (hard cap)

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

# ====================== VOLATILITY DAMPENER ======================
VOL_DAMPENER_RECENT_WINDOW = 20        # Recent vol lookback (trading days)
VOL_DAMPENER_HIST_WINDOW = 120         # Historical vol lookback (trading days)
VOL_DAMPENER_THRESHOLD = 1.3           # Vol ratio threshold for confidence reduction
VOL_DAMPENER_SEVERE = 1.8              # Severe vol -> more aggressive dampening

# ====================== RISK MANAGEMENT ======================
MIN_DEFENSIVE_WEIGHT = 0.15    # Min in defensive assets
MAX_EQUITY_EXPOSURE = 0.70     # Max 70% total in stocks
DRAWDOWN_LOOKBACK = 60         # Days to compute recent drawdown
DRAWDOWN_STRESS_THRESHOLD = -0.10     # 10% drawdown triggers stress mode
DRAWDOWN_CRISIS_THRESHOLD = -0.20     # 20% drawdown triggers crisis mode
RISK_AVERSION_BASE = 1.5       # Higher risk aversion for ranking mode (vs 0.5 default)
RISK_AVERSION_STRESS = 5.0     # Even higher during stress regime
DEFAULT_DEFENSIVE_ASSETS = ["VFF"]

# Defensive Assets Return Spreads
DEFENSIVE_CONFIDENCE = 0.80    # Confidence for defensive views in stress
EXPECTED_ANNUAL_SPREAD_IN_CRISIS_REGIME = 0.10 
EXPECTED_CONF_IN_CRISIS_REGIME = 1.0
EXPECTED_ANNUAL_SPREAD_IN_STRESS_REGIME = 0.05
EXPECTED_CONF_IN_STRESS_REGIME = 0.85

# ====================== HYBRID MVO+BL STRATEGY ======================
# HYBRID weights are a regime-aware convex combination of MVO and BL weights:
#     w_hybrid = alpha(regime) * w_mvo + (1 - alpha(regime)) * w_bl
# alpha (the MVO share) is reduced as the market regime worsens, so the
# portfolio leans toward MVO upside during calm markets and toward BL's
# defensive posterior during stress / crisis.
ENABLE_HYBRID_STRATEGY = True
HYBRID_MVO_RATIO_NORMAL = 0.60   # Normal: balanced, slight MVO tilt
HYBRID_MVO_RATIO_STRESS = 0.30   # Stress: BL-leaning
HYBRID_MVO_RATIO_CRISIS = 0.10   # Crisis: BL-dominant (small MVO satellite)

HYBRID_REGIME_RATIOS = {
    "normal": HYBRID_MVO_RATIO_NORMAL,
    "stress": HYBRID_MVO_RATIO_STRESS,
    "crisis": HYBRID_MVO_RATIO_CRISIS,
}
