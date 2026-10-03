"""The measures workflow through the real web pages, end to end."""
import unittest
from datetime import date
from unittest import mock

from openpms import db, mail, measures_service

from .helpers import ADMIN, AppCase, VIEWER

UPDATER = "nadia.hassan@example.org"
APPROVER = "jordan.hughes@example.org"
KEY = "PM-0020|FY-2025-26"   # yes/no measure, not started, target 1
PAGE = f"/measures/value?key={KEY}"


class Lifecycle(AppCase, unittest.TestCase):
    def as_(self, email):
        self.client = self.app.test_client()
        self.login(email=email)

    def act(self, action, **fields):
        return self.post("/measures/value", dict(key=KEY, action=action, **fields), csrf_from=PAGE)

    def sub(self):
        return self.repo().get("submissions", KEY)

    def test_full_lifecycle(self):
        mail.SENT.clear()
        self.as_(UPDATER)
        r = self.act("submit", value_yes_no="no", narrative="", data_quality="verified")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Narrative is required when the value is off track.", r.get_data(as_text=True))
        self.assertEqual(self.sub()["status"], "not_started", "nothing saved when validation fails")

        self.act("save_draft", value_yes_no="no", narrative="Payroll delay", data_quality="provisional")
        self.act("save_draft", value_yes_no="no", narrative="Payroll delay, now fixed", data_quality="provisional")
        self.assertEqual(self.sub()["current_version"], 1, "drafts are edited in place")
        self.act("submit", value_yes_no="no", narrative="Payroll delay, now fixed", data_quality="verified")
        self.assertEqual(self.sub()["status"], "submitted")
        self.assertIn(APPROVER, [m["To"] for m in mail.SENT], "approver told")

        r = self.act("save_draft", value_yes_no="yes", narrative="x", data_quality="verified")
        self.assertEqual(r.status_code, 403, "locked once submitted")

        self.as_(APPROVER)
        r = self.act("return", comment="")
        self.assertIn("A comment is required", r.get_data(as_text=True))
        self.act("return", comment="Please confirm the publication date.")
        self.assertEqual(self.sub()["status"], "returned")
        self.assertIn(UPDATER, [m["To"] for m in mail.SENT if "Returned" in m["Subject"]])

        self.as_(UPDATER)
        self.act("submit", value_yes_no="yes", narrative="Published on time.", data_quality="verified")
        self.assertEqual(self.sub()["current_version"], 2, "a resubmission is a new version")
        page = self.client.get(PAGE).get_data(as_text=True)
        self.assertIn("Changed since version 1:</strong> value (No to Yes), narrative", page)

        self.as_(APPROVER)
        self.act("approve", comment="")
        s = self.sub()
        self.assertEqual((s["status"], s["approved_version"], s["approved_by"]), ("approved", 2, APPROVER))
        repo = self.repo()
        self.assertEqual(repo.get("submission_versions", f"{KEY}|v2")["rag_status"], "green")
        rpt = repo.get("rpt_values", KEY)
        self.assertEqual((rpt["value_number"], rpt["version_no"], rpt["is_latest"]), (1, 2, True))
        self.assertTrue(all(c["resolved"] for c in repo.by("review_comments", submission_key=KEY)))

        self.as_(APPROVER)
        self.assertEqual(self.act("reopen", comment="x").status_code, 403, "only admins reopen")
        self.as_(ADMIN)
        self.act("reopen", comment="Publication date was wrong.")
        self.assertEqual(self.sub()["status"], "draft")
        self.assertEqual(self.repo().get("rpt_values", KEY)["version_no"], 2, "reports keep the approved value")

        self.as_(UPDATER)
        self.act("submit", value_yes_no="yes", narrative="Published on the 3rd.", data_quality="verified")
        self.as_(APPROVER)
        self.act("approve")
        repo = self.repo()
        statuses = [v["version_status"] for v in sorted(repo.by("submission_versions", submission_key=KEY),
                                                        key=lambda v: v["version_no"])]
        self.assertEqual(statuses, ["returned", "superseded", "approved"])
        self.assertEqual(repo.get("rpt_values", KEY)["version_no"], 3)
        changes = [(a["old_value"], a["new_value"]) for a in
                   repo.find("audit_log", "item_key = ? AND field_name = 'status'", (KEY,), order="id")]
        self.assertEqual(changes[0], ("not_started", "draft"))
        self.assertEqual(changes[-1], ("submitted", "approved"))

    def test_approver_cannot_approve_own_entry(self):
        conn = self.conn()
        db.Repo(conn, 1).insert("measure_roles", dict(role_key=f"PM-0020|{APPROVER}|updater", measure_code="PM-0020",
                                                     email=APPROVER, role="updater", active=True), "t")
        conn.close()
        self.as_(APPROVER)
        self.act("submit", value_yes_no="yes", narrative="", data_quality="verified")
        page = self.client.get(PAGE).get_data(as_text=True)
        self.assertIn("another approver needs to review it", page)
        self.assertEqual(self.act("approve").status_code, 403)

    def test_viewer_and_strangers_cannot_act(self):
        for who in (VIEWER, "priya.shah@example.org"):
            self.as_(who)
            self.assertEqual(self.act("save_draft", value_yes_no="yes").status_code, 403, who)
            self.assertNotIn('value="submit"', self.client.get(PAGE).get_data(as_text=True))

    def test_bad_number_rejected(self):
        self.as_("ellie.brooks@example.org")
        key = "PM-0007|M-2026-08"   # returned to Ellie in the demo data
        r = self.post("/measures/value", dict(key=key, action="save_draft", value_number="lots",
                                              data_quality="verified"), csrf_from=f"/measures/value?key={key}")
        self.assertIn("Enter a number", r.get_data(as_text=True))

    def test_failed_save_leaves_nothing_behind(self):
        self.as_(UPDATER)
        real = db.Repo.insert

        def boom(repo, table, *a, **k):
            if table == "audit_log":
                raise RuntimeError("disk full")
            return real(repo, table, *a, **k)
        with mock.patch.object(db.Repo, "insert", boom):
            with self.assertRaises(RuntimeError):
                self.act("save_draft", value_yes_no="yes", narrative="x", data_quality="verified")
        self.assertEqual(self.sub()["status"], "not_started")
        self.assertEqual(self.repo().by("submission_versions", submission_key=KEY), [])


