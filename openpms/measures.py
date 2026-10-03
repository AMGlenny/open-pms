"""Measures: my work list, the value page (enter, review, reopen) and targets."""
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import auth, forms, mail, measures_service as svc, rules, workflow
from .schema import columns

bp = Blueprint("measures", __name__, url_prefix="/measures")

QUALITY = [("verified", "Verified: checked against source"), ("provisional", "Provisional: may change"),
           ("estimated", "Estimated: modelled or partial"), ("unverified", "Unverified: not yet checked")]
RAG_TEXT = {"green": "Green: on or better than target", "amber": "Amber: short of target, within tolerance",
            "red": "Red: off track", "no_target": "No target set", "no_data": "No data",
            "not_applicable": "RAG not used for this measure"}
STATUS_TEXT = {"not_started": "Not started", "draft": "Draft", "submitted": "Awaiting review",
               "returned": "Returned for changes", "approved": "Approved"}
OPEN = ("not_started", "draft", "returned", "submitted")


def fmt_value(measure, value_number, value_text=None, missing=False):
    """A value as people expect to read it: 58.0%, £1,250, Yes."""
    if missing:
        return "No value"
    unit = measure["unit"]
    if unit == "text":
        return value_text or ""
    if value_number is None:
        return ""
    if unit == "yes_no":
        return "Yes" if value_number == 1 else "No"
    dp = measure.get("decimal_places") or 0
    text = f"{value_number:,.{dp}f}"
    return {"percent": text + "%", "gbp": "£" + text}.get(unit, text)


@bp.app_context_processor
def helpers():
    return {"fmt_value": fmt_value, "rag_text": RAG_TEXT, "status_text": STATUS_TEXT}


@bp.route("/")
@auth.login_required
def home():
    tab = request.args.get("tab", "update")
    me = g.person["email"]
    roles = g.repo.by("measure_roles", email=me, active=True)
    updates = {r["measure_code"] for r in roles if r["role"] == "updater"}
    approves = {r["measure_code"] for r in roles if r["role"] == "approver"}
    today = date.today()
    cutoff = (today - timedelta(days=400)).isoformat()
    open_subs = g.repo.find("submissions", f"period_end >= ? AND status IN ({','.join('?' * len(OPEN))})",
                            (cutoff, *OPEN))
    measures = {m["measure_code"]: m for m in g.repo.find("measures")}

    def late(s):
        return s["expected_by"] is not None and s["expected_by"] < today

    to_update = []
    for s in open_subs:
        if s["measure_code"] in updates and s["status"] != "submitted":
            grp = (1, "Returned for changes") if s["status"] == "returned" else \
                  (2, "Expected, not received") if late(s) else \
                  (3, "Draft") if s["status"] == "draft" else (4, "Awaiting data")
            to_update.append((grp, s))
    to_review = []
    for s in open_subs:
        if s["measure_code"] in approves:
            if s["status"] == "submitted":
                to_review.append(((1, "Awaiting your review"), s))
            elif s["status"] == "returned":
                to_review.append(((2, "Returned, waiting on the updater"), s))
            elif late(s):
                to_review.append(((3, "Overdue"), s))
    keys = {s["period_key"] for _, s in to_update + to_review}
    periods = {}
    if keys:
        periods = {p["period_key"]: p for p in g.repo.find("periods", f"period_key IN ({','.join('?' * len(keys))})",
                                                           tuple(keys))}
    order = lambda item: (item[0][0], periods[item[1]["period_key"]]["end_date"], item[1]["measure_code"])
    to_update.sort(key=order)
    to_review.sort(key=order)
    q = request.args.get("q", "").strip().lower()
    latest = {r["measure_code"]: r for r in g.repo.find("rpt_values", "is_latest = 1")}
    all_measures = [m for m in measures.values() if m["status"] == "active" and
                    (not q or q in m["measure_name"].lower() or q in (m["source_ref"] or "").lower()
                     or q in m["measure_code"].lower())]
    return render_template("measures/list.html", tab=tab, to_update=to_update, to_review=to_review,
                           measures=measures, periods=periods, all_measures=all_measures, latest=latest, q=q)


