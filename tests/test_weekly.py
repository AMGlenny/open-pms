"""Pins down the weekly-work rules the app and wellbeing flow must follow."""
import unittest
from datetime import date

from openpms import rules, seed_data as seed

DATA = seed.build()
WEEK = date(2026, 9, 21)


class WeekStartTests(unittest.TestCase):
    def test_monday(self):
        self.assertEqual(rules.week_start(date(2026, 9, 30)), date(2026, 9, 28))  # Wednesday
        self.assertEqual(rules.week_start(date(2026, 9, 28)), date(2026, 9, 28))  # Monday
        self.assertEqual(rules.week_start(date(2026, 10, 4)), date(2026, 9, 28))  # Sunday


class CarryForwardTests(unittest.TestCase):
    def test_open_tasks_carry_over_and_closed_ones_drop_off(self):
        shown = rules.tasks_for_week(DATA["tasks"], "ST-SDS-A", WEEK)
        codes = {t["task_code"] for t in shown}
        for t in DATA["tasks"]:
            if t["org_unit_key"] != "ST-SDS-A":
                self.assertNotIn(t["task_code"], codes)
            elif t["status"] == "open":
                self.assertIn(t["task_code"], codes, "open tasks always carry over")
            elif t["completed_date"] < WEEK:
                self.assertNotIn(t["task_code"], codes, "tasks closed in earlier weeks drop off")
        self.assertEqual(shown[0]["status"], "open")

    def test_completed_this_week_is_shown(self):
        task = dict(DATA["tasks"][1], status="complete", completed_date=date(2026, 9, 23))
        shown = rules.tasks_for_week([task], task["org_unit_key"], WEEK)
        self.assertEqual(len(shown), 1)

    def test_open_problems_carry_over(self):
        shown = rules.problems_for_week(DATA["problems"], "ST-SDS-A", WEEK)
        self.assertTrue(all(p["org_unit_key"] == "ST-SDS-A" for p in shown))
        self.assertTrue(any(p["status"] == "open" for p in shown))


def checkin(email, manager, org, wellbeing="ok"):
    return dict(email=email, line_manager_email=manager, org_unit_key=org, week_start=WEEK,
                wellbeing=wellbeing, comments=None)


class WellbeingViewTests(unittest.TestCase):
    rows = [checkin(f"p{i}@x", "boss@x" if i < 2 else "other@x", "T1", "struggling" if i == 0 else "ok")
            for i in range(5)]

    def test_manager_sees_only_their_reports(self):
        v = rules.wellbeing_view(self.rows, "boss@x", "T1", WEEK, 5)
        self.assertEqual([r["email"] for r in v["direct_reports"]], ["p0@x", "p1@x"])
        self.assertEqual(v["direct_reports"][0]["wellbeing"], "struggling")

    def test_non_manager_sees_no_individuals(self):
        v = rules.wellbeing_view(self.rows, "p3@x", "T1", WEEK, 5)
        self.assertEqual(v["direct_reports"], [])

    def test_counts_only_at_threshold(self):
        v = rules.wellbeing_view(self.rows, "p3@x", "T1", WEEK, 5)
        self.assertTrue(v["show_counts"])
        self.assertEqual(v["counts"], {"thriving": 0, "ok": 4, "struggling": 1})
        v = rules.wellbeing_view(self.rows[:4], "p3@x", "T1", WEEK, 5)
        self.assertFalse(v["show_counts"])
        self.assertIsNone(v["counts"])
        self.assertEqual(v["responses"], 4)

    def test_other_weeks_and_teams_ignored(self):
        other = [dict(r, week_start=date(2026, 9, 14)) for r in self.rows] + \
                [dict(r, org_unit_key="T2") for r in self.rows]
        v = rules.wellbeing_view(other, "boss@x", "T1", WEEK, 5)
        self.assertEqual(v["responses"], 0)
        self.assertEqual(len(v["direct_reports"]), 2, "reports in another team still go to their manager")

    def test_seed_managers(self):
        v = rules.wellbeing_view(DATA["wellbeing_checkins"], "jordan.hughes@example.org", "ST-SDS-A", WEEK, 5)
        self.assertTrue(v["direct_reports"])
        people = {p["email"]: p for p in DATA["people"]}
        for r in v["direct_reports"]:
            self.assertEqual(people[r["email"]]["line_manager_email"], "jordan.hughes@example.org")


class ValidationTests(unittest.TestCase):
    def test_task(self):
        self.assertEqual(rules.validate_task({"task_name": "Do it"}), [])
        self.assertTrue(rules.validate_task({"task_name": "  "}))
        self.assertTrue(rules.validate_task({"task_name": "x" * 256}))
        self.assertTrue(rules.validate_task({"task_name": "Do it", "contributes_to_type": "group"}))

    def test_problem(self):
        ok = {"problem_title": "T", "problem_statement": "S", "status": "open"}
        self.assertEqual(rules.validate_problem(ok), [])
        self.assertTrue(rules.validate_problem(dict(ok, status="closed")))
        self.assertEqual(rules.validate_problem(dict(ok, status="closed", resolution="Fixed")), [])

    def test_seed_passes(self):
        for t in DATA["tasks"]:
            self.assertEqual(rules.validate_task(t), [], t["task_code"])
        for p in DATA["problems"]:
            self.assertEqual(rules.validate_problem(p), [], p["problem_code"])


if __name__ == "__main__":
    unittest.main()
