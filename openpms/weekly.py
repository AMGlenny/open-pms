"""Weekly updates: My week, tasks, problems and My team.

Rules (shared with the original design, see rules.py):
- one update and one wellbeing check-in per person per week; people can only
  ever write their own, because the key is built from the signed-in person;
- open tasks and problems carry over every week until they're closed;
- individual wellbeing is only shown to the person themselves and to the
  line manager recorded on the check-in; everyone else sees team totals,
  and only once enough people have answered.
"""
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import auth, db, forms, rules
from .schema import columns

bp = Blueprint("weekly", __name__)

WORKLOAD = [("light", "Light"), ("manageable", "Manageable"), ("heavy", "Heavy"), ("overloaded", "Overloaded")]
WELLBEING = [("thriving", "Thriving"), ("ok", "OK"), ("struggling", "Struggling")]
PRIORITY = [("must", "Must do"), ("should", "Should do"), ("could", "Could do")]
LEVELS = [("low", "Low"), ("medium", "Medium"), ("high", "High")]


def can_edit():
    return g.role in ("admin", "standard")


def edit_required(view):
    import functools

    @functools.wraps(view)
    @auth.login_required
    def wrapped(*a, **k):
        if request.method == "POST" and not can_edit():
            abort(403)
        return view(*a, **k)
    return wrapped


def chosen_week():
    raw = request.values.get("week")
    try:
        d = date.fromisoformat(raw) if raw else date.today()
    except ValueError:
        d = date.today()
    return rules.week_start(d)


def team_paths():
    """[(org_unit_key, 'Workstream > Team > Sub-team')] for active teams."""
    units = {u["org_unit_key"]: u for u in g.repo.find("org_units", "active = 1")}

    def path(u):
        parts, seen = [], set()
        while u and u["org_unit_key"] not in seen:
            seen.add(u["org_unit_key"])
            parts.append(u["unit_name"])
            u = units.get(u["parent_key"])
        return " > ".join(reversed(parts))
    return sorted(((k, path(u)) for k, u in units.items()), key=lambda t: t[1].lower())


def chosen_team():
    team = request.values.get("team") or g.person.get("org_unit_key")
    valid = {k for k, _ in team_paths()}
    return team if team in valid else (sorted(valid)[0] if valid else None)


def people_names():
    return {p["email"]: p["display_name"] for p in g.repo.find("people")}


def contributes_options():
    opts = [(f"group:{x['group_key']}", f"{x['group_name']} ({x['group_type']})")
            for x in g.repo.find("groups", "active = 1", order="group_name")]
    opts += [(f"measure:{m['measure_code']}", f"{m['source_ref'] or ''} {m['measure_name']} (measure)".strip())
             for m in g.repo.find("measures", "status = 'active'", order="measure_code")]
    return opts


def team_items(table, team, week):
    """Open items for the team, plus anything closed during the week."""
    closed_col = "completed_date" if table == "tasks" else "closed_date"
    week_end = week + timedelta(days=6)
    rows = g.repo.find(table, f"org_unit_key = ? AND (status = 'open' OR ({closed_col} BETWEEN ? AND ?))",
                       (team, week.isoformat(), week_end.isoformat()))
    if table == "tasks":
        return rules.tasks_for_week(rows, team, week)
    return rules.problems_for_week(rows, team, week)


