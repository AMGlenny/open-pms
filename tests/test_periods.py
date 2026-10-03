"""Periods for any financial year start, not just April."""
import unittest
from collections import defaultdict
from datetime import date, timedelta

from openpms import periods


def check_contiguous(test, rows):
    by_type = defaultdict(list)
    for r in rows:
        test.assertLessEqual(r["start_date"], r["end_date"])
        by_type[r["period_type"]].append(r)
    for ptype, rs in by_type.items():
        if ptype == "term":
            continue
        rs.sort(key=lambda r: r["start_date"])
        for a, b in zip(rs, rs[1:]):
            test.assertEqual(a["end_date"] + timedelta(days=1), b["start_date"], ptype)


class PeriodTests(unittest.TestCase):
    def test_uk_april_default(self):
        rows = {r["period_key"]: r for r in periods.generate(2026, 2026)}
        self.assertEqual(rows["Q-2026-27-Q1"]["start_date"], date(2026, 4, 1))
        self.assertEqual(rows["FY-2026-27"]["end_date"], date(2027, 3, 31))
        self.assertEqual(rows["M-2027-02"]["financial_quarter"], "2026-27 Q4")

    def test_calendar_financial_year(self):
        rows = {r["period_key"]: r for r in periods.generate(2026, 2026, fy_start_month=1)}
        self.assertEqual(rows["FY-2026"]["start_date"], date(2026, 1, 1))
        self.assertEqual(rows["Q-2026-Q3"]["start_date"], date(2026, 7, 1))
        self.assertEqual(rows["M-2026-12"]["financial_quarter"], "2026 Q4")

    def test_july_financial_year(self):
        rows = {r["period_key"]: r for r in periods.generate(2026, 2026, fy_start_month=7)}
        self.assertEqual(rows["FY-2026-27"]["end_date"], date(2027, 6, 30))
        self.assertEqual(rows["Q-2026-27-Q2"]["start_date"], date(2026, 10, 1))

    def test_no_gaps_or_overlaps(self):
        for month in (1, 4, 7, 10):
            rows = periods.generate(2025, 2027, 2027, fy_start_month=month)
            keys = [r["period_key"] for r in rows]
            self.assertEqual(len(keys), len(set(keys)), month)
            check_contiguous(self, rows)

    def test_weeks_and_fortnights_start_monday(self):
        for r in periods.generate(2026, 2026):
            if r["period_type"] in ("weekly", "fortnightly"):
                self.assertEqual(r["start_date"].weekday(), 0)

    def test_fortnights_continue_across_years(self):
        anchor = date(2025, 4, 7)
        a = [r for r in periods.generate(2025, 2025, fortnight_anchor=anchor) if r["period_type"] == "fortnightly"]
        b = [r for r in periods.generate(2026, 2026, fortnight_anchor=anchor) if r["period_type"] == "fortnightly"]
        self.assertEqual(a[-1]["end_date"] + timedelta(days=1), b[0]["start_date"])

    def test_academic_year_setting(self):
        rows = {r["period_key"]: r for r in periods.generate(2026, 2026, ay_start_month=8)}
        self.assertEqual(rows["AY-2026-27"]["start_date"], date(2026, 8, 1))


if __name__ == "__main__":
    unittest.main()
