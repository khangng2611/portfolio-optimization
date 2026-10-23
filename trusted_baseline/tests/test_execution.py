"""Behavioral checks for next-close execution and fixed-share holdings."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from backtest._loop import backtest


class ExecutionTests(unittest.TestCase):
    def test_ranking_inputs_cannot_have_future_shifted_indices(self):
        prices = pd.DataFrame(100.0,index=pd.bdate_range("2024-01-01",periods=10),
                              columns=["A","B","C","D","E","GOLD","VFF"])
        universe = prices[["A","B","C","D","E"]].copy()
        universe.index = universe.index + pd.Timedelta(days=7)
        with self.assertRaisesRegex(ValueError,"align"):
            backtest(prices,window=2,rebalance_freq=5,view_mode="ranking_absolute",
                     ranking_universe_prices=universe,ranking_market_prices=prices["A"])

    def run_fixture(self, prices, warmup=0):
        target = np.array([0.5, 0.5, 0.0])
        with patch("backtest._loop.optimize_weight", return_value=target), \
             patch("backtest._loop.generate_dynamic_views", return_value=(None,None,None,[])), \
             patch("backtest._loop.detect_market_regime", return_value={"regime":"normal"}):
            return backtest(prices, window=2, rebalance_freq=5, view_mode="rule_based", warmup_end_index=warmup)

    def prices(self):
        return pd.DataFrame(100.0, index=pd.bdate_range("2024-01-01", periods=10), columns=["A","B","C"])

    def test_close_signal_cannot_earn_return_ending_at_execution(self):
        prices = self.prices()
        prices.loc[prices.index[3]:,"A"] = 200.0
        result = self.run_fixture(prices)
        self.assertAlmostEqual(result["mvo_nav"].loc[prices.index[3]], 1.0, places=12)

    def test_fixed_shares_allow_weights_to_drift_between_trades(self):
        prices = self.prices()
        prices.loc[prices.index[4]:,"A"] = 200.0
        prices.loc[prices.index[5]:,"B"] = 200.0
        result = self.run_fixture(prices)
        self.assertAlmostEqual(result["mvo_nav"].loc[prices.index[5]], 2.0, places=12)

    def test_oos_includes_first_eligible_return(self):
        prices = self.prices()
        prices.loc[prices.index[5]:,"A"] = 200.0
        # returns row 4 ends at price row 5, the first OOS date.
        result = self.run_fixture(prices, warmup=4)
        self.assertEqual(result["mvo_nav"].index[0], prices.index[4])
        self.assertAlmostEqual(result["mvo_nav"].loc[prices.index[5]], 1.5, places=12)

    def test_pending_order_executes_at_available_final_close_without_future_return(self):
        # Decisions at price rows2 and7 execute at rows3 and8. The second
        # execution is observable even though row9's earned return is absent.
        prices = self.prices().iloc[:9]
        result = self.run_fixture(prices)
        self.assertEqual(len(result["execution_ledger"]), 2)
        final = result["execution_ledger"][-1]
        self.assertEqual(final["decision_date"], prices.index[7])
        self.assertEqual(final["execution_date"], prices.index[8])
        self.assertIsNone(final["first_return_date"])
        self.assertEqual(final["execution_status"], "end_of_sample_no_return")
        self.assertIsNone(result["unexecuted_final_order"])
        self.assertTrue(any(row["date"] == prices.index[8]
                            for row in result["turnover_history"]))
        self.assertAlmostEqual(result["mvo_nav"].iloc[-1], 1.0, places=12)


if __name__ == "__main__":
    unittest.main()
