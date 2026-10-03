"""Export definitions and the reference export transform.

Every export (on demand or scheduled) is one of the DATASETS below. Each
dataset is a set of tidy tables: one row per record, snake_case headers,
ISO dates, numbers as numbers, blanks as blanks, and lookup columns (names,
labels) filled in so each file stands on its own.

The Office Script (office_scripts/PMSExport.ts) does exactly what
transform() and to_csv() do here; tests/test_exports.py runs both on the
same input and checks the output is identical.
"""
from datetime import date, datetime, timedelta, timezone

from .schema import LISTS_BY_NAME

# ---------------------------------------------------------------------------
# Column helpers
# ---------------------------------------------------------------------------
TYPE_MAP = {"text": "text", "note": "text", "choice": "text", "number": "number",
            "integer": "number", "bool": "bool", "date": "date", "datetime": "datetime"}


def _cols(list_name, include=None, exclude=()):
    lst = LISTS_BY_NAME[list_name]
    out = []
    for i, c in enumerate(lst.all_columns):
        if (include and c.name not in include) or c.name in exclude:
            continue
        out.append(dict(name=c.name, source="Title" if i == 0 else c.name,
                        type=TYPE_MAP[c.type], description=c.description))
    if include:
        order = {n: i for i, n in enumerate(include)}
        out.sort(key=lambda c: order[c["name"]])
    return out


def _lookup(name, from_field, tables, description):
    """A column filled from another table. tables: [(lookup_table, field)],
    tried in order; the lookup table's key is always its Title."""
    return dict(name=name, lookup_from=from_field, type="text", description=description,
                lookup=[dict(table=t, field=f) for t, f in tables])


PERSON = [("people", "display_name")]
TEAM = [("org_units", "unit_name")]
CONTRIB = [("groups", "group_name"), ("measures", "measure_name")]

# Small reference tables the flow reads once per export and passes to the
# script for lookups.
LOOKUP_TABLES = {
    "people": ["display_name"],
    "org_units": ["unit_name"],
    "groups": ["group_name"],
    "measures": ["measure_name"],
}


def _table(name, list_name, columns, filter_="", main=False):
    return dict(name=name, list=list_name, columns=columns, filter=filter_, main=main)


WEEKLY_UPDATE_COLS = (
    _cols("weekly_updates", ["update_key", "week_start", "email"])
    + [_lookup("person_name", "email", PERSON, "Name of the person."),
       dict(_cols("weekly_updates", ["org_unit_key"])[0]),
       _lookup("team_name", "org_unit_key", TEAM, "Team name.")]
    + _cols("weekly_updates", ["successes", "communication", "workload", "submitted_at"])
)
TASK_COLS = (
    _cols("tasks", ["task_code", "task_name", "priority", "status", "org_unit_key"])
    + [_lookup("team_name", "org_unit_key", TEAM, "Team name.")]
    + _cols("tasks", ["contributes_to_type", "contributes_to_key"])
    + [_lookup("contributes_to_name", "contributes_to_key", CONTRIB, "Name of the group or measure the task supports.")]
    + _cols("tasks", ["contributes_to_note", "raised_by"])
    + [_lookup("raised_by_name", "raised_by", PERSON, "Who raised it.")]
    + _cols("tasks", ["date_raised", "assigned_to"])
    + [_lookup("assigned_to_name", "assigned_to", PERSON, "Who is doing it.")]
    + _cols("tasks", ["completed_by"])
    + [_lookup("completed_by_name", "completed_by", PERSON, "Who completed it.")]
    + _cols("tasks", ["completed_date", "notes"])
)
PROBLEM_COLS = (
    _cols("problems", ["problem_code", "problem_title", "problem_statement", "status", "impact", "urgency", "org_unit_key"])
    + [_lookup("team_name", "org_unit_key", TEAM, "Team name.")]
    + _cols("problems", ["raised_by"])
    + [_lookup("raised_by_name", "raised_by", PERSON, "Who raised it.")]
    + _cols("problems", ["raised_on", "problem_owner"])
    + [_lookup("problem_owner_name", "problem_owner", PERSON, "Who owns resolving it.")]
    + _cols("problems", ["target_resolution_date", "closed_date", "resolution", "contributes_to_type", "contributes_to_key"])
    + [_lookup("contributes_to_name", "contributes_to_key", CONTRIB, "Name of the group or measure affected.")]
    + _cols("problems", ["notes"])
)

