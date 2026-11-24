import json
import unittest

import numpy as np
import pandas as pd

from phase2_gold_k5.forecast import build_panel, calibration, check_ledger, training_origins, walk_forward


class ForecastTimingTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range('2020-01-01', periods=180)
        self.names = list('ABCDEF') + ['GOLD', 'VFF']
        i = np.arange(len(self.dates))[:, None]
        j = np.arange(len(self.names))[None, :] + 1
        self.prices = pd.DataFrame(100 * np.exp(.001 * i * j + .013 * np.sin(i / j)),
                                   index=self.dates, columns=self.names)
        self.history = pd.DataFrame(dict(
            experiment_id=['A3_ProposedK5'] * 2, selection_date=self.dates[[20, 150]],
            history_end=self.dates[[19, 149]], selected_assets=[json.dumps(list(s)) for s in ('ABCDE', 'BCDEF')]))
        self.split = self.dates[85]
        self.settings = dict(anchor_index=145, frequency=10, minimum_rows=100, seeds=[17,41],
                             n_estimators=3, max_depth=2, learning_rate=.05, subsample=.85, n_jobs=1)

    def panel(self, eligible=None, valuation=None):
        return build_panel(self.prices if eligible is None else eligible,
                           self.prices if valuation is None else valuation, self.history, self.split)

    def test_fixed_membership_and_horizon_across_reselection(self):
        align, members, features, targets = self.panel()
        self.assertEqual(members[148], tuple('ABCDE'))
        self.assertEqual(members[150], tuple('BCDEF'))
        self.assertEqual(align.label_start.iloc[148], self.dates[149])
        self.assertEqual(align.label_end.iloc[148], self.dates[154])
        expected = self.prices.iloc[154] / self.prices.iloc[149] - 1
        self.assertAlmostEqual(targets.direct.iloc[148], expected.GOLD - expected.loc[list('ABCDE')].mean())
        window = self.prices.iloc[130:151].loc[:,list('BCDEF')]
        units = 1 / (5 * window.iloc[0])
        self.assertAlmostEqual(features['direct'][150,5], (window @ units).pct_change().std())
        self.assertTrue(targets.iloc[-6:].isna().all().all())

    def test_gold_due_next_day_and_boundaries_purged(self):
        align, _, _, _ = self.panel()
        x = training_origins(align, 145)
        self.assertEqual(x[-1], 138)
        self.assertNotIn(139, x)  # Exit date is today; the GOLD close is still unpublished.
        self.assertEqual(align.label_end.iloc[139], self.dates[145])
        self.assertLess(align.cutoff_at.iloc[145], align.label_available_at.iloc[139])
        self.assertTrue(align.label_available_at.iloc[x].le(align.cutoff_at.iloc[145]).all())
        self.assertFalse(align.crosses_split.iloc[x].any())

    def test_forecasts_invariant_to_future_features_labels_and_current_gold_outcome(self):
        idx = np.arange(20, 161, 5)
        calendar = pd.DataFrame(dict(decision_index=idx, decision_date=self.dates[idx],
                                     assumed_execution_date=self.dates[idx+1],
                                     selection_state_id=self.dates[np.where(idx < 150, 20, 150)]))
        original, seeds, _ = walk_forward(*self.panel(), calendar, self.settings)
        eligible, valuation = self.prices.copy(), self.prices.copy()
        eligible.iloc[151:] *= 4
        valuation.iloc[150:, valuation.columns.get_loc('GOLD')] *= 3
        valuation.iloc[151:] *= 2
        altered, _, _ = walk_forward(*self.panel(eligible, valuation), calendar, self.settings)
        cols = ['prediction','q_daily','calibration_n','confidence','fit_date']
        pd.testing.assert_frame_equal(original.loc[original.date <= self.dates[150],cols],
                                      altered.loc[altered.date <= self.dates[150],cols])
        at_change = original[original.date == self.dates[150]].set_index('view')
        raw = seeds.loc[seeds.date.eq(self.dates[150])].groupby('model').prediction.mean()
        self.assertAlmostEqual(at_change.at['derived','prediction'], raw.GOLD - raw.loc[list('BCDEF')].mean())
        self.assertEqual(at_change.at['derived','fit_date'], self.dates[145])
        self.assertTrue(original.loc[original.date < self.dates[145],'prediction'].isna().all())
        self.assertTrue(original.q_daily.isna().all())

    def test_calibration_uses_only_mature_out_of_sample_rows(self):
        cutoff = pd.Timestamp('2020-05-18', tz='UTC')
        history = [dict(date=i, actual=float(i), prediction=float(i) + 1, crosses_split=False,
                        label_available_at=cutoff - pd.Timedelta(days=20-i)) for i in range(20)]
        excluded = [history[0] | {'prediction':np.nan}, history[0] | {'crosses_split':True},
                    history[0] | {'label_available_at':cutoff + pd.Timedelta(seconds=1)}]
        self.assertTrue(np.isnan(calibration(history[:19] + excluded, cutoff)['confidence']))
        audit = calibration(history + excluded, cutoff)
        self.assertEqual(audit['calibration_n'], 20)
        self.assertAlmostEqual(audit['calibration_mse_daily'], .04)
        self.assertAlmostEqual(audit['calibration_variance_daily'], np.var(np.arange(20) / 5))
        self.assertEqual(audit['confidence'], .9)

    def test_ledger_rejects_post_cutoff_observations(self):
        day = self.dates[0]
        dt = day.tz_localize('Asia/Ho_Chi_Minh')
        data = pd.DataFrame(dict(session_date=[day], asset=['GOLD'], price=[10.],
                                 observed_at=[dt], available_at=[dt], decision_at=[dt + pd.Timedelta(hours=18)]))
        check_ledger(pd.DataFrame({'GOLD':[10.]},index=[day]), data)
        data.loc[0,'available_at'] += pd.Timedelta(days=1)
        with self.assertRaises(ValueError):
            check_ledger(pd.DataFrame({'GOLD':[10.]},index=[day]), data)


if __name__ == '__main__':
    unittest.main()