def _parse_value(measure, form):
    """Read the value fields. Returns (kwargs for the workflow, error or None)."""
    missing = form.get("value_missing") == "1"
    unit = measure["unit"]
    out = dict(value_missing=missing, value_number=None, value_text=None,
               narrative=(form.get("narrative") or "").strip() or None,
               data_quality=form.get("data_quality") or "unverified")
    if out["data_quality"] not in dict(QUALITY):
        return out, "Choose the data quality from the list."
    if missing:
        return out, None
    if unit == "text":
        out["value_text"] = (form.get("value_text") or "").strip() or None
    elif unit == "yes_no":
        yn = form.get("value_yes_no")
        out["value_number"] = 1 if yn == "yes" else 0 if yn == "no" else None
    else:
        raw = (form.get("value_number") or "").strip().replace(",", "").replace("£", "").rstrip("%").strip()
        if raw:
            try:
                n = float(raw)
            except ValueError:
                return out, "Enter a number, for example 58 or 1250.5."
            out["value_number"] = int(n) if n.is_integer() else n
    return out, None


@bp.route("/value", methods=["GET", "POST"])
@auth.login_required
def value():
    key = request.values.get("key", "")
    sub = g.repo.get("submissions", key)
    if sub is None:
        abort(404)
    measure = g.repo.get("measures", sub["measure_code"])
    me = g.person["email"]
    errors = []
    if request.method == "POST":
        action = request.form.get("action")
        if action not in ("save_draft", "submit", "approve", "return", "reopen"):
            abort(400)
        if g.role == "viewer":
            abort(403)
        kwargs, err = ({}, None)
        if action in ("save_draft", "submit"):
            kwargs, err = _parse_value(measure, request.form)
        else:
            kwargs = {"comment": (request.form.get("comment") or "").strip() or None}
        if err:
            errors = [err]
        else:
            try:
                notify = svc.run(g.repo, key, me, action, **kwargs)
            except workflow.NotAllowed:
                abort(403)
            except workflow.Invalid as exc:
                errors = exc.errors
            else:
                _notify(action, notify, measure, sub, kwargs.get("comment"))
                flash({"save_draft": "Draft saved.", "submit": "Submitted for review.", "approve": "Approved.",
                       "return": "Returned to the updater with your comment.",
                       "reopen": "Reopened. Reports keep the approved value until a new one is approved."}[action])
                return redirect(url_for("measures.value", key=key))
    return _value_page(key, errors)


def _notify(action, emails, measure, sub, comment):
    base = (g.repo.get("settings", "base_url") or {}).get("setting_value", "").rstrip("/")
    link = f"{base}{url_for('measures.value', key=sub['submission_key'])}"
    subject, body = {
        "submit": ("Value to review", f"{g.person['display_name']} has submitted a value."),
        "return": ("Returned for changes", f"{g.person['display_name']} returned this value:\n\n{comment}"),
        "reopen": ("Reopened for correction", f"{g.person['display_name']} reopened this value:\n\n{comment}"),
    }.get(action, (None, None))
    if not subject:
        return
    for email in emails:
        if email != g.person["email"]:
            mail.send(g.repo, email, f"{subject}: {measure['measure_name']}",
                      f"{body}\n\nMeasure: {measure['measure_name']} ({measure['measure_code']})\n"
                      f"Period: {sub['period_key']}\n\nOpen it here: {link}")