# Filter tokens the flow replaces for quarter packs.
QUARTER_WINDOW = "gt '{window_start}' and {col} le '{window_end}'"


def _in_quarter(col):
    return f"{col} " + QUARTER_WINDOW.replace("{col}", col)


DATASETS = {
    "full_model": dict(
        title="Full data model",
        description="Every table in the model, for Power BI, Excel or AI tools. Approved values only; "
                    "review comments, wellbeing and the audit log are never included.",
        tables=[
            _table("measures", "measures", _cols("measures")),
            _table("periods", "periods", _cols("periods")),
            _table("measure_roles", "measure_roles", _cols("measure_roles")),
            _table("people", "people", _cols("people", exclude=("line_manager_email",))),
            _table("org_units", "org_units", _cols("org_units")),
            _table("groups", "groups", _cols("groups")),
            _table("measure_links", "measure_links", _cols("measure_links")),
            _table("reference_values", "reference_values", _cols("reference_values")),
            _table("submissions", "submissions", _cols("submissions")),
            _table("approved_values", "submission_versions",
                   _cols("submission_versions", exclude=("version_status", "entered_by", "entered_date")),
                   "version_status eq 'approved'"),
            _table("values_flat", "rpt_values", _cols("rpt_values")),
            _table("weekly_updates", "weekly_updates", WEEKLY_UPDATE_COLS),
            _table("tasks", "tasks", TASK_COLS),
            _table("problems", "problems", PROBLEM_COLS),
        ],
    ),
    "measures": dict(
        title="Measure values",
        description="One row per approved measure per period, with measure, owner, period, targets and RAG "
                    "filled in. Works on its own with no joins.",
        tables=[_table("values_flat", "rpt_values", _cols("rpt_values"), main=True)],
    ),
    "weekly_work": dict(
        title="Weekly work",
        description="Weekly updates (successes, communication, workload), tasks and problems, with names filled in. "
                    "Wellbeing is never included.",
        tables=[
            _table("weekly_updates", "weekly_updates", WEEKLY_UPDATE_COLS, main=True),
            _table("tasks", "tasks", TASK_COLS, main=True),
            _table("problems", "problems", PROBLEM_COLS, main=True),
        ],
    ),
    "quarter_pack": dict(
        title="Quarterly report pack",
        description="Everything needed to write the quarterly report for one financial quarter: the quarter's "
                    "approved values, the latest value of every measure, work completed, open work, problems, "
                    "and successes. Comes with a prompt for drafting the report with AI.",
        tables=[
            _table("quarter_values", "rpt_values", _cols("rpt_values"), "financial_quarter eq '{quarter_label}'"),
            _table("latest_values", "rpt_values", _cols("rpt_values"), "is_latest eq 1"),
            _table("tasks", "tasks", TASK_COLS,
                   f"({_in_quarter('completed_date')}) or status eq 'open'"),
            _table("problems", "problems", PROBLEM_COLS,
                   f"({_in_quarter('raised_on')}) or ({_in_quarter('closed_date')}) or status eq 'open'"),
            _table("weekly_updates", "weekly_updates", WEEKLY_UPDATE_COLS, _in_quarter("week_start")),
        ],
    ),
}


def select_fields(table):
    fields = ["Title"]
    for c in table["columns"]:
        f = c.get("source") or c.get("lookup_from")
        if f not in fields:
            fields.append(f)
    return ",".join(fields)


def dictionary_rows(dataset):
    rows = []
    for t in DATASETS[dataset]["tables"]:
        for c in t["columns"]:
            rows.append([t["name"], c["name"], c["type"], c["description"]])
    return rows


DICTIONARY_HEADERS = ["table_name", "column_name", "data_type", "description"]
DICTIONARY_TABLE = dict(name="data_dictionary", columns=[
    dict(name=h, type="text", description="") for h in DICTIONARY_HEADERS])


# ---------------------------------------------------------------------------
# Transform: rows -> tidy export rows
# ---------------------------------------------------------------------------
def _last_sunday_utc(year, month):
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    d -= timedelta(days=(d.weekday() + 1) % 7)
    return datetime(d.year, d.month, d.day, 1, tzinfo=timezone.utc)


