"""Business rules, written once here as the reference implementation.

The Power Apps formulas and Power Automate flows in later phases must behave
exactly like these functions; the tests pin the behaviour down.
"""
from datetime import timedelta

OFF_TRACK = {"amber", "red"}


def rag_status(measure, value_number, value_missing, target=None, tolerance=None):
    """RAG for one value.

    - text measures and polarity "neither": not_applicable
    - no value: no_data
    - tolerance is ignored unless the measure is a kpi or okr
    - no target and no tolerance: no_target
    - higher_is_better: green at or above target, amber at or above tolerance,
      otherwise red (lower_is_better is the mirror image)
    - only a tolerance: green if at or better than it, otherwise red
    """
    if measure["unit"] == "text" or measure["polarity"] == "neither":
        return "not_applicable"
    if value_missing or value_number is None:
        return "no_data"
    if measure["measure_class"] not in ("kpi", "okr"):
        tolerance = None
    if target is None and tolerance is None:
        return "no_target"

    if measure["polarity"] == "higher_is_better":
        def at_least(x):
            return value_number >= x
    else:
        def at_least(x):
            return value_number <= x

    if target is not None:
        if at_least(target):
            return "green"
        if tolerance is not None and at_least(tolerance):
            return "amber"
        return "red"
    return "green" if at_least(tolerance) else "red"


def validate_value(measure, value_number, value_text, value_missing, narrative, rag):
    """Return a list of problems with a value, empty if it can be submitted."""
    errors = []
    unit = measure["unit"]
    has_narrative = bool(narrative and narrative.strip())
    if value_missing:
        if value_number is not None or value_text:
            errors.append("A missing value must be left blank.")
        if not has_narrative:
            errors.append("Narrative is required when the value is missing.")
        return errors
    if unit == "text":
        if not value_text:
            errors.append("Enter a text value.")
        if value_number is not None:
            errors.append("Text measures take a text value only.")
    else:
        if value_text:
            errors.append("This measure takes a number, not text.")
        if value_number is None:
            errors.append("Enter a value or mark it as missing.")
        elif unit == "yes_no" and value_number not in (0, 1):
            errors.append("Yes/no values must be 1 (yes) or 0 (no).")
        elif unit == "count" and (value_number < 0 or value_number != int(value_number)):
            errors.append("Counts must be whole numbers of 0 or more.")
    if rag in OFF_TRACK and not has_narrative:
        errors.append("Narrative is required when the value is off track.")
    return errors


def expected_by(period_end, lag_days):
    if lag_days is None:
        return None
    return period_end + timedelta(days=lag_days)


# ---------------------------------------------------------------------------
# Weekly work
# ---------------------------------------------------------------------------
PRIORITY_LABELS = {"must": "Must do", "should": "Should do", "could": "Could do"}


def week_start(d):
    """Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def tasks_for_week(tasks, org_unit_key, week):
    """Tasks shown on a team's week: every open task (they carry over until
    closed) plus anything completed or cancelled during that week."""
    week_end = week + timedelta(days=6)
    shown = [t for t in tasks if t["org_unit_key"] == org_unit_key and (
        t["status"] == "open"
        or (t["completed_date"] is not None and week <= t["completed_date"] <= week_end))]
    return sorted(shown, key=lambda t: (t["status"] != "open", t["date_raised"], t["task_code"]))


def problems_for_week(problems, org_unit_key, week):
    week_end = week + timedelta(days=6)
    shown = [p for p in problems if p["org_unit_key"] == org_unit_key and (
        p["status"] == "open"
        or (p["closed_date"] is not None and week <= p["closed_date"] <= week_end))]
    return sorted(shown, key=lambda p: (p["status"] != "open", p["raised_on"], p["problem_code"]))


def wellbeing_view(checkins, caller_email, org_unit_key, week, min_group_size):
    """What one person may see about wellbeing for a week.

    - individual responses only where the caller is the recorded line manager
    - team counts only when at least min_group_size people in the team responded
    """
    in_week = [c for c in checkins if c["week_start"] == week]
    team = [c for c in in_week if c["org_unit_key"] == org_unit_key]
    show = len(team) >= min_group_size
    counts = {w: sum(1 for c in team if c["wellbeing"] == w) for w in ("thriving", "ok", "struggling")}
    return {
        "responses": len(team),
        "show_counts": show,
        "counts": counts if show else None,
        "direct_reports": sorted(
            ({"email": c["email"], "wellbeing": c["wellbeing"], "comments": c["comments"]}
             for c in in_week if c["line_manager_email"] == caller_email),
            key=lambda r: r["email"]),
    }


def validate_task(task):
    errors = []
    name = (task.get("task_name") or "").strip()
    if not name:
        errors.append("Enter a task name.")
    elif len(name) > 255:
        errors.append("Task name must be 255 characters or fewer.")
    if bool(task.get("contributes_to_type")) != bool(task.get("contributes_to_key")):
        errors.append("Choose what the task contributes to, or leave it blank.")
    return errors


def validate_problem(problem):
    errors = []
    if not (problem.get("problem_title") or "").strip():
        errors.append("Enter a short title.")
    if not (problem.get("problem_statement") or "").strip():
        errors.append("Describe the problem.")
    if problem.get("status") == "closed" and not (problem.get("resolution") or "").strip():
        errors.append("Say how the problem was resolved before closing it.")
    return errors
