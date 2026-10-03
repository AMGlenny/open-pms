"""Walks values through the full approval lifecycle, and checks every rule
the flows must enforce."""
import copy
import unittest
from datetime import date, datetime, timedelta, timezone

from openpms import seed_data as seed, workflow
from openpms.workflow import Invalid, NotAllowed

BASE = seed.build()
UPDATER = "nadia.hassan@example.org"
APPROVER = "jordan.hughes@example.org"
ADMIN = "sam.patel@example.org"
OTHER = "priya.shah@example.org"
KEY = "PM-0020|FY-2025-26"  # yes/no measure, not started, target 1


def t(minutes):
    return datetime(2026, 10, 1, 9, tzinfo=timezone.utc) + timedelta(minutes=minutes)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.s = copy.deepcopy(BASE)

    def sub(self, key=KEY):
        return next(x for x in self.s["submissions"] if x["submission_key"] == key)

    def versions(self, key=KEY):
        return sorted((v for v in self.s["submission_versions"] if v["submission_key"] == key),
                      key=lambda v: v["version_no"])

    def rpt(self, key=KEY):
        return [r for r in self.s["rpt_values"] if r["submission_key"] == key]

    def test_full_lifecycle(self):
        s = self.s
        self.assertEqual(workflow.allowed_actions(s, KEY, UPDATER), {"save_draft", "submit"})
        self.assertEqual(workflow.allowed_actions(s, KEY, APPROVER), set())

        # Draft is created, then edited in place.
        workflow.save_value(s, KEY, UPDATER, t(0), submit=False, value_number=1)
        workflow.save_value(s, KEY, UPDATER, t(1), submit=False, value_number=0, narrative="Report delayed by payroll.")
        self.assertEqual([v["version_no"] for v in self.versions()], [1])
        self.assertEqual(self.sub()["status"], "draft")

        # Submit, then the approver returns it with a comment.
        workflow.save_value(s, KEY, UPDATER, t(2), submit=True, value_number=0, narrative="Report delayed by payroll.")
        self.assertEqual(workflow.allowed_actions(s, KEY, APPROVER), {"approve", "return"})
        emails = workflow.return_for_changes(s, KEY, APPROVER, t(3), "Please confirm the publication date.")
        self.assertEqual(emails, [UPDATER])
        self.assertEqual(self.sub()["status"], "returned")
        self.assertEqual(self.versions()[0]["version_status"], "returned")

        # Resubmission is a new version; the old one is kept for comparison.
        workflow.save_value(s, KEY, UPDATER, t(4), submit=True, value_number=1, narrative="Published on time.")
        vs = self.versions()
        self.assertEqual([(v["version_no"], v["version_status"]) for v in vs], [(1, "returned"), (2, "submitted")])
        self.assertEqual(vs[0]["value_number"], 0)

        # Approve: RAG stored, comments resolved, reporting row created as latest.
        workflow.approve(s, KEY, APPROVER, t(5))
        self.assertEqual(self.sub()["status"], "approved")
        self.assertEqual(self.sub()["approved_version"], 2)
        self.assertEqual(self.versions()[1]["rag_status"], "green")
        comments = [c for c in s["review_comments"] if c["submission_key"] == KEY]
        self.assertTrue(all(c["resolved"] for c in comments))
        row, = self.rpt()
        self.assertEqual((row["version_no"], row["value_number"], row["is_latest"]), (2, 1, True))
        self.assertEqual(row["target_value"], 1)

        # Admin reopens; approved value stays in reports until re-approved.
        self.assertIn("reopen", workflow.allowed_actions(s, KEY, ADMIN))
        workflow.reopen(s, KEY, ADMIN, t(6), "Date was wrong.")
        self.assertEqual(self.sub()["status"], "draft")
        self.assertEqual(self.rpt()[0]["version_no"], 2)
        workflow.save_value(s, KEY, UPDATER, t(7), submit=True, value_number=1, narrative="Published on the 3rd.")
        self.assertEqual(self.sub()["current_version"], 3, "first save after reopen makes a new version")
        workflow.approve(s, KEY, APPROVER, t(8))
        statuses = [v["version_status"] for v in self.versions()]
        self.assertEqual(statuses, ["returned", "superseded", "approved"])
        self.assertEqual(len(self.rpt()), 1)
        self.assertEqual(self.rpt()[0]["version_no"], 3)

        # Every status change is in the audit log.
        changes = [(a["old_value"], a["new_value"]) for a in s["audit_log"]
                   if a["item_key"] == KEY and a["field_name"] == "status"]
        self.assertEqual(changes, [("not_started", "draft"), ("draft", "submitted"), ("submitted", "returned"),
                                   ("returned", "submitted"), ("submitted", "approved"), ("approved", "draft"),
                                   ("draft", "submitted"), ("submitted", "approved")])
        reopen_audit = [a for a in s["audit_log"] if a["item_key"] == KEY and a["action"] == "reopen"]
        self.assertEqual(len(reopen_audit), 1)

    def test_edits_are_audited_with_old_and_new(self):
        workflow.save_value(self.s, KEY, UPDATER, t(0), submit=False, value_number=1)
        workflow.save_value(self.s, KEY, UPDATER, t(1), submit=False, value_number=0, narrative="x")
        edit = [a for a in self.s["audit_log"] if a["item_key"] == f"{KEY}|v1" and a["field_name"] == "value_number"]
        self.assertEqual((edit[-1]["old_value"], edit[-1]["new_value"]), ("1", "0"))

    def test_permissions(self):
        s = self.s
        with self.assertRaises(NotAllowed):
            workflow.save_value(s, KEY, OTHER, t(0), submit=False, value_number=1)
        with self.assertRaises(NotAllowed):
            workflow.approve(s, KEY, APPROVER, t(0))  # nothing submitted yet
        workflow.save_value(s, KEY, UPDATER, t(0), submit=True, value_number=1)
        with self.assertRaises(NotAllowed):
            workflow.save_value(s, KEY, UPDATER, t(1), submit=False, value_number=0)  # locked once submitted
        with self.assertRaises(NotAllowed):
            workflow.approve(s, KEY, UPDATER, t(1))
        with self.assertRaises(NotAllowed):
            workflow.reopen(s, KEY, ADMIN, t(1), "x")  # only approved values reopen
        workflow.approve(s, KEY, APPROVER, t(2))
        with self.assertRaises(NotAllowed):
            workflow.reopen(s, KEY, APPROVER, t(3), "x")  # admins only
        with self.assertRaises(NotAllowed):
            workflow.save_value(s, KEY, UPDATER, t(3), submit=False, value_number=0)  # approved is locked

    def test_approver_cannot_approve_own_entry(self):
        s = self.s
        s["measure_roles"].append(dict(role_key=f"PM-0020|{APPROVER}|updater", measure_code="PM-0020",
                                       email=APPROVER, role="updater", active=True, start_date=None, end_date=None))
        workflow.save_value(s, KEY, APPROVER, t(0), submit=True, value_number=1)
        self.assertEqual(workflow.allowed_actions(s, KEY, APPROVER), set())

    def test_validation(self):
        s = self.s
        with self.assertRaises(Invalid):
            workflow.save_value(s, KEY, UPDATER, t(0), submit=True, value_missing=True)  # no narrative
        with self.assertRaises(Invalid):
            workflow.save_value(s, KEY, UPDATER, t(0), submit=True, value_number=0)  # red, no narrative
        with self.assertRaises(Invalid):
            workflow.save_value(s, KEY, UPDATER, t(0), submit=True, value_number=2, narrative="x")  # not yes/no
        # Drafts can be saved incomplete.
        workflow.save_value(s, KEY, UPDATER, t(0), submit=False, value_missing=True)
        workflow.save_value(s, KEY, UPDATER, t(1), submit=True, value_number=1)
        with self.assertRaises(Invalid):
            workflow.return_for_changes(s, KEY, APPROVER, t(2), "  ")

    def test_older_period_does_not_take_latest(self):
        s = self.s
        # PM-0010 has a newer approved fortnight than its first one.
        key = next(x["submission_key"] for x in s["submissions"] if x["measure_code"] == "PM-0010")
        sub = self.sub(key)
        workflow.reopen(s, key, ADMIN, t(0), "Recheck")
        workflow.save_value(s, key, "rhys.evans@example.org", t(1), submit=True, value_number=90.0)
        workflow.approve(s, key, "sam.patel@example.org", t(2))
        self.assertEqual(sub["approved_version"], 2)
        self.assertFalse(self.rpt(key)[0]["is_latest"])
        latest = [r for r in s["rpt_values"] if r["measure_code"] == "PM-0010" and r["is_latest"]]
        self.assertEqual(len(latest), 1)