def _parse_utc(iso):
    s = iso.replace("Z", "+00:00")
    if "." in s:
        head, tail = s.split(".", 1)
        tz = tail[tail.find("+"):] if "+" in tail else ""
        s = head + tz
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def uk_date(iso):
    """SharePoint returns date-only values as a UTC instant (midnight UK
    time, or midday UTC in the seed data). Turn it back into the UK date."""
    dt = _parse_utc(iso)
    bst = _last_sunday_utc(dt.year, 3) <= dt < _last_sunday_utc(dt.year, 10)
    return (dt + timedelta(hours=1 if bst else 0)).date().isoformat()


def utc_datetime(iso):
    return _parse_utc(iso).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lookup_maps(lookups):
    return {t: {row["Title"]: row for row in rows} for t, rows in lookups.items()}


def cell(col, item, maps):
    if col.get("lookup"):
        key = item.get(col["lookup_from"])
        if key in (None, ""):
            return ""
        for lk in col["lookup"]:
            row = maps.get(lk["table"], {}).get(key)
            if row and row.get(lk["field"]) not in (None, ""):
                return row[lk["field"]]
        return ""
    v = item.get(col["source"])
    if v is None or v == "":
        return ""
    t = col["type"]
    if t == "date":
        return uk_date(v)
    if t == "datetime":
        return utc_datetime(v)
    if t == "number":
        n = float(v)
        return int(n) if n == int(n) else n
    if t == "bool":
        return v is True or v == "true"
    return str(v)


def transform(table, items, lookups):
    maps = _lookup_maps(lookups)
    headers = [c["name"] for c in table["columns"]]
    rows = [[cell(c, it, maps) for c in table["columns"]] for it in items]
    return headers, rows


def csv_field(v):
    if v == "" or v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    s = str(v)
    if any(ch in s for ch in ',"\r\n') or s != s.strip():
        return '"' + s.replace('"', '""') + '"'
    return s


def to_csv(headers, rows, include_header=True):
    lines = [",".join(headers)] if include_header else []
    lines += [",".join(csv_field(v) for v in r) for r in rows]
    return "".join(line + "\r\n" for line in lines)


# ---------------------------------------------------------------------------
# Scheduling helpers (the scheduler flow mirrors these)
# ---------------------------------------------------------------------------
def previous_fy_quarter(today):
    """Label of the last completed financial quarter, e.g. '2026-27 Q2'."""
    fy = today.year if today.month >= 4 else today.year - 1
    q = (today.month - 4) % 12 // 3 + 1
    if q == 1:
        fy, q = fy - 1, 4
    else:
        q -= 1
    return f"{fy}-{str(fy + 1)[-2:]} Q{q}"


def job_due(job, today):
    """Is an export_jobs row due to run today?"""
    if not job["active"]:
        return False
    f = job["frequency"]
    if f == "daily":
        return True
    if f == "weekly":
        return today.isoweekday() == job["run_day"]
    if f == "monthly":
        return today.day == job["run_day"]
    if f == "quarterly":
        return today.month in (1, 4, 7, 10) and today.day == job["run_day"]
    return False


# ---------------------------------------------------------------------------
# Files written alongside every export
# ---------------------------------------------------------------------------
READING_RULES = """## How to read this data

- Every file is tidy: one row per record, one column per field, a single header row, no merged cells and no totals.
- Column names are snake_case and mean the same thing in every file. `data_dictionary.csv` (or the `data_dictionary` sheet) describes every column.
- Dates are `YYYY-MM-DD` (UK dates). Date-times are UTC in ISO 8601, for example `2026-09-30T06:00:00Z`.
- Numbers are plain numbers. A blank cell means there is no value; it never means zero.
- `percent` values are 0 to 100, so 58 means 58%. `gbp` is pounds. `yes_no` is 1 (yes) or 0 (no). `text` measures use `value_text`.
- Only **approved** values are included. Drafts, returned values and reviewer comments are not.
- `measure_code` (for example PM-0007) is the unique key for a measure. `source_ref` is the reference used in the source document and can repeat.
- The financial year runs April to March. `financial_quarter` looks like `2026-27 Q2` (Q1 is April to June).
- `rag_status`: `green` is on or better than target; `amber` is short of target but within tolerance; `red` is off track; `no_target` means no target was set; `no_data` means no value was provided; `not_applicable` means RAG isn't used for that measure.
- `polarity` says whether higher or lower is better. `aggregation_method` says how to combine values into a longer period: sum, average, latest, max or min. `do_not_combine` means the values must not be added up or averaged.
- `is_latest` is true on the most recent approved period for each measure.
- Individual wellbeing, reviewer comments and the audit log are never included in exports.
"""

