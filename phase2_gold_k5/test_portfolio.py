import json
import unittest

import numpy as np
import pandas as pd

from phase2_gold_k5.portfolio import Allocation, Market, known_weights, rebalance, simulate, view_row


class TestExecution(unittest.TestCase):
    def setUp(self):
        self.names = pd.Index(["GOLD", "A", "B", "C", "D", "E", "VFF", "X"])
        dates = pd.bdate_range("2020-03-02", periods=9)
        marks = np.full((9, 8), 100.)
        quotes = np.tile([99., 101., 99., 101.], (9, 1))
        self.market = Market(dates, self.names, marks, marks.copy(), quotes, dates.to_numpy())
        self.target = np.array([.2, .2, .1, .1, .05, .05, .3, 0.])
        self.allocation = Allocation(np.arange(7), np.zeros(7), np.eye(7)*.001, self.target)

    def test_side_cash_initial_buy_and_terminal_sale(self):
        units, cash, buy, fee = rebalance(np.zeros(2), 1., np.full(2, 100.), np.array([1.,0.]), 0, 99., 101., 0.)
        self.assertAlmostEqual(units[0], 1/101)
        self.assertAlmostEqual(cash, 0)
        self.assertAlmostEqual(buy, 1/101)
        self.assertEqual(fee, 0.)
        units, cash, sale, fee = rebalance(units, cash, np.full(2, 100.), np.array([0.,1.]), 0, 99., 101., .001)
        self.assertAlmostEqual(sale, 1/101)
        self.assertAlmostEqual(fee, units[1]*100*.001)
        self.assertAlmostEqual(units[1]*100+cash, (99/101)/1.001)

    def test_decision_next_close_and_fixed_units(self):
        self.market.marks[1:, 1] = 150.
        self.market.marks[2:, 1] = 165.
        self.market.quotes[:] = 100.
        daily, trades = simulate(self.market, {0:self.allocation}, "B1", False, 0)
        self.assertEqual(trades[0]["execution_date"], self.market.dates[1])
        self.assertAlmostEqual(daily[0][-1], 1.)
        self.assertAlmostEqual(daily[1][-1], 1.02)
        self.assertAlmostEqual(daily[-1][-1], 1.02)

    def test_missing_quote_skips_whole_order_and_logs_for_all_cost_policies(self):
        self.market.quotes[1,:2] = np.nan
        for gate in (False, True):
            daily, trades = simulate(self.market, {0:self.allocation, 3:self.allocation}, "B2", gate, 10)
            self.assertEqual(trades[0]["status"], "missing_quote")
            self.assertEqual(trades[0]["units_after"], "{}")
            self.assertTrue(trades[1]["initial_allocation"])
            self.assertEqual(trades[1]["status"], "executed")
            self.assertAlmostEqual(daily[2][-1], 1.)

    def test_gate_uses_available_prices_only(self):
        first = simulate(self.market, {0:self.allocation, 3:self.allocation}, "B2", True, 10)[1]
        # Previous real VFF fill and next GOLD quote change, eligible history is identical.
        self.market.marks[1,6] = 800.
        self.market.marks[4,0] = 63.
        self.market.quotes[4,:2] = [60.,66.]
        second = simulate(self.market, {0:self.allocation, 3:self.allocation}, "B2", True, 10)[1]
        for trades in [first, second]:
            self.assertEqual(trades[1]["status"], "gate_hold")
        for k in ("known_weights", "order_at_decision", "expected_cost", "utility_gain"):
            self.assertEqual(first[1][k], second[1][k])

    def test_gate_rejects_costly_change_and_admits_profitable_one(self):
        target = self.target.copy()
        target[0] += .1
        target[1] -= .1
        weak = Allocation(np.arange(7), np.zeros(7), np.zeros((7,7)), target)
        strong = Allocation(np.arange(7), np.array([.1,0,0,0,0,0,0]), np.zeros((7,7)), target)
        for allocation, expected in ((weak, "gate_hold"),(strong, "executed")):
            _, records = simulate(self.market, {0:self.allocation, 3:allocation}, "B2", True, 10)
            self.assertEqual(records[1]["status"], expected)
            self.assertFalse(records[1]["mandatory"])

    def test_member_exit_and_drift_force_feasible_target(self):
        target = self.target.copy()
        target[7], target[5] = target[5], 0
        changed = Allocation(np.array([0,1,2,3,4,7,6]), np.zeros(7), np.eye(7), target)
        _, records = simulate(self.market, {0:self.allocation, 3:changed}, "B1", True, 50)
        self.assertTrue(records[1]["mandatory"])
        self.assertEqual(records[1]["status"], "executed")
        self.assertNotIn("E", json.loads(records[1]["units_after"]))
        self.market.eligible[3,1] = 1000.
        _, records = simulate(self.market, {0:self.allocation, 3:self.allocation}, "B1", True, 50)
        self.assertTrue(records[1]["mandatory"])

    def test_delayed_vff_drift_only_uses_available_observations(self):
        dates = self.market.dates
        self.market.vff_observed = dates[[0,0,0,0,0,0,1,2,3]].to_numpy()
        self.market.eligible[:,6] = [60,60,60,60,60,60,70,84,90]
        self.market.marks[3,6] = 145.
        # Still no published VFF NAV after fill at index 3, so its drift is zero.
        np.testing.assert_allclose(known_weights(self.market, 7, 3, self.target, 6), self.target)
        # Fill at index 1 and mark at index 7: eligible NAVs 70 and 84.
        w = self.target.copy()
        w[6] *= 84/70
        np.testing.assert_allclose(known_weights(self.market, 7, 1, self.target, 6), w/w.sum())

    def test_relative_p_aligns_to_asset_identity(self):
        names = ["VFF","A","B","C","GOLD","D","E"]
        expected = [0.,-.2,-.2,-.2,1.,-.2,-.2]
        self.assertEqual(view_row(names, "derived"), expected)
        self.assertEqual(view_row(names, "direct"), expected)
        self.assertEqual(view_row(names, "gold"), [0.,0.,0.,0.,1.,0.,0.])


if __name__ == "__main__":
    unittest.main()
