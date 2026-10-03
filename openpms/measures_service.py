"""Runs the tested workflow rules (workflow.py) against the database.

Each action loads every row one value touches into a small in-memory state,
runs the same function the tests exercise, then saves exactly what changed,
all in one transaction. So the rules in the app are the rules in the tests,
and a failure part-way leaves nothing half-saved.
"""
import copy
import uuid
from datetime import date, timedelta

from . import db, forms, mail, workflow
from .schema import LISTS_BY_NAME

PERSISTED = ("submissions", "submission_versions", "review_comments", "rpt_values")


def load_state(repo, submission_key):
    sub = repo.get("submissions", submission_key)
    if sub is None:
        return None
    m, p = sub["measure_code"], sub["period_key"]
    return {
        "measures": [repo.get("measures", m)],
        "periods": [repo.get("periods", p)],
        "people": repo.find("people"),
        "measure_roles": repo.by("measure_roles", measure_code=m),
        "reference_values": repo.by("reference_values", measure_code=m, period_key=p),
        "submissions": [sub],
        "submission_versions": repo.by("submission_versions", submission_key=submission_key),
        "review_comments": repo.by("review_comments", submission_key=submission_key),
        "rpt_values": repo.by("rpt_values", measure_code=m),
        "audit_log": [],
    }


def _clean(row):
    return {k: v for k, v in row.items() if not k.startswith("_")}


def persist(repo, before, after, who, now):
    """Write the difference between two states. Audit rows come from the
    workflow itself (it records exactly the fields it changed)."""
    for table in PERSISTED:
        key = LISTS_BY_NAME[table].key
        old = {r[key]: r for r in before[table]}
        for row in after[table]:
            row = _clean(row)
            if table == "review_comments" and row[key] not in old:
                row[key] = forms.make_key({"key": ("sequence", "RC-", 5)}, {}, repo, table)
            if row[key] in old:
                prev = _clean(old[row[key]])
                changes = {k: v for k, v in row.items() if k != key and prev.get(k) != v}
                if changes:
                    repo.update(table, row[key], changes, who, now, audit=False)
            else:
                repo.insert(table, row, who, now, audit=False)
    for a in after["audit_log"]:
        a = dict(a, audit_ref="AUD-" + uuid.uuid4().hex[:16])
        repo.insert("audit_log", a, who, now, audit=False)


def run(repo, submission_key, who, action, **kwargs):
    """action: save_draft, submit, approve, return, reopen.
    Raises workflow.NotAllowed or workflow.Invalid. Returns the emails to notify."""
    now = db.utcnow()
    with repo.transaction():
        state = load_state(repo, submission_key)
        if state is None:
            raise workflow.NotAllowed("No such value.")
        before = copy.deepcopy(state)
        notify = []
        if action in ("save_draft", "submit"):
            workflow.save_value(state, submission_key, who, now, submit=action == "submit", **kwargs)
            if action == "submit":
                notify = [r["email"] for r in state["measure_roles"] if r["role"] == "approver" and r["active"]]
        elif action == "approve":
            workflow.approve(state, submission_key, who, now, kwargs.get("comment"))
        elif action == "return":
            notify = workflow.return_for_changes(state, submission_key, who, now, kwargs.get("comment"))
        elif action == "reopen":
            workflow.reopen(state, submission_key, who, now, kwargs.get("comment"))
            notify = [r["email"] for r in state["measure_roles"] if r["role"] == "updater" and r["active"]]
        else:
            raise ValueError(action)
        persist(repo, before, state, who, now)
    return notify


def allowed(repo, submission_key, who):
    state = load_state(repo, submission_key)
    return workflow.allowed_actions(state, submission_key, who) if state else set()


# ---------------------------------------------------------------------------
# Daily jobs
# ---------------------------------------------------------------------------
def create_expected(repo, today=None, lookback_days=7, who="system"):
    """Not-started submissions for periods that ended in the last week."""
    today = today or date.today()
    start = (today - timedelta(days=lookback_days)).isoformat()
    periods = repo.find("periods", "end_date >= ? AND end_date < ?", (start, today.isoformat()))
    if not periods:
        return 0
    keys = [p["period_key"] for p in periods]
    marks = ",".join("?" * len(keys))
    state = {
        "periods": periods,
        "measures": repo.find("measures", "status = 'active'"),
        "submissions": repo.find("submissions", f"period_key IN ({marks})", keys),
    }
    new = workflow.expected_submissions(state, today, lookback_days)
    with repo.transaction():
        for s in new:
            repo.insert("submissions", s, who)
    return len(new)


def send_reminders(repo, today=None, days_before=None):
    """One email per updater listing what's late or due soon."""
    today = today or date.today()
    if days_before is None:
        row = repo.get("settings", "reminder_days_before_expected")
        days_before = int(row["setting_value"]) if row and row["setting_value"].isdigit() else 5
    horizon = (today + timedelta(days=days_before)).isoformat()
    state = {
        "submissions": repo.find("submissions", "status IN ('not_started', 'draft', 'returned') AND expected_by <= ?",
                                 (horizon,)),
        "measure_roles": repo.find("measure_roles", "role = 'updater' AND active = 1"),
    }
    due = workflow.reminders(state, today, days_before)
    names = {m["measure_code"]: m["measure_name"] for m in repo.find("measures")}
    subs = {s["submission_key"]: s for s in state["submissions"]}
    base = (repo.get("settings", "base_url") or {}).get("setting_value", "").rstrip("/")
    for email, keys in due.items():
        lines = []
        for k in keys:
            s = subs[k]
            lines.append(f"- {names.get(s['measure_code'], s['measure_code'])}, {s['period_key']}: "
                         f"{s['status'].replace('_', ' ')}, expected by {s['expected_by'].isoformat()}")
        mail.send(repo, email, f"Performance values due: {len(keys)}",
                  "These values are late or expected soon:\n\n" + "\n".join(lines) +
                  f"\n\nUpdate them here: {base}/measures")
    return due


def run_daily(repo, today=None):
    """Runs once a day: from the first request of the day, or `openpms run-jobs`."""
    today = today or date.today()
    marker = f"daily_jobs_{repo.org_id}"
    conn = repo.conn
    conn.execute("BEGIN IMMEDIATE")  # only one process claims today's run
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (marker,)).fetchone()
    if row and row["value"] >= today.isoformat():
        conn.execute("COMMIT")
        return None
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (marker, today.isoformat()))
    conn.execute("COMMIT")
    result = {"expected": create_expected(repo, today)}
    if today.isoweekday() == 1:
        result["reminders"] = len(send_reminders(repo, today))
    return result
