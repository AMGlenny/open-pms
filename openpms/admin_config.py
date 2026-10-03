"""Which tables admins manage directly, and how each one behaves.

Everything else (values, versions, weekly updates, tasks, wellbeing, the
audit log) is written only by the app's own screens and rules.

key: how a new row's key is made
  ("manual", hint)            admin types it
  ("sequence", prefix, digits) next number, e.g. PM-0023
  ("template", "{a}|{b}")     built from other fields
app_fields: columns only the app writes, shown but never edited
"""
ADMIN_TABLES = {
    "measures": dict(
        title="Measures", key=("sequence", "PM-", 4), label="measure_name",
        list_cols=["measure_code", "source_ref", "measure_name", "measure_class", "frequency", "status"],
        search=["measure_code", "source_ref", "measure_name"], inactive=("status", "retired"),
        help="Retire a measure instead of deleting it: its history stays in reports and exports."),
    "measure_roles": dict(
        title="Measure roles", key=("template", "{measure_code}|{email}|{role}"), label="role_key",
        list_cols=["measure_code", "email", "role", "active"], search=["measure_code", "email"],
        inactive=("active", False),
        help="Each measure needs exactly one active owner, at least one updater and at least one approver."),
    "measure_links": dict(
        title="Measure links", key=("template", "{measure_code}|{group_key}"), label="link_key",
        list_cols=["measure_code", "group_key", "relationship_type", "active"], search=["measure_code", "group_key"],
        inactive=("active", False), help="Link measures to the themes, programmes and objectives they serve."),
    "reference_values": dict(
        title="Targets and reference values", key=("template", "{measure_code}|{period_key}|{ref_type}"),
        label="ref_key", list_cols=["measure_code", "period_key", "ref_type", "ref_value", "active"],
        search=["measure_code", "period_key"], inactive=("active", False),
        help="Optional. Tolerance only applies to KPIs and OKRs."),
    "people": dict(
        title="People", key=("manual", "Their work email address. It's also their sign-in."), label="display_name",
        list_cols=["display_name", "email", "org_unit_key", "app_role", "active"],
        search=["email", "display_name"], inactive=("active", False),
        help="Leavers are made inactive, never deleted, so their history stays linked."),
    "org_units": dict(
        title="Teams", key=("manual", "A short code, for example TM-HSG."), label="unit_name",
        list_cols=["org_unit_key", "unit_name", "unit_level", "parent_key", "active"],
        search=["org_unit_key", "unit_name"], inactive=("active", False)),
    "groups": dict(
        title="Themes, programmes and objectives", key=("manual", "A short code, for example TH-JOBS."),
        label="group_name", list_cols=["group_key", "group_name", "group_type", "active"],
        search=["group_key", "group_name"], inactive=("active", False)),
    "periods": dict(
        title="Periods and term dates", key=("manual", "For a term: T-<academic year>-<code>, for example T-2026-27-AUT."),
        label="period_label", list_cols=["period_key", "period_type", "period_label", "start_date", "end_date"],
        search=["period_key", "period_label", "period_type"], order="start_date DESC",
        help="Most periods are created for you a year at a time. Edit term dates here when they're published."),
    "lookups": dict(
        title="Pick lists", key=("template", "{lookup_type}|{code}"), label="label",
        list_cols=["lookup_type", "code", "label", "sort_order", "active"], search=["code", "label"],
        inactive=("active", False)),
    "export_jobs": dict(
        title="Scheduled exports", key=("manual", "A short code, for example EXP-FULL-NIGHTLY."), label="job_name",
        list_cols=["job_code", "job_name", "dataset", "frequency", "active", "last_run_status"],
        search=["job_code", "job_name"], inactive=("active", False), app_fields=("last_run_at", "last_run_status"),
        help="Each job writes files to the snapshot folder on the server. See Exports > Scheduled exports."),
    "settings": dict(
        title="Settings", key=("manual", "Setting name."), label="setting_key",
        list_cols=["setting_key", "setting_value", "description"], search=["setting_key"]),
}

# How to show a key from another table in dropdowns: (table, label column).
REF_LABELS = {
    "measures": "measure_name", "people": "display_name", "org_units": "unit_name",
    "groups": "group_name", "periods": "period_label", "lookups": "label",
}

# Reference columns with too many options for a dropdown: typed, with suggestions.
LARGE_REFS = {"periods"}