# ---------------------------------------------------------------------------
# My week
# ---------------------------------------------------------------------------
@bp.route("/week", methods=["GET", "POST"])
@edit_required
def my_week():
    week, team = chosen_week(), chosen_team()
    me = g.person["email"]
    key = f"{me}|{week.isoformat()}"
    update = g.repo.get("weekly_updates", key)
    checkin = g.repo.get("wellbeing_checkins", key)
    tasks = team_items("tasks", team, week) if team else []
    errors = {}
    if request.method == "POST":
        if not team:
            abort(400, description="Choose a team first.")
        f = request.form
        workload = f.get("workload") or None
        wellbeing = f.get("wellbeing") or None
        if workload and workload not in dict(WORKLOAD):
            errors["workload"] = "Choose your workload from the list."
        if wellbeing and wellbeing not in dict(WELLBEING):
            errors["wellbeing"] = "Choose how you're doing from the list."
        if not errors:
            now = db.utcnow()
            fields = dict(week_start=week, org_unit_key=team, successes=f.get("successes", "").strip() or None,
                          communication=f.get("communication", "").strip() or None, workload=workload,
                          submitted_at=now)
            with g.repo.transaction():
                if update:
                    g.repo.update("weekly_updates", key, fields, me, now)
                else:
                    g.repo.insert("weekly_updates", dict(fields, update_key=key, email=me), me, now)
                if wellbeing:
                    w = dict(week_start=week, org_unit_key=team, wellbeing=wellbeing,
                             line_manager_email=g.person.get("line_manager_email"),
                             comments=f.get("wellbeing_comments", "").strip() or None, submitted_at=now)
                    if checkin:
                        g.repo.update("wellbeing_checkins", key, w, me, now)
                    else:
                        g.repo.insert("wellbeing_checkins", dict(w, checkin_key=key, email=me), me, now)
                # Ticking a task on a week's page means it was done that week.
                done_on = min(date.today(), week + timedelta(days=6))
                for t in tasks:
                    if t["status"] == "cancelled":
                        continue
                    done = f.get(f"done_{t['task_code']}") == "1"
                    if done and t["status"] == "open":
                        g.repo.update("tasks", t["task_code"], dict(status="complete", completed_by=me,
                                                                    completed_date=done_on), me, now)
                    elif not done and t["status"] == "complete":
                        g.repo.update("tasks", t["task_code"], dict(status="open", completed_by=None,
                                                                    completed_date=None), me, now)
            flash("Saved. Thanks for your update.")
            return redirect(url_for("weekly.my_week", week=week.isoformat(), team=team))
    return render_template(
        "weekly/my_week.html", week=week, team=team, teams=team_paths(), update=update, checkin=checkin,
        tasks=tasks, problems=team_items("problems", team, week) if team else [], names=people_names(),
        errors=errors, workload=WORKLOAD, wellbeing=WELLBEING, priority=dict(PRIORITY), levels=dict(LEVELS),
        can_edit=can_edit(), prev_week=week - timedelta(days=7), next_week=week + timedelta(days=7),
        manager=g.person.get("line_manager_email")), (400 if errors else 200)


# ---------------------------------------------------------------------------
# Tasks and problems
# ---------------------------------------------------------------------------
def _contrib(raw):
    if not raw:
        return None, None
    kind, _, key = raw.partition(":")
    if kind == "group" and g.repo.get("groups", key):
        return "group", key
    if kind == "measure" and g.repo.get("measures", key):
        return "measure", key
    return "invalid", None


def _item_form(table, item):
    """Read and validate a task or problem form. Returns (fields, errors)."""
    f = request.form
    me = g.person["email"]
    errors = {}
    ctype, ckey = _contrib(f.get("contributes_to"))
    if ctype == "invalid":
        errors["contributes_to"] = "Choose what it contributes to from the list."
        ctype = None
    status = f.get("status") or "open"
    people = {p["email"] for p in g.repo.find("people", "active = 1")}
    team = f.get("org_unit_key") or (item or {}).get("org_unit_key")
    if team not in {k for k, _ in team_paths()}:
        errors["org_unit_key"] = "Choose a team from the list."
    if table == "tasks":
        fields = dict(task_name=f.get("task_name", "").strip(), priority=f.get("priority"), org_unit_key=team,
                      contributes_to_type=ctype, contributes_to_key=ckey,
                      contributes_to_note=f.get("contributes_to_note", "").strip() or None,
                      assigned_to=f.get("assigned_to") or None, notes=f.get("notes", "").strip() or None,
                      status=status)
        for msg in rules.validate_task(fields):
            errors["task_name" if "name" in msg.lower() else "contributes_to"] = msg
        if fields["priority"] not in {k for k, _ in PRIORITY}:
            errors["priority"] = "Choose a priority."
        if status not in ("open", "complete", "cancelled"):
            errors["status"] = "Choose a status."
        if fields["assigned_to"] and fields["assigned_to"] not in people:
            errors["assigned_to"] = "Choose someone from the list."
        was = (item or {}).get("status")
        if status != was:
            fields["completed_by"] = me if status == "complete" else None
            fields["completed_date"] = date.today() if status != "open" else None
    else:
        target, err = forms.parse_field(columns("problems")["target_resolution_date"], f.get("target_resolution_date"))
        if err:
            errors["target_resolution_date"] = err
        fields = dict(problem_title=f.get("problem_title", "").strip(),
                      problem_statement=f.get("problem_statement", "").strip(), org_unit_key=team,
                      problem_owner=f.get("problem_owner") or None, impact=f.get("impact"), urgency=f.get("urgency"),
                      target_resolution_date=target, contributes_to_type=ctype, contributes_to_key=ckey,
                      resolution=f.get("resolution", "").strip() or None, notes=f.get("notes", "").strip() or None,
                      status=status)
        for msg in rules.validate_problem(fields):
            field = ("problem_title" if "title" in msg else "problem_statement" if "Describe" in msg else "resolution")
            errors[field] = msg
        for col in ("impact", "urgency"):
            if fields[col] not in {k for k, _ in LEVELS}:
                errors[col] = f"Choose the {col}."
        if status not in ("open", "closed"):
            errors["status"] = "Choose a status."
        if fields["problem_owner"] and fields["problem_owner"] not in people:
            errors["problem_owner"] = "Choose someone from the list."
        was = (item or {}).get("status")
        if status != was:
            fields["closed_date"] = date.today() if status == "closed" else None
    return fields, errors


