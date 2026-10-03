"""Open PMS at volume: more measures, people and history than most
organisations will ever have, with time limits on every key page.

Slow, so it only runs when asked:
    OPENPMS_SCALE_TESTS=1 python -m unittest tests.test_scale -v
Set OPENPMS_SCALE_REPORT=path.md to also write the timings as a table.
"""
import os
import random
import re
import tempfile
import time
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openpms import create_app, db, exports, measures_service, workflow
from openpms.cli import DEFAULT_SETTINGS
from openpms.schema import LISTS_BY_NAME

from .helpers import PASSWORD, drop_database, new_database

MEASURES, PEOPLE, TEAMS = 360, 120, 15
FIRST_FY, AS_OF = 2024, date(2026, 9, 30)
PAGE_SECONDS = 2.0      # every page, on a slow CI machine
EXPORT_SECONDS = 30.0   # the full data model as Excel


def bulk(conn, org, table, rows, who="system"):
    """Fast inserts for building test data (no audit rows)."""
    if not rows:
        return
    cols = LISTS_BY_NAME[table].all_columns
    names = [c.name for c in cols] + ["org_id", "created_at", "created_by", "modified_at", "modified_by"]
    now = db.iso(db.utcnow())
    sql = f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})"
    values = [[db.to_db(c, r.get(c.name)) for c in cols] + [org, now, who, now, who] for r in rows]
    if conn.dialect == "postgres":
        with conn.raw.cursor() as cur:
            cur.executemany(sql.replace("?", "%s"), values)
    else:
        conn.raw.executemany(sql, values)