JOINS = """## How the tables join

| From | Column | To |
|---|---|---|
| any table | `measure_code` | `measures.measure_code` |
| any table | `period_key` | `periods.period_key` |
| measures | `parent_measure_code` | `measures.measure_code` (parent summary measure) |
| submissions, approved_values | `submission_key` | `submissions.submission_key` |
| measure_links | `group_key` | `groups.group_key` |
| measure_roles, weekly_updates | `email` | `people.email` |
| most tables | `org_unit_key` | `org_units.org_unit_key` |
| tasks, problems | `contributes_to_key` | `groups.group_key` or `measures.measure_code` (see `contributes_to_type`) |

`values_flat` already has every lookup filled in, so for most questions it's the only table you need.
"""


def readme_for(dataset):
    d = DATASETS[dataset]
    lines = [f"# {d['title']}", "", d["description"], "",
             "The folder name and `export_info.txt` say when the export ran and what filter was used.", "",
             "## Files", ""]
    for t in d["tables"]:
        src = LISTS_BY_NAME[t["list"]].description
        lines.append(f"- `{t['name']}.csv` (sheet `{t['name']}` in the Excel file): {src}")
    lines += ["- `data_dictionary.csv` (sheet `data_dictionary`): every column in this export, with its type and meaning.",
              "- `README_for_AI.md`: this file."]
    if dataset == "quarter_pack":
        lines.append("- `prompt_quarterly_report.md`: a prompt for drafting the quarterly report from these files.")
    lines += ["", READING_RULES]
    if dataset == "full_model":
        lines += [JOINS]
    if dataset == "quarter_pack":
        lines += ["## What's in each table", "",
                  "- `quarter_values`: approved values for periods that start in the quarter (daily, weekly, fortnightly, monthly and quarterly measures).",
                  "- `latest_values`: the latest approved value of every measure, which covers annual, calendar-year, academic-year and term measures.",
                  "- `tasks`: tasks completed in the quarter, plus everything still open.",
                  "- `problems`: problems raised or closed in the quarter, plus everything still open.",
                  "- `weekly_updates`: successes, communication and workload from every weekly update in the quarter.", ""]
    return "\n".join(lines)


QUARTER_PROMPT = """# Prompt: draft the quarterly performance report

Use this with Microsoft 365 Copilot or any other AI tool your organisation allows. Attach, or point it at, the files in this folder, then paste everything below the line.

You can also use the pack without AI: open the Excel file and work through the sheets in the order of the report sections below.

---

You are helping write the quarterly performance report for {quarter}. Use **only** the attached files. Read `README_for_AI.md` and `data_dictionary.csv` first so you understand every column.

Write the report in plain UK English, for senior leaders who have two minutes. Use these sections:

1. **Summary** (five bullet points at most): overall position, the biggest improvement, the biggest concern, and what needs a decision.
2. **Measures**, grouped by `category`:
   - a table with measure (`source_ref` and `measure_name`), latest value with its unit, target, RAG and the direction of travel from the previous period;
   - for every red or amber measure, one or two sentences from its `narrative` explaining why and what is being done.
3. **Delivery**: the main work completed this quarter (`tasks` with `status` complete), grouped by what it `contributes_to_name`, and notable successes from `weekly_updates`.
4. **Problems and risks**: open problems with high impact or high urgency, who owns them and their target date, then problems resolved this quarter.
5. **Data notes**: measures with `no_data`, values marked `provisional` or `estimated` in `data_quality`, and measures with no target.

Rules:
- Never invent or estimate numbers. If something isn't in the files, say "not available".
- Quote measure codes (for example PM-0007) so every statement can be checked.
- Percentages are stored as 0 to 100: show 58 as 58%.
- Use `polarity` when you describe change: for lower-is-better measures, a fall is an improvement.
- Use `aggregation_method` if you combine monthly or weekly values into a quarter figure, and say that you did.
- Don't name individuals when you describe problems or workload; use team names.
- Finish with a short list of questions the report owner should check before publishing.
"""


