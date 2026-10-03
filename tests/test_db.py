"""The database enforces the data rules itself, audits every change and
keeps organisations apart."""
import sqlite3
import unittest
from datetime import date

from openpms import db
from openpms.schema import LISTS


def fresh():
    conn = db.connect(":memory:")
    db.init(conn)
    return conn, db.Repo(conn, db.create_org(conn, "Org A", "a"))


class ConstraintTests(unittest.TestCase):
    def test_every_table_created_with_key_and_org(self):
        conn, _ = fresh()
        for lst in LISTS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({lst.name})")}
            self.assertTrue({"id", "org_id", lst.key, "created_at", "modified_by"} <= cols, lst.name)

    def test_bad_values_rejected_by_database(self):
        conn, repo = fresh()
        base = {"group_key": "G1", "group_name": "One", "group_type": "theme", "active": True}
        for bad in ({"group_type": "nonsense"}, {"group_name": "   "}, {"group_name": None}):
            with self.assertRaises(sqlite3.IntegrityError, msg=bad):
                repo.insert("groups", dict(base, **bad), "t@x")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO periods (org_id, period_key, period_type, period_label, start_date, end_date, "
                         "created_at, created_by, modified_at, modified_by) VALUES (1, 'P', 'daily', 'x', "
                         "'30/09/2026', '2026-09-30', 'x', 'x', 'x', 'x')")

    def test_keys_unique_per_organisation(self):
        conn, repo = fresh()
        row = {"group_key": "G1", "group_name": "One", "group_type": "theme", "active": True}
        repo.insert("groups", row, "t@x")
        with self.assertRaises(sqlite3.IntegrityError):
            repo.insert("groups", row, "t@x")
        other = db.Repo(conn, db.create_org(conn, "Org B", "b"))
        other.insert("groups", row, "t@x")  # same key, different organisation: fine
        self.assertEqual(repo.count("groups"), 1)
        self.assertEqual(other.count("groups"), 1)

    def test_organisations_cannot_see_each_other(self):
        conn, repo = fresh()
        repo.insert("groups", {"group_key": "SECRET", "group_name": "A's", "group_type": "theme", "active": True}, "a")
        other = db.Repo(conn, db.create_org(conn, "Org B", "b"))
        self.assertIsNone(other.get("groups", "SECRET"))
        self.assertEqual(other.find("groups"), [])

    def test_no_delete_anywhere(self):
        self.assertFalse(any(name.startswith("delete") for name in dir(db.Repo)))


class AuditTests(unittest.TestCase):
    def test_create_and_each_changed_field_audited(self):
        _, repo = fresh()
        repo.insert("groups", {"group_key": "G1", "group_name": "One", "group_type": "theme", "active": True}, "a@x")
        repo.update("groups", "G1", {"group_name": "Uno", "group_type": "theme", "active": False}, "b@x")
        rows = [(a["action"], a["field_name"], a["old_value"], a["new_value"], a["changed_by"])
                for a in repo.find("audit_log", order="id")]
        self.assertEqual(rows, [("create", None, None, None, "a@x"),
                                ("edit", "group_name", "One", "Uno", "b@x"),
                                ("edit", "active", "true", "false", "b@x")])

    def test_unchanged_update_writes_nothing(self):
        _, repo = fresh()
        repo.insert("groups", {"group_key": "G1", "group_name": "One", "group_type": "theme", "active": True}, "a")
        repo.update("groups", "G1", {"group_name": "One"}, "a")
        self.assertEqual(repo.count("audit_log"), 1)

    def test_status_changes_marked(self):
        _, repo = fresh()
        repo.insert("tasks", {"task_code": "T1", "task_name": "x", "priority": "must", "org_unit_key": "U",
                              "raised_by": "a@x", "date_raised": date(2026, 9, 1), "status": "open"}, "a")
        repo.update("tasks", "T1", {"status": "complete"}, "a")
        self.assertEqual(repo.find("audit_log", order="id")[-1]["action"], "status_change")

    def test_wellbeing_values_never_in_audit_log(self):
        _, repo = fresh()
        repo.insert("wellbeing_checkins", {"checkin_key": "k", "email": "a@x", "org_unit_key": "U",
                                           "week_start": date(2026, 9, 28), "wellbeing": "ok",
                                           "submitted_at": db.utcnow()}, "a@x")
        repo.update("wellbeing_checkins", "k", {"wellbeing": "struggling", "comments": "private"}, "a@x")
        for a in repo.find("audit_log", "list_name = 'wellbeing_checkins'"):
            self.assertNotIn(a["old_value"], ("ok", "struggling", "private"))
            self.assertNotIn(a["new_value"], ("ok", "struggling", "private"))

    def test_round_trip_types(self):
        _, repo = fresh()
        repo.insert("periods", {"period_key": "M-2026-09", "period_type": "monthly", "period_label": "Sep 2026",
                                "start_date": date(2026, 9, 1), "end_date": date(2026, 9, 30),
                                "calendar_year": 2026}, "a")
        p = repo.get("periods", "M-2026-09")
        self.assertEqual(p["start_date"], date(2026, 9, 1))
        self.assertEqual(p["calendar_year"], 2026)


if __name__ == "__main__":
    unittest.main()
