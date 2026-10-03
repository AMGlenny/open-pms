"""Weekly pages: saving your week, carry-over tasks, problems and the
wellbeing privacy rules, through the real web pages."""
import unittest
from datetime import date

from .helpers import AppCase, VIEWER

MANAGER = "jordan.hughes@example.org"    # line manager of Team A members
MEMBER = "priya.shah@example.org"         # in Team A, reports to Jordan
WEEK = "2026-09-21"
TEAM = "ST-SDS-A"


class MyWeekTests(AppCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.login(email=MEMBER)

    def page(self, week=WEEK):
        return f"/week?week={week}&team={TEAM}"

    def save(self, **fields):
        data = dict(week=WEEK, team=TEAM, successes="", communication="", workload="", wellbeing="",
                    wellbeing_comments="")
        data.update(fields)
        return self.post("/week", data, csrf_from=self.page())

    def test_open_tasks_carry_over(self):
        html = self.client.get(self.page("2026-11-02")).get_data(as_text=True)
        self.assertIn("Explore linking the portal to Fabric", html, "raised in August, still open in November")
        self.assertNotIn("Confirm baseline figures", html, "completed weeks ago, so no longer shown")

    def test_save_creates_one_row_per_week_and_audits_changes(self):
        self.save(successes="Launched the pilot", workload="heavy", wellbeing="ok")
        self.save(successes="Launched the pilot early", workload="heavy", wellbeing="ok")
        repo = self.repo()
        key = f"{MEMBER}|2026-09-21"
        update = repo.get("weekly_updates", key)
        self.assertEqual(update["successes"], "Launched the pilot early")
        self.assertEqual(repo.count("weekly_updates", "email = ? AND week_start = ?", (MEMBER, WEEK)), 1)
        edits = repo.find("audit_log", "item_key = ? AND field_name = 'successes'", (key,))
        self.assertTrue(edits)
        checkin = repo.get("wellbeing_checkins", key)
        self.assertEqual(checkin["line_manager_email"], MANAGER, "line manager recorded on the check-in")

    def test_any_day_moves_to_monday(self):
        self.post("/week", dict(week="2026-09-24", team=TEAM, successes="x"), csrf_from=self.page())
        self.assertIsNotNone(self.repo().get("weekly_updates", f"{MEMBER}|2026-09-21"))

    def test_ticking_and_unticking_tasks(self):
        repo = self.repo()
        self.assertEqual(repo.get("tasks", "TSK-00003")["status"], "open")
        open_codes = [t["task_code"] for t in repo.find("tasks", "org_unit_key = ? AND status = 'open'", (TEAM,))]
        ticks = {f"done_{c}": "1" for c in open_codes if c != "TSK-00003"}
        ticks["done_TSK-00003"] = "1"
        self.save(**ticks)
        t = self.repo().get("tasks", "TSK-00003")
        week_end = date(2026, 9, 27)
        self.assertEqual((t["status"], t["completed_by"], t["completed_date"]), ("complete", MEMBER, min(date.today(), week_end)),
                         "done on the week being reported, not after it")
        self.save()  # nothing ticked: tasks completed this week reopen
        self.assertEqual(self.repo().get("tasks", "TSK-00003")["status"], "open")

    def test_cannot_write_someone_elses_update(self):
        self.post("/week", dict(week=WEEK, team=TEAM, successes="mine", email=MANAGER), csrf_from=self.page())
        repo = self.repo()
        self.assertIsNotNone(repo.get("weekly_updates", f"{MEMBER}|{WEEK}"))
        mgr = repo.get("weekly_updates", f"{MANAGER}|{WEEK}")
        self.assertNotEqual(mgr and mgr["successes"], "mine")

    def test_bad_choice_rejected(self):
        r = self.save(workload="exhausted")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Choose your workload from the list.", r.get_data(as_text=True))


class TaskAndProblemTests(AppCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.login(email=MEMBER)

    def test_new_task_gets_next_code(self):
        r = self.post("/tasks/new", dict(task_name="Write the Q3 summary", priority="must", org_unit_key=TEAM,
                                         contributes_to="measure:PM-0001", status="open", assigned_to=MEMBER))
        self.assertEqual(r.status_code, 302)
        t = self.repo().get("tasks", "TSK-00017")
        self.assertEqual((t["raised_by"], t["contributes_to_type"], t["contributes_to_key"]), (MEMBER, "measure", "PM-0001"))

    def test_task_needs_a_name(self):
        r = self.post("/tasks/new", dict(task_name=" ", priority="must", org_unit_key=TEAM, status="open"))
        self.assertIn("Enter a task name.", r.get_data(as_text=True))

    def test_problem_closing_needs_resolution(self):
        base = dict(problem_title="Feed late", problem_statement="Arrives after the 20th", org_unit_key=TEAM,
                    impact="high", urgency="medium", status="closed")
        r = self.post("/problems/new", base)
        self.assertIn("resolved before closing", r.get_data(as_text=True))
        r = self.post("/problems/new", dict(base, resolution="Agreed a new deadline"))
        self.assertEqual(r.status_code, 302)
        p = self.repo().get("problems", "PRB-00009")
        self.assertEqual((p["status"], p["closed_date"]), ("closed", date.today()))


class ViewerTests(AppCase, unittest.TestCase):
    def test_viewers_can_look_but_not_change(self):
        self.login(email=VIEWER)
        html = self.client.get(f"/week?week={WEEK}&team={TEAM}").get_data(as_text=True)
        self.assertIn("read-only access", html)
        self.assertNotIn("Save my week", html)
        token = self.csrf(f"/week?week={WEEK}&team={TEAM}")
        r = self.client.post("/week", data=dict(csrf_token=token, week=WEEK, team=TEAM, successes="x"))
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/tasks/new", data=dict(csrf_token=token, task_name="x", priority="must",
                                                     org_unit_key=TEAM, status="open"))
        self.assertEqual(r.status_code, 403)