def build(conn, org):
    from openpms.admin import add_periods
    rng = random.Random(7)
    repo = db.Repo(conn, org)
    conn.begin()
    for k, v, d in DEFAULT_SETTINGS:
        repo.insert("settings", dict(setting_key=k, setting_value="Scale Test Council" if k == "organisation_name" else v,
                                     description=d), "system", audit=False)
    conn.execute("COMMIT")
    for fy in range(FIRST_FY, 2028):
        add_periods(repo, fy, "system", daily=fy >= 2026)
    periods = repo.find("periods")
    by_type = {}
    for p in periods:
        by_type.setdefault(p["period_type"], []).append(p)

    conn.begin()
    teams = [dict(org_unit_key=f"TM-{i:02d}", unit_name=f"Team {i:02d}", unit_level="team", active=True)
             for i in range(TEAMS)]
    bulk(conn, org, "org_units", teams)
    people = []
    for i in range(PEOPLE):
        team = teams[i % TEAMS]["org_unit_key"]
        people.append(dict(email=f"person{i:03d}@scale.example", display_name=f"Person {i:03d}", org_unit_key=team,
                           line_manager_email=f"person{i % TEAMS:03d}@scale.example" if i >= TEAMS else None,
                           app_role="admin" if i < 3 else "viewer" if i >= PEOPLE - 10 else "standard", active=True))
    bulk(conn, org, "people", people)
    emails = [p["email"] for p in people]

    measures, roles, subs, versions, rpt, refs, audit = [], [], [], [], [], [], []
    freqs = ["monthly"] * 6 + ["quarterly"] * 2 + ["annual"]
    approved_at = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)
    for i in range(MEASURES):
        code = f"PM-{i + 1:04d}"
        freq = freqs[i % len(freqs)]
        unit = ["number", "percent", "count", "gbp"][i % 4]
        m = dict(measure_code=code, measure_name=f"Measure {i + 1}: {unit} indicator {rng.randint(1, 999)}",
                 source_ref=f"{i // 30 + 1}.{i % 30 + 1:02d}", measure_class=["measure", "kpi", "okr"][i % 3],
                 measure_type="output", unit=unit, decimal_places=1 if unit == "percent" else 0,
                 polarity="higher_is_better", frequency=freq, aggregation_method="sum", expected_lag_days=30,
                 category="economy", org_unit_key=teams[i % TEAMS]["org_unit_key"], status="active",
                 parent_measure_code=None)
        measures.append(m)
        owner, updater, approver = emails[i % PEOPLE], emails[(i + 7) % PEOPLE], emails[(i + 13) % PEOPLE]
        for email, role in ((owner, "owner"), (updater, "updater"), (approver, "approver")):
            roles.append(dict(role_key=f"{code}|{email}|{role}", measure_code=code, email=email, role=role, active=True))
        done = [p for p in by_type[freq] if p["end_date"] <= AS_OF and p["start_date"] >= date(FIRST_FY, 4, 1)]
        for n, p in enumerate(done):
            key = f"{code}|{p['period_key']}"
            value = round(rng.uniform(40, 120), 1)
            target = 80
            sub = dict(submission_key=key, measure_code=code, period_key=p["period_key"], period_end=p["end_date"],
                       status="approved", expected_by=p["end_date"] + timedelta(days=30), current_version=1,
                       approved_version=1, submitted_date=approved_at, approved_by=approver, approved_date=approved_at)
            ver = dict(version_key=f"{key}|v1", submission_key=key, measure_code=code, period_key=p["period_key"],
                       version_no=1, value_number=value, value_text=None, value_missing=False, narrative="On track." if value >= target else
                       "Below target because of a delay in returns; recovery plan agreed.", data_quality="verified",
                       entered_by=updater, entered_date=approved_at, submitted_date=approved_at, version_status="approved",
                       rag_status="green" if value >= target else "red")
            subs.append(sub)
            versions.append(ver)
            refs.append(dict(ref_key=f"{key}|target", measure_code=code, period_key=p["period_key"], ref_type="target",
                             ref_value=target, active=True))
            rpt.append(workflow.rpt_row(sub, ver, m, p, owner, f"Person {i % PEOPLE:03d}", {"target": target},
                                        n == len(done) - 1, approved_at))
            for field in ("status", "status", "value_number", "narrative"):
                audit.append(dict(audit_ref="AUD-" + uuid.uuid4().hex[:16], list_name="submissions", item_key=key,
                                  action="edit", field_name=field, old_value="draft", new_value="submitted",
                                  changed_by=updater, changed_at=approved_at))
        nxt = next((p for p in by_type[freq] if p["end_date"] > AS_OF), None)
        if nxt and nxt["end_date"] <= AS_OF + timedelta(days=60):
            subs.append(dict(submission_key=f"{code}|{nxt['period_key']}", measure_code=code, period_key=nxt["period_key"],
                             period_end=nxt["end_date"], status=["not_started", "draft", "submitted", "returned"][i % 4],
                             expected_by=nxt["end_date"] + timedelta(days=30), current_version=0))
    for table, rows in (("measures", measures), ("measure_roles", roles), ("submissions", subs),
                        ("submission_versions", versions), ("reference_values", refs), ("rpt_values", rpt),
                        ("audit_log", audit)):
        bulk(conn, org, table, rows)

    updates, tasks, problems = [], [], []
    week = date(2026, 3, 30)
    while week <= AS_OF:
        for p in people[:-10]:
            updates.append(dict(update_key=f"{p['email']}|{week}", email=p["email"], week_start=week,
                                org_unit_key=p["org_unit_key"], successes="Delivered the monthly return early.",
                                communication="Nothing new.", workload="manageable",
                                submitted_at=datetime(week.year, week.month, week.day, 16, tzinfo=timezone.utc)))
        week += timedelta(days=7)
    for i in range(3000):
        p = people[i % (PEOPLE - 10)]
        raised = date(2026, 1, 5) + timedelta(days=i % 260)
        done = i % 3 != 0
        tasks.append(dict(task_code=f"TSK-{i + 1:05d}", task_name=f"Task {i + 1}", priority=["must", "should", "could"][i % 3],
                          org_unit_key=p["org_unit_key"], contributes_to_type="measure",
                          contributes_to_key=f"PM-{i % MEASURES + 1:04d}", raised_by=p["email"], date_raised=raised,
                          assigned_to=p["email"], status="complete" if done else "open",
                          completed_by=p["email"] if done else None,
                          completed_date=min(raised + timedelta(days=10), AS_OF) if done else None))
    for i in range(400):
        p = people[i % (PEOPLE - 10)]
        problems.append(dict(problem_code=f"PRB-{i + 1:05d}", problem_title=f"Problem {i + 1}", org_unit_key=p["org_unit_key"],
                             raised_by=p["email"], raised_on=date(2026, 1, 5) + timedelta(days=i % 260),
                             problem_owner=p["email"], impact="medium", urgency="high", status="open" if i % 2 else "closed",
                             closed_date=date(2026, 9, 1) if i % 2 == 0 else None))
    for table, rows in (("weekly_updates", updates), ("tasks", tasks), ("problems", problems)):
        bulk(conn, org, table, rows)
    conn.execute("COMMIT")

    from openpms import auth
    for email in emails[:3] + [emails[7], emails[13], emails[-1]]:
        auth.issue_token(conn, org, email, "invite")
        acc = conn.execute("SELECT id FROM accounts WHERE org_id = ? AND email = ?", (org, email)).fetchone()[0]
        auth.set_password(conn, acc, PASSWORD)
    return dict(submissions=len(subs), versions=len(versions), audit=len(audit), updates=len(updates),
                tasks=len(tasks), periods=len(periods))


