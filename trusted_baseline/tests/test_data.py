import unittest
from unittest.mock import patch
import pandas as pd
from pathlib import Path
from utils.data_loader import build_price_table, load_assets_config, load_asset_series

ROOT = Path(__file__).resolve().parents[1]


class DataTests(unittest.TestCase):
    def test_non_session_nav_is_carried_to_next_exchange_session(self):
        values = pd.Series([100.0,110.0,120.0],index=pd.to_datetime(["2020-01-03","2020-01-04","2020-01-07"]),name="VFF")
        with patch("utils.data_loader.load_asset_series",return_value=values):
            actual = build_price_table("2020-01-03","2020-01-07",{"VFF":{}},window=1)
        self.assertEqual(actual.loc["2020-01-06","VFF"],110.0)

    def test_exchange_holidays_are_not_fictitious_trading_sessions(self):
        assets = load_assets_config(selected_assets=["FPT"])
        actual = build_price_table("2020-01-07","2020-01-31",assets,phase="full",data_mode="full",window=1)
        market = pd.read_csv(ROOT/"datasets/indices/full/VNINDEX.csv")
        expected = pd.DatetimeIndex(pd.to_datetime(market["date"]))
        expected = expected[(expected>="2020-01-07") & (expected<="2020-01-31")].sort_values().unique()
        self.assertEqual(list(actual.index),list(expected))

    def test_gold_full_loading_preserves_training_history(self):
        asset = load_assets_config(selected_assets=["GOLD"])["GOLD"]
        values = load_asset_series("GOLD",asset,"full","full","2020-01-01","2026-07-01")
        self.assertLessEqual(values.index.min(),pd.Timestamp("2020-01-07"))


if __name__ == "__main__":
    unittest.main()
