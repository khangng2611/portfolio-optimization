"""End-to-end control replay of the archived study before changing its GOLD vintage."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from phase2_gold_k5.revision.rebuild import ARMS, FROZEN, READY, ROOT, prepare


class FrozenControl(unittest.TestCase):
    def test_original_vintage_reproduces_complete_input_panels_and_both_arms(self):
        with TemporaryDirectory() as directory:
            out = Path(directory)
            prepare(out, READY / "gold_archive_daily.csv")
            names = ["prices_valuation", "prices_eligible", "availability_ledger"]
            names += [f"{arm}_{table}" for arm in ARMS for table in ("posterior_audit", "weights")]
            for name in names:
                with self.subTest(table=name):
                    actual = pd.read_csv(out / "inputs" / f"{name}.csv", float_precision="round_trip")
                    expected = pd.read_csv(FROZEN / f"{name}.csv", float_precision="round_trip")
                    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
            expected_quotes = ROOT / "phase2_gold_k5/runs/20261124T083539735869Z/gold_quotes.csv"
            pd.testing.assert_frame_equal(pd.read_csv(out / "gold_quotes.csv"), pd.read_csv(expected_quotes),
                                          check_exact=True)
            diag = pd.read_csv(out / "b2_regime_confidence.csv")
            self.assertEqual(len(diag), 310)
            self.assertTrue(diag.regime.eq(diag.frozen_regime).all())
            self.assertTrue(diag.max_abs_confidence_change.eq(0).all())


if __name__ == "__main__":
    unittest.main()
