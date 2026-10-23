"""Data-loading helpers for VN30 universe, market proxy, and pretrained ML models."""

from pathlib import Path

from config import BACKTEST_DATA_MODE, VN30_LIST_PATH
from gen_view.xgboost.xgboost_core import XGBoostCoreModel
from utils.data_loader import build_price_table, load_assets_config, load_raw_assets_config

ROOT_DIR = Path(__file__).resolve().parents[1]
ML_MODEL_CACHE_DIR = ROOT_DIR / "gen_view" / "xgboost" / ".cache"

# Fallback defaults used when the assets JSON config does not override them.
DEFAULT_MARKET_PROXY = "E1VFVN30"
DEFAULT_ML_MODEL_CACHE_PATHS = {
    "xgboost": [
        ML_MODEL_CACHE_DIR / "xgboost_models.pkl",
        ROOT_DIR / ".cache" / "xgboost_models.pkl",
    ],
}


def _resolve_vn30_universe(raw_config):
    """Return the VN30 ticker list from the raw config, falling back to the txt file."""
    vn30 = raw_config.get("vn30_universe")
    if isinstance(vn30, list) and vn30:
        return [t.strip() for t in vn30 if isinstance(t, str) and t.strip()]
    # Backward-compat fallback: read from datasets/vn30_list.txt
    vn30_list_path = ROOT_DIR / VN30_LIST_PATH
    with open(vn30_list_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_vn30_universe_prices(start_date, end_date, phase, window, assets_config_path=None):
    """Load price data for the full VN30 stock universe (for K-Medoids selection)."""
    raw_config = load_raw_assets_config(assets_config_path)
    vn30_tickers = _resolve_vn30_universe(raw_config)

    # Reuse the JSON-configured asset paths (resolved against ROOT_DIR) so we
    # no longer hardcode "datasets/stocks/..." patterns here.
    vn30_assets = load_assets_config(
        config_path=assets_config_path,
        selected_assets=vn30_tickers,
    )

    return build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=vn30_assets,
        phase=phase,
        data_mode=BACKTEST_DATA_MODE,
        window=window,
    )


def load_market_proxy_prices(start_date, end_date, phase, window, assets_config_path=None):
    """Load market-proxy ETF prices (configurable via ``market_proxy`` in assets JSON)."""
    raw_config = load_raw_assets_config(assets_config_path)
    proxy_ticker = raw_config.get("market_proxy") or DEFAULT_MARKET_PROXY
    if not isinstance(proxy_ticker, str) or not proxy_ticker.strip():
        raise ValueError(
            f"'market_proxy' trong assets config phai la string, got: {proxy_ticker!r}"
        )
    proxy_ticker = proxy_ticker.strip()

    market_asset = load_assets_config(
        config_path=assets_config_path,
        selected_assets=[proxy_ticker],
    )

    prices = build_price_table(
        start_date=start_date,
        end_date=end_date,
        assets=market_asset,
        phase=phase,
        data_mode=BACKTEST_DATA_MODE,
        window=window,
    )
    return prices[proxy_ticker]


def _resolve_ml_model_paths(model_type, raw_config):
    """Return candidate model paths for ``model_type`` from config or fallback defaults."""
    config_paths = raw_config.get("ml_model_cache_paths")
    if isinstance(config_paths, dict) and model_type in config_paths:
        raw_paths = config_paths[model_type]
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ValueError(
                f"ml_model_cache_paths['{model_type}'] phai la list cac duong dan"
            )
        resolved = []
        for p in raw_paths:
            path_obj = Path(p)
            resolved.append(path_obj if path_obj.is_absolute() else ROOT_DIR / path_obj)
        return resolved
    return DEFAULT_ML_MODEL_CACHE_PATHS.get(model_type, [])


def load_ml_model(model_type: str, assets_config_path=None) -> XGBoostCoreModel:
    """Load a pretrained ML model from the cache directory."""
    raw_config = load_raw_assets_config(assets_config_path) if assets_config_path else {}
    candidates = _resolve_ml_model_paths(model_type, raw_config)
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
