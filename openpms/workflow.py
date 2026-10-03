"""Reference implementation of the measures workflow.

The Power Automate flows (flows/*.md) must behave exactly like these
functions. Each function takes a `state` dict holding the list rows, checks
permissions, changes the rows and writes audit rows. The tests walk a value
through its whole life to pin the behaviour down.

State lists: measures, periods, people, measure_roles, reference_values,
submissions, submission_versions, review_comments, audit_log, rpt_values.

Status flow
    not_started -> draft -> submitted -> approved
                               |    ^
                               v    |
                            returned
    approved -> (admin reopen) -> draft -> submitted -> approved
"""
from datetime import timedelta

from . import rules

EDITABLE = ("not_started", "draft", "returned")


class NotAllowed(Exception):
    """The caller may not do this."""


class Invalid(Exception):
    """The request breaks a validation rule. .errors lists the reasons."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def _one(rows, key_name, key):
    return next((r for r in rows if r[key_name] == key), None)


def caller_roles(state, measure_code, email):
    return {r["role"] for r in state["measure_roles"]
            if r["measure_code"] == measure_code and r["email"] == email and r["active"]}


def app_role(state, email):
    p = _one(state["people"], "email", email)
    return p["app_role"] if p and p["active"] else None


def refs_for(state, measure_code, period_key):
    return {r["ref_type"]: r["ref_value"] for r in state["reference_values"]
            if r["measure_code"] == measure_code and r["period_key"] == period_key and r["active"]}


def version(state, submission_key, version_no):
    return _one(state["submission_versions"], "version_key", f"{submission_key}|v{version_no}")


def allowed_actions(state, submission_key, caller):
    """What the caller can do to a submission right now."""
    sub = _one(state["submissions"], "submission_key", submission_key)
    roles = caller_roles(state, sub["measure_code"], caller)
    current = version(state, submission_key, sub["current_version"]) if sub["current_version"] else None
    acts = set()
    if "updater" in roles and sub["status"] in EDITABLE:
        acts |= {"save_draft", "submit"}
    # Approvers can't approve a value they entered themselves.
    if "approver" in roles and sub["status"] == "submitted" and current and current["entered_by"] != caller:
        acts |= {"approve", "return"}
    if app_role(state, caller) == "admin" and sub["status"] == "approved":
        acts.add("reopen")
    return acts


def needs_new_version(sub):
    """A new version starts on the first save after a return or a reopen.
    Drafts are otherwise edited in place."""
    if sub["status"] in ("not_started", "returned"):
        return True
    return sub["current_version"] > 0 and sub["current_version"] == sub["approved_version"]


def rag_for(state, measure, period_key, value_number, value_missing):
    refs = refs_for(state, measure["measure_code"], period_key)
    return rules.rag_status(measure, value_number, value_missing, refs.get("target"), refs.get("tolerance"))


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
def _audit(state, list_name, key, action, field, old, new, who, when):
    state["audit_log"].append(dict(
        audit_ref=f"AUD-{len(state['audit_log']) + 1:07d}", list_name=list_name, item_key=key, action=action,
        field_name=field, old_value=None if old is None else str(old), new_value=None if new is None else str(new),
        changed_by=who, changed_at=when))


def _update(state, list_name, row, key_name, changes, who, when, action="edit"):
    """Apply changes to a row, auditing every field that actually changes."""
    for field, new in changes.items():
        old = row.get(field)
        if old != new:
            if action == "edit" and field in ("status", "version_status"):
                act = "status_change"
            else:
                act = action
            _audit(state, list_name, row[key_name], act, field, old, new, who, when)
            row[field] = new


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def _check(state, submission_key, caller, action):
    if action not in allowed_actions(state, submission_key, caller):
        raise NotAllowed(f"{caller} cannot {action} {submission_key}")
    return _one(state["submissions"], "submission_key", submission_key)


def save_value(state, submission_key, caller, now, *, submit, value_number=None, value_text=None,
               value_missing=False, narrative=None, data_quality="unverified"):
    """Updater saves a draft or submits. Returns the version row."""
    sub = _check(state, submission_key, caller, "submit" if submit else "save_draft")
    measure = _one(state["measures"], "measure_code", sub["measure_code"])
    if submit:
        rag = rag_for(state, measure, sub["period_key"], value_number, value_missing)
        errors = rules.validate_value(measure, value_number, value_text, value_missing, narrative, rag)
        if errors:
            raise Invalid(errors)
    fields = dict(value_number=value_number, value_text=value_text, value_missing=value_missing,
                  narrative=narrative, data_quality=data_quality, entered_by=caller,
                  version_status="submitted" if submit else "draft",
                  submitted_date=now if submit else None)
    if needs_new_version(sub):
        no = sub["current_version"] + 1
        row = dict(version_key=f"{submission_key}|v{no}", submission_key=submission_key,
                   measure_code=sub["measure_code"], period_key=sub["period_key"], version_no=no,
                   entered_date=now, rag_status=None, **fields)
        state["submission_versions"].append(row)
        _audit(state, "submission_versions", row["version_key"], "create", None, None, None, caller, now)
    else:
        no = sub["current_version"]
        row = version(state, submission_key, no)
        _update(state, "submission_versions", row, "version_key", fields, caller, now)
    _update(state, "submissions", sub, "submission_key",
            dict(status="submitted" if submit else "draft", current_version=no,
                 submitted_date=now if submit else sub["submitted_date"]), caller, now)
    return row


def _comment(state, submission_key, version_no, caller, action, text, now):
    state["review_comments"].append(dict(
        comment_ref=f"RC-{len(state['review_comments']) + 1:05d}", submission_key=submission_key,
        version_no=version_no, reviewer_email=caller, action=action, comment=text, comment_date=now,
        resolved=False, resolved_by=None, resolved_date=None))


def return_for_changes(state, submission_key, caller, now, comment):
    sub = _check(state, submission_key, caller, "return")
    if not (comment and comment.strip()):
        raise Invalid(["A comment is required when returning for changes."])
    row = version(state, submission_key, sub["current_version"])
    _update(state, "submission_versions", row, "version_key", dict(version_status="returned"), caller, now)
    _update(state, "submissions", sub, "submission_key", dict(status="returned"), caller, now)
    _comment(state, submission_key, row["version_no"], caller, "returned", comment.strip(), now)
    # The flow emails every active updater with the comment and a link.
    return [r["email"] for r in state["measure_roles"]
            if r["measure_code"] == sub["measure_code"] and r["role"] == "updater" and r["active"]]


def approve(state, submission_key, caller, now, comment=None):
    sub = _check(state, submission_key, caller, "approve")
    measure = _one(state["measures"], "measure_code", sub["measure_code"])
    row = version(state, submission_key, sub["current_version"])
    rag = rag_for(state, measure, sub["period_key"], row["value_number"], row["value_missing"])
    if sub["approved_version"]:
        old = version(state, submission_key, sub["approved_version"])
        _update(state, "submission_versions", old, "version_key", dict(version_status="superseded"), caller, now)
    _update(state, "submission_versions", row, "version_key", dict(version_status="approved", rag_status=rag), caller, now)
    _update(state, "submissions", sub, "submission_key",
            dict(status="approved", approved_version=row["version_no"], approved_by=caller, approved_date=now),
            caller, now)
    if comment and comment.strip():
        _comment(state, submission_key, row["version_no"], caller, "approved", comment.strip(), now)
    for c in state["review_comments"]:
        if c["submission_key"] == submission_key and not c["resolved"]:
            c.update(resolved=True, resolved_by=caller, resolved_date=now)
    upsert_rpt(state, sub, row, now)
    return row


def reopen(state, submission_key, caller, now, reason):
    sub = _check(state, submission_key, caller, "reopen")
    if not (reason and reason.strip()):
        raise Invalid(["Give a reason for reopening."])
    _update(state, "submissions", sub, "submission_key", dict(status="draft"), caller, now, action="reopen")
    _comment(state, submission_key, sub["current_version"], caller, "reopened", reason.strip(), now)
    # The approved version stays in reports until a new one is approved.


# ---------------------------------------------------------------------------
# Reporting table
# ---------------------------------------------------------------------------
def rpt_row(sub, ver, measure, period, owner_email, owner_name, refs, is_latest, refreshed_at):
    kpi = measure["measure_class"] in ("kpi", "okr")
    return dict(
        submission_key=sub["submission_key"], measure_code=measure["measure_code"], measure_name=measure["measure_name"],
        source_ref=measure["source_ref"], parent_measure_code=measure["parent_measure_code"],
        measure_class=measure["measure_class"], measure_type=measure["measure_type"], category=measure["category"],
        unit=measure["unit"], polarity=measure["polarity"], frequency=measure["frequency"],
        aggregation_method=measure["aggregation_method"], owner_name=owner_name, owner_email=owner_email,
        org_unit_key=measure["org_unit_key"], period_key=period["period_key"], period_type=period["period_type"],
        period_label=period["period_label"], period_start=period["start_date"], period_end=period["end_date"],
        financial_year=period["financial_year"], financial_quarter=period["financial_quarter"],
        value_number=ver["value_number"], value_text=ver["value_text"], value_missing=ver["value_missing"],
        narrative=ver["narrative"], data_quality=ver["data_quality"], version_no=ver["version_no"],
        approved_by=sub["approved_by"], approved_date=sub["approved_date"],
        target_value=refs.get("target"), tolerance_value=refs.get("tolerance") if kpi else None,
        baseline_value=refs.get("baseline"), capacity_value=refs.get("capacity"),
        rag_status=ver["rag_status"], is_latest=is_latest, refreshed_at=refreshed_at,
    )


def upsert_rpt(state, sub, ver, now):
    """Add or replace the reporting row, and move is_latest if this period is newer."""
    measure = _one(state["measures"], "measure_code", sub["measure_code"])
    period = _one(state["periods"], "period_key", sub["period_key"])
    owner = next(r["email"] for r in state["measure_roles"]
                 if r["measure_code"] == measure["measure_code"] and r["role"] == "owner" and r["active"])
    owner_name = _one(state["people"], "email", owner)["display_name"]
    current_latest = next((r for r in state["rpt_values"]
                           if r["measure_code"] == measure["measure_code"] and r["is_latest"]), None)
    latest = (current_latest is None or current_latest["submission_key"] == sub["submission_key"]
              or period["end_date"] >= current_latest["period_end"])
    if latest and current_latest and current_latest["submission_key"] != sub["submission_key"]:
        current_latest["is_latest"] = False
    row = rpt_row(sub, ver, measure, period, owner, owner_name,
                  refs_for(state, measure["measure_code"], period["period_key"]), latest, now)
    state["rpt_values"][:] = [r for r in state["rpt_values"] if r["submission_key"] != sub["submission_key"]]
    state["rpt_values"].append(row)
    return row


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------
def expected_submissions(state, today, lookback_days=7):
    """New not_started submissions for periods that ended in the last
    lookback_days (the look-back catches up if a daily run is missed)."""
    existing = {s["submission_key"] for s in state["submissions"]}
    new = []
    for p in state["periods"]:
        if not (today - timedelta(days=lookback_days) <= p["end_date"] < today):
            continue
        for m in state["measures"]:
            if m["status"] != "active" or m["frequency"] != p["period_type"]:
                continue
            key = f"{m['measure_code']}|{p['period_key']}"
            if key in existing:
                continue
            new.append(dict(submission_key=key, measure_code=m["measure_code"], period_key=p["period_key"],
                            period_end=p["end_date"], status="not_started", expected_by=rules.expected_by(p["end_date"], m["expected_lag_days"]),
                            current_version=0, approved_version=None, submitted_date=None,
                            approved_by=None, approved_date=None))
    return new


def reminders(state, today, days_before):
    """Who to remind: updaters with work expected by today + days_before
    that isn't submitted yet. Returns {email: [submission_key, ...]}."""
    horizon = today + timedelta(days=days_before)
    due = [s for s in state["submissions"]
           if s["status"] in EDITABLE and s["expected_by"] is not None and s["expected_by"] <= horizon]
    out = {}
    for s in due:
        for r in state["measure_roles"]:
            if r["measure_code"] == s["measure_code"] and r["role"] == "updater" and r["active"]:
                out.setdefault(r["email"], []).append(s["submission_key"])
    return {k: sorted(v) for k, v in sorted(out.items())}
