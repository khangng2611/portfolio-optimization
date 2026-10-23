"""Final allocation feasibility, including pruning and solver failure."""
import unittest
from unittest.mock import patch

import numpy as np
import cvxpy as cp

from backtest import _optimizer as opt


class OptimizerIntegrityTests(unittest.TestCase):
    def assert_feasible(self, weights, max_weight=.5):
        self.assertTrue(np.isfinite(weights).all())
        self.assertAlmostEqual(float(weights.sum()), 1., delta=1e-8)
        self.assertGreaterEqual(float(weights.min()), -1e-8)
        self.assertLessEqual(float(weights.max()), max_weight + 1e-8)

    def test_standard_pruning_cannot_exceed_position_cap(self):
        # Real solver boundary fixture; the old proportional redistribution
        # produces .50251256 in the first position from this feasible input.
        with patch.object(opt, "_solve_mvo", return_value=np.array([.5, .495, .005])):
            weights = opt.optimize_weight(np.zeros(3), np.eye(3))
        self.assert_feasible(weights)
        np.testing.assert_allclose(weights, [.5, .5, 0.], atol=1e-8)

    def test_ranking_pruning_preserves_cap_and_nondefensive_limit(self):
        with patch.object(opt, "_solve_mvo", return_value=np.array([.5, .195, .005, .3])):
            weights = opt.optimize_weight_ranking(np.zeros(4), np.eye(4), ["A", "B", "GOLD", "VFF"])
        self.assert_feasible(weights)
        self.assertGreaterEqual(float(weights[3]), .3 - 1e-8)
        self.assertLessEqual(float(weights[:3].sum()), .7 + 1e-8)

    def test_pruning_retains_tiny_position_when_survivors_cannot_fill_budget(self):
        with patch.object(opt, "_solve_mvo", return_value=np.array([.499, .499, .002])):
            weights = opt.optimize_weight(np.zeros(3), np.eye(3), max_weight=.499)
        self.assert_feasible(weights, max_weight=.499)
        np.testing.assert_allclose(weights, [.499, .499, .002], atol=1e-8)

    def test_infeasible_single_asset_cap_raises_instead_of_bad_fallback(self):
        with patch.object(opt, "_solve_mvo", return_value=None):
            with self.assertRaises(ValueError):
                opt.optimize_weight(np.zeros(1), np.eye(1), max_weight=.5)

    def test_solver_failure_respects_effective_vff_floor(self):
        with patch.object(opt, "_solve_mvo", return_value=None):
            weights = opt.optimize_weight_ranking(np.zeros(7), np.eye(7), ["A", "B", "C", "D", "E", "GOLD", "VFF"])
        self.assert_feasible(weights)
        self.assertGreaterEqual(float(weights[-1]), .3 - 1e-8)
        self.assertLessEqual(float(weights[:-1].sum()), .7 + 1e-8)

    def test_solver_failure_all_defensive_assets_still_spends_full_budget(self):
        with patch.object(opt, "_solve_mvo", return_value=None):
            weights = opt.optimize_weight_ranking(np.zeros(2), np.eye(2), ["VFF", "BOND"], defensive_assets=["VFF", "BOND"])
        self.assert_feasible(weights)
        np.testing.assert_allclose(weights, [.5, .5], atol=1e-8)

    def test_infeasible_absent_defensive_asset_raises_instead_of_bad_fallback(self):
        with patch.object(opt, "_solve_mvo", return_value=None):
            with self.assertRaises(ValueError):
                opt.optimize_weight_ranking(np.zeros(2), np.eye(2), ["A", "GOLD"])

    def test_hybrid_pruning_preserves_position_cap_without_adding_bl_floor(self):
        weights = opt.blend_weights(np.array([.5, .495, .005, 0.]), np.array([.5, .49, .005, .005]), .6)
        self.assert_feasible(weights)
        self.assertEqual(float(weights[-1]), 0.)
        np.testing.assert_allclose(weights[:2], [.5, .5], atol=1e-8)

    def test_zero_hybrid_inputs_cannot_bypass_an_infeasible_cap(self):
        with self.assertRaises(ValueError):
            opt.blend_weights(np.zeros(1), np.zeros(1), .6)

    def test_optimal_status_does_not_accept_infeasible_cleaned_solver_vector(self):
        # Force the numerical-solver boundary, while using real CVXPY variable
        # and constraints. Clipping this raw vector then normalizing makes
        # its second position exceed .5 by approximately 2.5e-6.
        variable = cp.Variable(3)
        objective = cp.Maximize(variable[0])
        constraints = [cp.sum(variable) == 1, variable >= 0, variable <= .5]

        def inaccurate_solve(problem, **kwargs):
            problem.variables()[0].value = np.array([.5, .500005, -.000005])
            problem._status = cp.OPTIMAL

        with patch.object(cp, "installed_solvers", return_value=["OSQP"]), \
                patch.object(cp.Problem, "solve", new=inaccurate_solve):
            result = opt._solve_mvo(objective, constraints, 3)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
