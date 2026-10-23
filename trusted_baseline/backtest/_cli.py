"""CLI argument parsing for the backtest entry point."""

import argparse

from config import (
    BACKTEST_PHASE,
    ML_MODEL_TYPE,
    ML_TRAINING_MODE,
    PHASE_PERIODS,
    VIEW_MODE,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backtest EW/MVO/BL on dataset"
    )
    parser.add_argument(
        "--start-date", default=None, help="Override start date YYYY-MM-DD"
    )
    parser.add_argument("--end-date", default=None, help="Override end date YYYY-MM-DD")
    parser.add_argument(
        "--no-plot", action="store_true", help="Disable NAV comparison plot"
    )
    parser.add_argument(
        "--assets-config",
        default=None,
        help="Path to assets JSON config (default: datasets/assets.json)",
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated asset list, e.g. E1VFVN30,GOLD,DCDS",
    )
    parser.add_argument(
        "--phase",
        choices=list(PHASE_PERIODS.keys()),
        default=BACKTEST_PHASE,
        help="Backtest phase: train/test/full",
    )
    parser.add_argument(
        "--view-mode",
        choices=["rule_based", "relative", "ml", "combined", "ranking", "ranking_absolute"],
        default=VIEW_MODE,
        help="View generation mode",
    )
    parser.add_argument(
        "--ml-model-type",
        choices=["xgboost"],
        default=ML_MODEL_TYPE,
        help="ML model for ml/combined view mode",
    )
    parser.add_argument(
        "--ml-training-mode",
        choices=["pretrained", "walk_forward"],
        default=ML_TRAINING_MODE,
        help="ML training mode: pretrained (load cached) or walk_forward (retrain during backtest)",
    )
    return parser.parse_args()
