"""Data-loading helpers for VN30 universe, market proxy, and pretrained ML models."""

from pathlib import Path

from config import BACKTEST_DATA_MODE, VN30_LIST_PATH
from gen_view.xgboost.xgboost_core import XGBoostCoreModel
from utils.data_loader import build_price_table

ROOT_DIR = Path(__file__).resolve().parents[1]
ML_MODEL_CACHE_DIR = ROOT_DIR / "gen_view" / "xgboost" / ".cache"


def load_vn30_universe_prices(start_date, end_date, phase, window):
    """Load price data for the full VN30 stock universe (for K-Medoids selection)."""
    vn30_list_path = ROOT_DIR / VN30_LIST_PATH
    with open(vn30_list_path, "r") as f:
        vn30_tickers = [line.strip() for line in f if line.strip()]

    vn30_assets = {}
    for ticker in vn30_tickers:
        vn30_assets[ticker] = {
            "full_path": ROOT_DIR / f"datasets/stocks/full/{ticker}.csv",
            "train_path": ROOT_DIR / f"datasets/stocks/train/{ticker}_train.csv",
            "test_path": ROOT_DIR / f"datasets/stocks/test/{ticker}_test.csv",
            "date_col": "date",
            "price_col": "close",
        }

    return build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=vn30_assets,
        phase=phase,
        data_mode=BACKTEST_DATA_MODE,
        window=window,
    )


def load_market_proxy_prices(start_date, end_date, phase, window):
    """Load E1VFVN30 ETF prices as market proxy."""
    market_asset = {
        "E1VFVN30": {
            "full_path": ROOT_DIR / "datasets/stocks/full/E1VFVN30.csv",
            "train_path": ROOT_DIR / "datasets/stocks/train/E1VFVN30_train.csv",
            "test_path": ROOT_DIR / "datasets/stocks/test/E1VFVN30_test.csv",
            "date_col": "date",
            "price_col": "close",
        }
    }
    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=market_asset,
        phase=phase,
        data_mode=BACKTEST_DATA_MODE,
        window=window,
    )
    return prices["E1VFVN30"]


def load_ml_model(model_type: str) -> XGBoostCoreModel:
    """Load a pretrained ML model from the cache directory."""
    model_candidates = {
        "xgboost": [
            ML_MODEL_CACHE_DIR / "xgboost_models.pkl",
            ROOT_DIR / ".cache" / "xgboost_models.pkl",
        ],
    }

    candidates = model_candidates.get(model_type, [])
    model_path = next((p for p in candidates if p.exists()), None)

    if model_path is None:
        searched = "\n".join(str(p) for p in candidates)
        raise FileNotFoundError(
            "Khong tim thay model da train truoc do.\n"
            "Hay train model truoc bang: python gen_view/xgboost/model_train.py --method xgboost\n"
            f"Da tim o:\n{searched}"
        )

    model = XGBoostCoreModel()
    model.load(model_path)
    return model