def _value_page(key, errors):
    state = svc.load_state(g.repo, key)
    sub, measure, period = state["submissions"][0], state["measures"][0], state["periods"][0]
    me = g.person["email"]
    acts = workflow.allowed_actions(state, key, me) if g.role != "viewer" else set()
    versions = sorted(state["submission_versions"], key=lambda v: v["version_no"], reverse=True)
    current = next((v for v in versions if v["version_no"] == sub["current_version"]), None)
    found = workflow.refs_for(state, measure["measure_code"], period["period_key"])
    refs = {t: found.get(t) for t in ("target", "tolerance", "baseline", "capacity")}
    rag_now = None
    if current:
        rag_now = workflow.rag_for(state, measure, period["period_key"], current["value_number"], current["value_missing"])
    history = sorted(state["rpt_values"], key=lambda r: r["period_end"], reverse=True)[:6]
    names = {p["email"]: p["display_name"] for p in state["people"]}
    comments = sorted(state["review_comments"], key=lambda c: c["comment_date"], reverse=True)
    own_entry = (sub["status"] == "submitted" and current and current["entered_by"] == me and
                 "approver" in workflow.caller_roles(state, measure["measure_code"], me))
    # When an updater has just failed validation, show what they typed.
    typed = None
    if request.method == "POST" and request.form.get("action") in ("save_draft", "submit"):
        typed, _ = _parse_value(measure, request.form)
    return render_template("measures/value.html", sub=sub, measure=measure, period=period, acts=acts,
                           versions=versions, current=current, refs=refs, rag_now=rag_now, history=history,
                           names=names, comments=comments, errors=errors, quality=QUALITY, own_entry=own_entry,
                           typed=typed, tolerance_used=measure["measure_class"] in ("kpi", "okr")), \
        (400 if errors else 200)


@bp.route("/targets", methods=["GET", "POST"])
@auth.admin_required
def targets():
    f = request.values
    measures = g.repo.find("measures", "status = 'active'", order="measure_code")
    code = f.get("measure_code") or ""
    measure = g.repo.get("measures", code) if code else None
    types = [("target", "Target"), ("baseline", "Baseline"), ("capacity", "Capacity or throughput")]
    if measure and measure["measure_class"] in ("kpi", "okr"):
        types.insert(1, ("tolerance", "Tolerance"))
    ref_type = f.get("ref_type") or "target"
    errors = {}
    start, err1 = forms.parse_field(columns("periods")["start_date"], f.get("from_date") or "")
    end, err2 = forms.parse_field(columns("periods")["end_date"], f.get("to_date") or "")
    periods = []
    if measure and start and end:
        periods = g.repo.find("periods", "period_type = ? AND start_date >= ? AND end_date <= ?",
                              (measure["frequency"], start.isoformat(), end.isoformat()), order="start_date")
    existing = {}
    if measure and periods:
        for r in g.repo.by("reference_values", measure_code=measure["measure_code"], ref_type=ref_type):
            existing[r["period_key"]] = r
    if request.method == "POST":
        action = f.get("action")
        if not measure:
            errors["measure_code"] = "Choose a measure."
        if ref_type not in dict(types):
            errors["ref_type"] = "Tolerance only applies to KPIs and OKRs." if ref_type == "tolerance" else "Choose a type."
        if err1 or not start:
            errors["from_date"] = "Enter the first date of the range."
        if err2 or not end:
            errors["to_date"] = "Enter the last date of the range."
        value, err = forms.parse_field(columns("reference_values")["ref_value"], f.get("ref_value"))
        if action == "apply" and (err or value is None):
            errors["ref_value"] = "Enter a number."
        if not errors and not periods:
            errors["from_date"] = "There are no periods of this measure's frequency in that range."
        if not errors:
            me = g.person["email"]
            notes = (f.get("notes") or "").strip() or None
            with g.repo.transaction():
                for p in periods:
                    k = f"{measure['measure_code']}|{p['period_key']}|{ref_type}"
                    row = g.repo.get("reference_values", k)
                    if action == "apply":
                        if row:
                            g.repo.update("reference_values", k, dict(ref_value=value, notes=notes, active=True), me)
                        else:
                            g.repo.insert("reference_values", dict(ref_key=k, measure_code=measure["measure_code"],
                                                                   period_key=p["period_key"], ref_type=ref_type,
                                                                   ref_value=value, notes=notes, active=True), me)
                    elif row:
                        g.repo.update("reference_values", k, dict(active=False), me)
            flash(f"{'Saved' if action == 'apply' else 'Stopped using'} for {len(periods)} period(s).")
            return redirect(url_for("measures.targets", measure_code=code, ref_type=ref_type,
                                    from_date=start.isoformat(), to_date=end.isoformat()))
    return render_template("measures/targets.html", measures=measures, measure=measure, types=types,
                           ref_type=ref_type, periods=periods, existing=existing, errors=errors, form=f)
