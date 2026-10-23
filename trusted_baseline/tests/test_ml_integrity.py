"""Behavioral integrity checks for the isolated research baseline.

Run from trusted_baseline with ../venv/bin/python -m unittest discover -s tests.
Real tiny XGBoost fits are used; no model artifact is saved.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from backtest._ranking_helpers import generate_ranking_abs_mode_views
from gen_view.xgboost.xgboost_core import XGBoostCoreModel, XGBoostEnsembleModel


def price_fixture(n=220):
    dates = pd.bdate_range('2020-01-02', periods=n)
    i = np.arange(n, dtype=float)
    # Reversals make stateful EMA/MACD history different from a tail-only restart.
    values = 80 + 0.12 * i + 6 * np.sin(i / 6.3) + 2 * np.cos(i / 3.7)
    return pd.DataFrame({'AAA': values}, index=dates)


def tiny_model(**kwargs):
    return XGBoostEnsembleModel(
        n_ensemble=2, model_params={'n_estimators': 8, 'n_jobs': 1}, **kwargs
    )


class MLIntegrityTests(unittest.TestCase):
    def test_fitting_labels_finish_before_validation_features(self):
        """Removing the purge must expose future fitting labels to validation."""
        prices = price_fixture()
        model = tiny_model()
        model.train(prices, verbose=False)
        self.assertTrue(model.is_trained)
        self.assertTrue(hasattr(model, 'training_audit'), 'Every actual fit must expose audit records')
        audit = model.training_audit[-1]
        self.assertLess(pd.Timestamp(audit['last_fitting_label_end']),
                        pd.Timestamp(audit['validation_start']))
        self.assertEqual(audit['purged_rows'], 5)
        self.assertEqual(audit['n_train'], 143)
        self.assertEqual(audit['n_validation'], 38)
        self.assertEqual(audit['n_valid_before_split'], 186)
        self.assertEqual(audit['status'], 'trained')
        self.assertLessEqual(pd.Timestamp(audit['last_label_end']), prices.index[-1])

    def test_scaler_uses_only_fitting_features_after_purge(self):
        """Fitting a scaler before purging would retain validation-period rows."""
        prices = price_fixture()
        model = tiny_model()
        model.train(prices, verbose=False)
        self.assertTrue(hasattr(model, 'training_audit'), 'Every actual fit must expose audit records')
        audit = model.training_audit[-1]
        # Hand-counted: rows29..214 give186 valid rows; split148; purge5 =>143.
        fitting_dates = prices.index[29:172]
        original_prefix = XGBoostCoreModel()._compute_features(prices['AAA'])
        wanted = original_prefix.loc[fitting_dates]
        np.testing.assert_allclose(model.scalers['AAA'].mean_, wanted.mean().values,
                                   rtol=1e-12, atol=1e-12)
        self.assertEqual(model.scalers['AAA'].n_samples_seen_, 143)
        self.assertEqual(audit['scaler_n_samples_seen'], 143)
        np.testing.assert_allclose(audit['scaler_mean'], wanted.mean().values,
                                   rtol=1e-12, atol=1e-12)
        self.assertEqual([member['seed'] for member in audit['members']], [42, 43])
        self.assertEqual(audit['members'][0]['parameters']['random_state'], 42)

    def test_empty_fitting_set_after_purge_is_skipped(self):
        """A horizon spanning the entire fitting split must never reach fit()."""
        model = tiny_model(prediction_horizon=500)
        model.train(price_fixture(700), verbose=False)
        self.assertFalse(model.is_trained)
        self.assertEqual(model.training_audit[-1]['status'], 'skipped_empty_purged_split')
        self.assertEqual(model.training_audit[-1]['n_train'], 0)

    def test_prediction_records_member_disagreement_and_native_origin(self):
        """Dropping audit observations would prevent native forecast validation."""
        prices = price_fixture()
        model = tiny_model()
        model.train(prices.iloc[:180], verbose=False)
        prediction = model.predict(prices.iloc[:200])
        self.assertTrue(hasattr(model, 'prediction_audit'), 'Every forecast must expose audit records')
        observation = model.prediction_audit[-1]
        member_values = np.asarray(observation['member_predictions'])
        self.assertEqual(pd.Timestamp(observation['feature_date']), prices.index[199])
        self.assertEqual(pd.Timestamp(observation['label_start']), prices.index[199])
        self.assertEqual(observation['prediction_horizon'], 5)
        self.assertAlmostEqual(observation['prediction_mean'], member_values.mean())
        self.assertAlmostEqual(observation['prediction_std'], member_values.std())
        self.assertEqual(prediction['AAA'],
                         (observation['prediction_mean'], observation['confidence']))
        self.assertEqual(len(observation['members']), 2)
        self.assertEqual(observation['training_event_id'], model.training_audit[-1]['training_event_id'])

    def test_ranking_absolute_passes_full_prefix_with_existing_one_row_lag(self):
        """Reintroducing tail30 changes the EMA feature at the same timestamp."""
        prices = price_fixture()
        model = tiny_model()
        model.train(prices.iloc[:175], verbose=False)
        returns = prices.pct_change().dropna()
        generate_ranking_abs_mode_views(200, model, ['AAA'], prices,
                                        ['AAA'], returns)
        self.assertTrue(hasattr(model, 'prediction_audit'), 'Every forecast must expose audit records')
        observed = model.prediction_audit[-1]
        wanted = XGBoostCoreModel()._compute_features(prices['AAA'].iloc[:200]).iloc[-1]
        self.assertEqual(pd.Timestamp(observed['feature_date']), prices.index[199])
        np.testing.assert_allclose(observed['feature_values'], wanted.values,
                                   rtol=1e-12, atol=1e-12)

    def test_all_eight_features_match_original_expanding_prefixes(self):
        """Vectorization must preserve original feature formulas at each prefix."""
        i = np.arange(185, dtype=float)
        scenarios = [price_fixture(185)['AAA'],
                     pd.Series(np.full(185, 100.0), index=price_fixture(185).index),
                     pd.Series(50 + i * 0.13, index=price_fixture(185).index)]
        legacy = XGBoostCoreModel()
        model = tiny_model()
        for prices in scenarios:
            for end in [30, 31, 60, 121, 185]:
                with self.subTest(scenario=float(prices.iloc[-1]), end=end):
                    expected = legacy._compute_features(prices.iloc[:end])
                    actual = model._compute_features(prices.iloc[:end])
                    self.assertEqual(list(actual.columns), list(expected.columns))
                    self.assertEqual(len(actual.columns), 8)
                    pd.testing.assert_index_equal(actual.index, expected.index)
                    np.testing.assert_allclose(actual.values, expected.values,
                                               rtol=1e-11, atol=1e-12, equal_nan=True)

    def test_future_price_perturbation_cannot_change_prefix_features(self):
        """Any future/centered feature alignment must fail this causal check."""
        prices = price_fixture(250)['AAA']
        altered = prices.copy()
        altered.iloc[180:] = np.linspace(1e3, 1e6, 70)
        model = tiny_model()
        before = model._compute_features(prices.iloc[:180])
        after = model._compute_features(altered).loc[before.index]
        np.testing.assert_array_equal(before.values, after.values)

    def test_all_eight_features_match_original_on_current_equity_history(self):
        """Real price scale/history must not expose vectorization arithmetic drift."""
        repository = Path(__file__).resolve().parents[2]
        raw = pd.read_csv(repository / 'datasets/stocks/full/ACB.csv')
        prices = pd.Series(raw['close'].astype(float).values,
                           index=pd.to_datetime(raw['date']))
        legacy, model = XGBoostCoreModel(), tiny_model()
        for end in [30, 121, 500, len(prices)]:
            with self.subTest(end=end):
                expected = legacy._compute_features(prices.iloc[:end])
                actual = model._compute_features(prices.iloc[:end])
                np.testing.assert_allclose(actual.values, expected.values,
                                           rtol=1e-11, atol=1e-12, equal_nan=True)

    def test_fixed_seed_fits_reproduce_predictions_and_audits_accumulate(self):
        """Seed drift or audit reset on retrain must be detectable."""
        prices = price_fixture()
        first, second = tiny_model(), tiny_model()
        first.train(prices.iloc[:180], verbose=False)
        second.train(prices.iloc[:180], verbose=False)
        self.assertEqual(first.predict(prices), second.predict(prices))
        first.train(prices.iloc[:200], verbose=False)
        first.predict(prices)
        self.assertTrue(hasattr(first, 'training_audit'), 'Training audit must survive retraining')
        self.assertEqual(len(first.training_audit), 2)
        self.assertEqual(len(first.prediction_audit), 2)


if __name__ == '__main__':
    unittest.main()
