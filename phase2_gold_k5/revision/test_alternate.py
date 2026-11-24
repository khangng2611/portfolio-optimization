import unittest

import pandas as pd

from phase2_gold_k5.revision.alternate import compose


class SourcePriorityTests(unittest.TestCase):
    def test_forward_mark_stays_untradable_until_new_evidence(self):
        dates = pd.date_range("2024-12-25", periods=7).strftime("%Y-%m-%d")
        gia = pd.DataFrame(dict(date=dates, archive_bid=[10, 10, 10, 10, 13, 13, 13],
                                archive_ask=[12, 12, 12, 12, 14, 14, 14], source_file="12.html",
                                source_url="archive", provider_carry_flag=[False, True, True, False, False, True, True]))
        news = pd.DataFrame([dict(date=dates[1], bid=11, ask=13, evidence="explicit_bullion_close",
                                  news_url="https://example.org/story-123.html", webgia_url="dated",
                                  webgia_time_ict=dates[1], news_published_ict=dates[2],
                                  news_quote_time_ict="")]).set_index("date")
        igold = pd.DataFrame([dict(date=dates[-1], bid=12, ask=14, source_url="iGold export")]).set_index("date")
        rows = compose(gia, news, igold)
        self.assertEqual(rows.archive_ask.tolist(), [12, 13, 13, 13, 14, 14, 14])
        self.assertEqual(rows.reference_age_days.tolist(), [0, 0, 1, 2, 0, 0, 0])
        self.assertEqual(rows.source_file.iloc[3], rows.source_file.iloc[1])
        self.assertEqual(rows.reference_date.iloc[3], dates[1])
        self.assertEqual(rows.primary_fill_allowed.tolist(), [True, True, False, False, True, False, False])
        self.assertEqual(rows.permissive_fill_allowed.tolist(), [True, True, False, False, True, True, True])
        self.assertEqual(rows.source.iloc[-1], "iGold")
        vetoed = compose(gia, news, igold, {dates[4]})
        self.assertEqual(vetoed.reference_date.iloc[4], dates[1])
        self.assertFalse(vetoed.permissive_fill_allowed.iloc[4])
        self.assertFalse(vetoed.primary_fill_allowed.iloc[4])
        self.assertFalse(vetoed.permissive_fill_allowed.iloc[5])


if __name__ == "__main__":
    unittest.main()