def _item_page(table, code=None):
    key_col = "task_code" if table == "tasks" else "problem_code"
    item = g.repo.get(table, code) if code else None
    if code and item is None:
        abort(404)
    errors = {}
    week = request.values.get("week")
    if request.method == "POST":
        fields, errors = _item_form(table, item)
        if not errors:
            me = g.person["email"]
            with g.repo.transaction():
                if item:
                    g.repo.update(table, code, fields, me)
                else:
                    code = forms.make_key({"key": ("sequence", "TSK-" if table == "tasks" else "PRB-", 5)}, {},
                                          g.repo, table)
                    extra = (dict(raised_by=me, date_raised=date.today()) if table == "tasks"
                             else dict(raised_by=me, raised_on=date.today()))
                    g.repo.insert(table, dict(fields, **extra, **{key_col: code}), me)
            flash(f"{'Task' if table == 'tasks' else 'Problem'} {code} saved.")
            return redirect(url_for("weekly.my_week", week=week, team=fields["org_unit_key"]))
        item = dict(item or {}, **fields)
    elif item is None:
        item = {"org_unit_key": chosen_team(), "status": "open", "assigned_to": g.person["email"],
                "priority": "should", "impact": "medium", "urgency": "medium"}
    contrib = f"{item.get('contributes_to_type')}:{item.get('contributes_to_key')}" if item.get("contributes_to_key") else ""
    people = [(p["email"], p["display_name"]) for p in g.repo.find("people", "active = 1", order="display_name")]
    return render_template(f"weekly/{'task' if table == 'tasks' else 'problem'}.html", item=item, code=code,
                           errors=errors, teams=team_paths(), people=people, contrib=contrib,
                           contrib_options=contributes_options(), priority=PRIORITY, levels=LEVELS,
                           names=people_names(), can_edit=can_edit(), week=week), (400 if errors else 200)


@bp.route("/tasks/new", methods=["GET", "POST"])
@edit_required
def new_task():
    return _item_page("tasks")


@bp.route("/tasks/<code>", methods=["GET", "POST"])
@edit_required
def task(code):
    return _item_page("tasks", code)


@bp.route("/problems/new", methods=["GET", "POST"])
@edit_required
def new_problem():
    return _item_page("problems")


@bp.route("/problems/<code>", methods=["GET", "POST"])
@edit_required
def problem(code):
    return _item_page("problems", code)


# ---------------------------------------------------------------------------
# My team
# ---------------------------------------------------------------------------
def setting_int(key, default):
    row = g.repo.get("settings", key)
    try:
        return int(row["setting_value"]) if row else default
    except ValueError:
        return default


@bp.route("/team")
@auth.login_required
def my_team():
    week, team = chosen_week(), chosen_team()
    names = people_names()
    members = sorted((p for p in g.repo.find("people", "active = 1 AND org_unit_key = ?", (team,))),
                     key=lambda p: p["display_name"].lower())
    updates = g.repo.find("weekly_updates", "org_unit_key = ? AND week_start = ?", (team, week.isoformat()))
    by_person = {u["email"]: u for u in updates}
    checkins = g.repo.find("wellbeing_checkins", "week_start = ? AND (org_unit_key = ? OR line_manager_email = ?)",
                           (week.isoformat(), team, g.person["email"]))
    view = rules.wellbeing_view(checkins, g.person["email"], team, week, max(3, setting_int("wellbeing_min_group_size", 5)))
    reports = sorted(g.repo.find("people", "active = 1 AND line_manager_email = ?", (g.person["email"],)),
                     key=lambda p: p["display_name"].lower())
    report_answers = {r["email"]: r for r in view["direct_reports"]}
    workload = {k: sum(1 for u in updates if u["workload"] == k) for k, _ in WORKLOAD}
    return render_template("weekly/my_team.html", week=week, team=team, teams=team_paths(), members=members,
                           by_person=by_person, updates=updates, names=names, view=view, reports=reports,
                           report_answers=report_answers, workload=workload, workload_labels=WORKLOAD,
                           wellbeing_labels=dict(WELLBEING), prev_week=week - timedelta(days=7),
                           next_week=week + timedelta(days=7),
                           min_group=max(3, setting_int("wellbeing_min_group_size", 5)))
