import unittest

import numpy as np
import pandas as pd

from phase2_gold_k5.audit import align_quotes, parse_month


class GoldEvidenceTests(unittest.TestCase):
    def test_archive_sides_units_and_carry_flag(self):
        html = """Vàng SJC 1L, 10L, 1KG · Hồ Chí Minh
        <div>triệu đồng / lượng</div><table class="gv-table">
        <thead><tr><th>Ngày</th><th>Mua lại</th><th>Bạn trả</th></tr></thead>
        <tbody><tr><td>05/01/2020 Chủ nhật</td><td>41,2</td>
        <td><span class="gv-row__price">41,8</span> không đổi</td></tr></tbody></table>"""
        row, = parse_month(html, "2020_1.html")
        self.assertEqual((row["archive_bid"], row["archive_ask"]), (41200, 41800))
        self.assertTrue(row["provider_carry_flag"])
        with self.assertRaises(ValueError):
            parse_month(html.replace("41,2", "42,9"), "2020_1.html")
        with self.assertRaises(ValueError):
            parse_month(html.replace("Mua lại", "Khác"), "2020_1.html")

    def test_monday_uses_sunday_ledger_and_never_executes_flagged_or_absent_quotes(self):
        dates = pd.to_datetime(["2020-01-05", "2020-01-06"])
        raw = pd.DataFrame(dict(archive_bid=[40., 42.], archive_ask=[41., 43.],
                                provider_carry_flag=[False, True], source_file=["2020_1.html"] * 2),
                           index=dates)
        sessions = pd.to_datetime(["2020-01-06", "2020-01-07"])
        ledger = pd.DataFrame(dict(
            observed_at=pd.to_datetime(dates).tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=23),
            available_at=sessions.tz_localize("Asia/Ho_Chi_Minh"),
            decision_at=sessions.tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=18),
            price=[41., 43.], source=["archive/2020_1.html"] * 2), index=sessions)
        actual = align_quotes(raw, sessions, ledger)
        np.testing.assert_equal(actual.known_bid.to_numpy(), [40., 42.])
        self.assertTrue(actual[["bid", "ask"]].isna().all().all())
        self.assertEqual(actual.execution_status.tolist(), ["flat_or_possible_carry", "archive_row_missing"])
        ledger.iloc[0, ledger.columns.get_loc("available_at")] += pd.Timedelta(days=1)
        with self.assertRaises(ValueError):
            align_quotes(raw, sessions, ledger)