@unittest.skipUnless(os.environ.get("OPENPMS_SCALE_TESTS"), "set OPENPMS_SCALE_TESTS=1 to run the scale tests")
class Scale(unittest.TestCase):
    timings = []

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.database = new_database(cls.tmp)
        cls.app = create_app({"TESTING": True, "DATABASE": cls.database, "SECRET_KEY": "test",
                              "SERVER_NAME": "pms.test", "DISABLE_DAILY_JOBS": True,
                              "SNAPSHOT_DIR": str(cls.tmp / "snapshots"), "JOBS_IN_FOREGROUND": True})
        cls.conn = db.connect(cls.database)
        db.init(cls.conn)
        org = db.create_org(cls.conn, "Scale Test Council", "default")
        start = time.perf_counter()
        cls.counts = build(cls.conn, org)
        cls.build_seconds = time.perf_counter() - start
        cls.repo = db.Repo(cls.conn, org)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        drop_database(cls.database)
        report = os.environ.get("OPENPMS_SCALE_REPORT")
        lines = [f"Database: {cls.conn.dialect}. {MEASURES} measures, {PEOPLE} people, "
                 f"{cls.counts['submissions']:,} values, {cls.counts['audit']:,} audit rows, "
                 f"{cls.counts['updates']:,} weekly updates, {cls.counts['tasks']:,} tasks. "
                 f"Built in {cls.build_seconds:.1f} s.", "", "| What | Seconds |", "|---|---|"]
        lines += [f"| {what} | {secs:.2f} |" for what, secs in cls.timings]
        print("\n" + "\n".join(lines))
        if report:
            Path(report).write_text("\n".join(lines) + "\n")

    def client_for(self, email):
        client = self.app.test_client()
        page = client.get("/login").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        r = client.post("/login", data=dict(email=email, password=PASSWORD, csrf_token=token))
        self.assertEqual(r.status_code, 302, email)
        return client

    def timed(self, what, fn, limit=PAGE_SECONDS):
        fn()  # warm up: templates compile on first use
        start = time.perf_counter()
        result = fn()
        secs = time.perf_counter() - start
        self.timings.append((what, secs))
        self.assertLess(secs, limit, f"{what} took {secs:.2f} s")
        return result

    def test_pages(self):
        admin = self.client_for("person000@scale.example")
        updater = self.client_for("person007@scale.example")
        approver = self.client_for("person013@scale.example")
        pages = [
            (admin, "/", "Home"),
            (updater, "/measures/?tab=update", "Measures: to update"),
            (approver, "/measures/?tab=review", "Measures: to review"),
            (admin, "/measures/?tab=all", "Measures: all 360 with latest values"),
            (updater, "/measures/value?key=PM-0001|M-2026-08", "One value with history"),
            (admin, "/admin/measures", "Admin: measures list"),
            (admin, "/admin/measures?q=indicator", "Admin: measures search"),
            (admin, "/admin/audit", "Admin: audit log"),
            (admin, "/admin/periods", "Admin: periods"),
            (updater, "/week?week=2026-09-21", "My week"),
            (admin, "/team?week=2026-09-21&team=TM-00", "My team"),
            (admin, "/exports/", "Exports page"),
        ]
        for client, url, what in pages:
            r = self.timed(what, lambda c=client, u=url: c.get(u))
            self.assertEqual(r.status_code, 200, url)

    def test_exports(self):
        exp = self.timed("Export: build measure values", lambda: exports.build(self.repo, "measures"), EXPORT_SECONDS)
        self.assertGreater(len(exp.table("values_flat")), 7000)
        full = self.timed("Export: build full data model", lambda: exports.build(self.repo, "full_model"), EXPORT_SECONDS)
        self.timed("Export: full data model as Excel", lambda: exports.to_xlsx(full), EXPORT_SECONDS)
        self.timed("Export: full data model as CSV", lambda: exports.csv_files(full), EXPORT_SECONDS)
        self.timed("Export: quarter pack", lambda: exports.build(self.repo, "quarter_pack"), EXPORT_SECONDS)

    def test_daily_jobs(self):
        self.timed("Daily jobs: expected values for a day",
                   lambda: measures_service.create_expected(self.repo, date(2026, 10, 1)), EXPORT_SECONDS)

    def test_workflow_round_trip(self):
        key = "PM-0001|M-2026-10"   # open, and person007 updates it
        self.assertEqual(self.repo.get("submissions", key)["status"], "not_started")
        self.timed("Workflow: save a value", lambda: measures_service.run(
            self.repo, key, "person007@scale.example", "save_draft", value_number=90, value_missing=False,
            value_text=None, narrative=None, data_quality="verified"))