class WellbeingPrivacyTests(AppCase, unittest.TestCase):
    def team_page(self, who):
        self.client = self.app.test_client()
        self.login(email=who)
        return self.client.get(f"/team?week={WEEK}&team={TEAM}").get_data(as_text=True)

    def test_manager_sees_reports_member_sees_totals_only(self):
        repo = self.repo()
        answers = {c["email"]: c["wellbeing"] for c in repo.find("wellbeing_checkins", "week_start = ?", (WEEK,))}
        manager_view = self.team_page(MANAGER)
        self.assertIn("Your direct reports", manager_view)
        self.assertIn("Priya Shah:", manager_view)
        member_view = self.team_page(MEMBER)
        self.assertNotIn("Your direct reports", member_view)
        self.assertNotIn("Priya Shah:", member_view)
        self.assertIn(f"{len([e for e in answers if repo.get('people', e)['org_unit_key'] == TEAM])} answers", member_view)

    def test_totals_hidden_below_threshold(self):
        conn = self.conn()
        conn.execute("UPDATE settings SET setting_value = '50' WHERE setting_key = 'wellbeing_min_group_size'")
        conn.close()
        html = self.team_page(MEMBER)
        self.assertIn("Totals are hidden until at least 50 people", html)
        self.assertNotIn("Thriving ", html)

    def test_threshold_can_never_go_below_three(self):
        conn = self.conn()
        conn.execute("UPDATE settings SET setting_value = '1' WHERE setting_key = 'wellbeing_min_group_size'")
        conn.close()
        self.assertNotIn("at least 1 people", self.team_page(MEMBER))

    def test_admins_have_no_wellbeing_screen(self):
        self.login()
        self.assertEqual(self.client.get("/admin/wellbeing_checkins").status_code, 404)


if __name__ == "__main__":
    unittest.main()