class Lists(AppCase, unittest.TestCase):
    def test_work_lists(self):
        self.login(email=UPDATER)
        html = self.client.get("/measures/?tab=update").get_data(as_text=True)
        self.assertIn("Gender pay gap report published on time", html)
        self.assertIn("Expected, not received", html)
        self.client = self.app.test_client()
        self.login(email=ADMIN)
        html = self.client.get("/measures/?tab=review").get_data(as_text=True)
        self.assertIn("Residents supported into work", html)
        self.assertIn("Awaiting your review", html)

    def test_all_measures_shows_latest_value_in_words(self):
        self.login(email=UPDATER)
        html = self.client.get("/measures/?tab=all").get_data(as_text=True)
        self.assertRegex(html, r"(Green: on or better than target|Red: off track|Amber: short of target)")


class Targets(AppCase, unittest.TestCase):
    def test_apply_across_a_year(self):
        self.login()
        page = "/measures/targets?measure_code=PM-0002&ref_type=target&from_date=2026-04-01&to_date=2027-03-31"
        r = self.post("/measures/targets", dict(measure_code="PM-0002", ref_type="target", from_date="2026-04-01",
                                                to_date="2027-03-31", ref_value="475", action="apply"), csrf_from=page)
        self.assertEqual(r.status_code, 302)
        rows = [r for r in self.repo().by("reference_values", measure_code="PM-0002", ref_type="target")
                if r["period_key"].startswith(("M-2026-", "M-2027-0"))]
        self.assertEqual({r["ref_value"] for r in rows if r["period_key"] >= "M-2026-04"}, {475})

    def test_tolerance_refused_for_plain_measures(self):
        self.login()
        r = self.post("/measures/targets", dict(measure_code="PM-0004", ref_type="tolerance", from_date="2026-04-01",
                                                to_date="2027-03-31", ref_value="5", action="apply"),
                      csrf_from="/measures/targets")
        self.assertIn("Tolerance only applies to KPIs and OKRs.", r.get_data(as_text=True))

    def test_admin_only(self):
        self.login(email=UPDATER)
        self.assertEqual(self.client.get("/measures/targets").status_code, 403)


class DailyJobs(AppCase, unittest.TestCase):
    def test_expected_submissions_once_a_day(self):
        repo = self.repo()
        made = measures_service.create_expected(repo, date(2026, 10, 1))
        self.assertGreater(made, 0)
        self.assertIsNotNone(repo.get("submissions", "PM-0003|Q-2026-27-Q2"))
        self.assertEqual(measures_service.create_expected(repo, date(2026, 10, 1)), 0, "running again adds nothing")
        self.assertIsNotNone(measures_service.run_daily(repo, date(2026, 10, 5)))
        self.assertIsNone(measures_service.run_daily(repo, date(2026, 10, 5)), "only once a day")

    def test_monday_reminders(self):
        mail.SENT.clear()
        due = measures_service.send_reminders(self.repo(), date(2026, 9, 28), 5)
        self.assertIn(UPDATER, due)
        msg = next(m for m in mail.SENT if m["To"] == UPDATER)
        self.assertIn("Gender pay gap report published on time", msg.get_content())

    def test_runs_from_first_request(self):
        self.app.config["DISABLE_DAILY_JOBS"] = False
        self.login(email=UPDATER)
        self.client.get("/")
        marker = self.conn().execute("SELECT value FROM meta WHERE key = 'daily_jobs_1'").fetchone()
        self.assertEqual(marker[0], date.today().isoformat())


if __name__ == "__main__":
    unittest.main()