@unittest.skipUnless(os.environ.get("OPENPMS_SCALE_TESTS"), "set OPENPMS_SCALE_TESTS=1 to run the scale tests")
class Concurrent(unittest.TestCase):
    def test_many_people_saving_at_once(self):
        """30 people save at the same moment, each on their own connection."""
        import threading
        tmp = Path(tempfile.mkdtemp())
        database = new_database(tmp)
        conn = db.connect(database)
        db.init(conn)
        org = db.create_org(conn, "Busy Council", "default")
        build(conn, org)
        repo = db.Repo(conn, org)
        open_subs = [s for s in repo.find("submissions", "status = 'not_started'") if s["period_key"].startswith("M-")][:30]
        updaters = {r["measure_code"]: r["email"] for r in repo.find("measure_roles", "role = 'updater'")}
        errors, barrier = [], threading.Barrier(len(open_subs))

        def save(sub):
            c = db.connect(database)
            try:
                barrier.wait()
                measures_service.run(db.Repo(c, org), sub["submission_key"], updaters[sub["measure_code"]],
                                     "save_draft", value_number=55, value_missing=False, value_text=None,
                                     narrative=None, data_quality="verified")
            except Exception as exc:
                errors.append(exc)
            finally:
                c.close()
        threads = [threading.Thread(target=save, args=(s,)) for s in open_subs]
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        secs = time.perf_counter() - start
        self.assertEqual(errors, [])
        self.assertEqual(repo.count("submissions", "status = 'draft' AND current_version = 1 AND submission_key IN (%s)"
                                    % ",".join("?" * len(open_subs)), [s["submission_key"] for s in open_subs]),
                         len(open_subs))
        print(f"\n{len(open_subs)} simultaneous saves on {conn.dialect}: {secs:.2f} s")
        conn.close()
        drop_database(database)