def definitions_json():
    """What the export flow reads: every dataset, its tables, the $select
    for each list, filters, dictionary rows and the text files to write."""
    out = {"lookup_tables": {t: dict(list=t, select="Title," + ",".join(f)) for t, f in LOOKUP_TABLES.items()},
           "datasets": {}}
    for name, d in DATASETS.items():
        out["datasets"][name] = dict(
            title=d["title"],
            tables=[dict(name=t["name"], list=t["list"], select=select_fields(t), filter=t["filter"],
                         main=t["main"], columns=t["columns"]) for t in d["tables"]],
            dictionary=dictionary_rows(name),
            readme=readme_for(name),
            prompt=QUARTER_PROMPT if name == "quarter_pack" else "",
        )
    return out


# ---------------------------------------------------------------------------
# Sample exports from the seed data (what the flow would produce)
# ---------------------------------------------------------------------------
def sp_items(list_name, rows):
    """Seed rows in the shape SharePoint REST returns (odata=nometadata)."""
    lst = LISTS_BY_NAME[list_name]
    out = []
    for r in rows:
        item = {}
        for i, c in enumerate(lst.all_columns):
            v = r.get(c.name)
            if isinstance(v, datetime):
                v = v.strftime("%Y-%m-%dT%H:%M:%SZ")
            elif isinstance(v, date):
                v = f"{v.isoformat()}T12:00:00Z"
            item["Title" if i == 0 else c.name] = v
        out.append(item)
    return out


def _in(d, lo, hi):
    return d is not None and lo <= d <= hi


def sample_filter(dataset, table, row, quarter):
    """Python equivalent of each table's OData filter, for the samples."""
    q_from, q_to = quarter["start_date"], quarter["end_date"]
    rules = {
        ("full_model", "approved_values"): lambda r: r["version_status"] == "approved",
        ("quarter_pack", "quarter_values"): lambda r: r["financial_quarter"] == quarter["financial_quarter"],
        ("quarter_pack", "latest_values"): lambda r: r["is_latest"],
        ("quarter_pack", "tasks"): lambda r: _in(r["completed_date"], q_from, q_to) or r["status"] == "open",
        ("quarter_pack", "problems"): lambda r: (_in(r["raised_on"], q_from, q_to) or _in(r["closed_date"], q_from, q_to)
                                                 or r["status"] == "open"),
        ("quarter_pack", "weekly_updates"): lambda r: _in(r["week_start"], q_from, q_to),
    }
    return rules.get((dataset, table["name"]), lambda r: True)(row)


def build_samples(data, as_of):
    """{dataset: {filename: text}} for every dataset, from seed data."""
    label = previous_fy_quarter(as_of + timedelta(days=1))  # the pack runs just after the quarter ends
    quarter = next(p for p in data["periods"] if p["period_type"] == "quarterly" and p["financial_quarter"] == label)
    lookups = {t: sp_items(t, data[t]) for t in LOOKUP_TABLES}
    out = {}
    for name, d in DATASETS.items():
        files = {}
        for t in d["tables"]:
            rows = [r for r in data[t["list"]] if sample_filter(name, t, r, quarter)]
            headers, cells = transform(t, sp_items(t["list"], rows), lookups)
            files[f"{t['name']}.csv"] = "﻿" + to_csv(headers, cells)
        files["data_dictionary.csv"] = "﻿" + to_csv(DICTIONARY_HEADERS, dictionary_rows(name))
        files["README_for_AI.md"] = readme_for(name)
        info = [f"dataset: {name}", f"created_at: {as_of.isoformat()}T06:00:00Z (sample built from seed data)",
                "filter: " + (f"financial quarter {label}" if name == "quarter_pack" else "everything")]
        files["export_info.txt"] = "\n".join(info) + "\n"
        if name == "quarter_pack":
            files["prompt_quarterly_report.md"] = QUARTER_PROMPT.replace("{quarter}", label)
        out[name] = files
    return out