class ScheduledJobTests(unittest.TestCase):
    def test_expected_submissions(self):
        s = copy.deepcopy(BASE)
        new = workflow.expected_submissions(s, date(2026, 10, 1))
        keys = {n["submission_key"] for n in new}
        self.assertIn("PM-0003|Q-2026-27-Q2", keys)  # quarter ended 30 Sep
        self.assertIn("PM-0011|D-2026-09-30", keys)  # daily
        self.assertNotIn("PM-0021|M-2026-09", keys)  # retired
        self.assertTrue(all(n["status"] == "not_started" for n in new))
        q2 = next(n for n in new if n["submission_key"] == "PM-0003|Q-2026-27-Q2")
        self.assertEqual(q2["expected_by"], date(2026, 11, 14))  # 45 day lag
        s["submissions"] += new
        self.assertEqual(workflow.expected_submissions(s, date(2026, 10, 1)), [], "re-running adds nothing")

    def test_reminders(self):
        r = workflow.reminders(BASE, date(2026, 9, 30), 5)
        self.assertIn("PM-0020|FY-2025-26", r["nadia.hassan@example.org"])
        for keys in r.values():
            for k in keys:
                sub = next(x for x in BASE["submissions"] if x["submission_key"] == k)
                self.assertIn(sub["status"], ("not_started", "draft", "returned"))


if __name__ == "__main__":
    unittest.main()
