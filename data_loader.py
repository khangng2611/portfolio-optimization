from datetime import datetime
import json
from pathlib import Path

import pandas as pd


TRAIN_START_DATE = "2020-01-01"
SPLIT_DATE = "2023-10-01"
TEST_END_DATE = "2026-03-01"

ROOT_DIR = Path(__file__).resolve().parents[0]
DATASETS_DIR = ROOT_DIR / "datasets"
DEFAULT_ASSETS_CONFIG_PATH = ROOT_DIR /"assets.json"

PHASE_PERIODS = {
    "train": (TRAIN_START_DATE, SPLIT_DATE),
    "test": (SPLIT_DATE, TEST_END_DATE),
    "full": (TRAIN_START_DATE, TEST_END_DATE),
}


def _resolve_path(path_value: str) -> Path:
    path_obj = Path(path_value)
    if path_obj.is_absolute():
        return path_obj
    return ROOT_DIR / path_obj


def load_assets_config(config_path=None, selected_assets=None):
    cfg_path = Path(config_path) if config_path else DEFAULT_ASSETS_CONFIG_PATH
    if not cfg_path.is_absolute():
        cfg_path = ROOT_DIR / cfg_path
    if not cfg_path.exists():
        raise FileNotFoundError(f"Khong tim thay file assets config: {cfg_path}")

    with open(cfg_path, "r", encoding="utf-8") as f:
        raw_config = json.load(f)

    if "assets" not in raw_config or not isinstance(raw_config["assets"], dict):
        raise ValueError("assets config phai co key 'assets' dang object")

    raw_assets = raw_config["assets"]
    default_selection = raw_config.get("default_selection")

    if selected_assets is None:
        if isinstance(default_selection, list) and len(default_selection) > 0:
            selection = default_selection
        else:
            selection = list(raw_assets.keys())
    else:
        selection = selected_assets

    missing_assets = [asset for asset in selection if asset not in raw_assets]
    if missing_assets:
        raise ValueError(
            f"Assets khong ton tai trong config: {', '.join(missing_assets)}"
        )

    resolved_assets = {}
    required_keys = ["full_path", "train_path", "test_path", "date_col", "price_col"]
    for asset_name in selection:
        item = raw_assets[asset_name]
        missing_keys = [key for key in required_keys if key not in item]
        if missing_keys:
            raise ValueError(
                f"Asset '{asset_name}' thieu cac truong: {', '.join(missing_keys)}"
            )

        resolved_assets[asset_name] = {
            "full_path": _resolve_path(item["full_path"]),
            "train_path": _resolve_path(item["train_path"]),
            "test_path": _resolve_path(item["test_path"]),
            "date_col": item["date_col"],
            "price_col": item["price_col"],
        }

    if len(resolved_assets) == 0:
        raise ValueError("Khong co asset nao duoc chon de backtest")

    return resolved_assets


def resolve_period(args, phase_periods, backtest_phase):
    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise ValueError(
                "When overriding dates, both --start-date and --end-date are required"
            )
        return args.start_date, args.end_date
    return phase_periods[backtest_phase]


def resolve_asset_path(cfg, phase, data_mode):
    if data_mode == "split" and phase in ("train", "test"):
        key = f"{phase}_path"
        p = cfg.get(key)
        if p is not None and Path(p).exists():
            return p
    return cfg["full_path"]


def load_asset_series(asset_name, cfg, phase, data_mode, start_date, end_date):
    if data_mode == "split" and phase == "full":
        train_path = cfg.get("train_path")
        test_path = cfg.get("test_path")
        if (
            train_path is not None
            and test_path is not None
            and Path(train_path).exists()
            and Path(test_path).exists()
        ):
            df_train = pd.read_csv(train_path)
            df_test = pd.read_csv(test_path)
            df = pd.concat([df_train, df_test], ignore_index=True)
        else:
            path = resolve_asset_path(cfg, phase, data_mode)
            df = pd.read_csv(path)
    else:
        path = resolve_asset_path(cfg, phase, data_mode)
        df = pd.read_csv(path)

    df[cfg["date_col"]] = pd.to_datetime(df[cfg["date_col"]], errors="coerce")
    df = df.dropna(subset=[cfg["date_col"], cfg["price_col"]])

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    series = (
        df[(df[cfg["date_col"]] >= start_ts) & (df[cfg["date_col"]] <= end_ts)][
            [cfg["date_col"], cfg["price_col"]]
        ]
        .drop_duplicates(subset=[cfg["date_col"]], keep="last")
        .sort_values(cfg["date_col"])
        .set_index(cfg["date_col"])[cfg["price_col"]]
        .astype(float)
    )
    series.name = asset_name
    return series


def build_price_table(start_date, end_date, assets, phase="full", data_mode="split", window=20):
    calendar = pd.date_range(start=start_date, end=end_date, freq="B")
    data = {}

    for asset, cfg in assets.items():
        series = load_asset_series(asset, cfg, phase, data_mode, start_date, end_date)
        series = series.reindex(calendar).ffill()
        data[asset] = series

    prices = pd.DataFrame(data, index=calendar)
    prices = prices.dropna(how="any")
    if len(prices) <= window:
        raise ValueError(
            f"Khong du du lieu sau khi dong bo: {len(prices)} dong, can > WINDOW={window}"
        )
    return prices


def summarize_asset_returns(prices, trading_days_per_year):
    returns = prices.pct_change().dropna()
    total_return = prices.iloc[-1] / prices.iloc[0] - 1
    annualized_return = (1 + total_return) ** (trading_days_per_year / len(returns)) - 1
    annualized_vol = returns.std() * (trading_days_per_year ** 0.5)
    return pd.DataFrame(
        {
            "Total Return": total_return,
            "Annualized Return": annualized_return,
            "Annualized Vol": annualized_vol,
        }
    )