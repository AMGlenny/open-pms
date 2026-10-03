"""Turns form input into typed, validated rows, using schema.py.

Error messages follow one pattern: say what's wrong and how to fix it.
"""
import re
from datetime import date

from .schema import LISTS_BY_NAME

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def label(name):
    return name.replace("_", " ").capitalize().replace(" kpi", " KPI").replace("Fy ", "FY ")


def parse_field(col, raw):
    """Returns (value, error)."""
    if col.type == "bool":
        return raw in ("1", "on", "true", "yes"), None
    raw = (raw or "").strip()
    if raw == "":
        return None, (f"Enter {label(col.name).lower()}." if col.required else None)
    if col.type in ("number", "integer"):
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            return None, f"{label(col.name)} must be a number."
        if col.type == "integer":
            if not v.is_integer():
                return None, f"{label(col.name)} must be a whole number."
            return int(v), None
        return (int(v) if v.is_integer() else v), None
    if col.type == "date":
        try:
            return date.fromisoformat(raw), None
        except ValueError:
            return None, f"{label(col.name)} must be a real date."
    if col.type == "choice":
        if raw not in col.choices:
            return None, f"Choose {label(col.name).lower()} from the list."
        return raw, None
    if col.type == "text" and len(raw) > 255:
        return None, f"{label(col.name)} must be 255 characters or fewer."
    return raw, None


def make_key(conf, values, repo, table):
    kind = conf["key"][0]
    if kind == "template":
        try:
            return conf["key"][1].format(**{k: ("" if v is None else v) for k, v in values.items()})
        except KeyError:
            return None
    if kind == "sequence":
        prefix, digits = conf["key"][1], conf["key"][2]
        key_col = LISTS_BY_NAME[table].key
        rows = repo.conn.execute(f"SELECT {key_col} FROM {table} WHERE org_id = ? AND {key_col} LIKE ?",
                                 (repo.org_id, prefix + "%")).fetchall()
        nums = [int(r[0][len(prefix):]) for r in rows if r[0][len(prefix):].isdigit()]
        return f"{prefix}{(max(nums) + 1 if nums else 1):0{digits}d}"
    return None


def check_refs(repo, table, values):
    errors = {}
    for col in LISTS_BY_NAME[table].columns:
        v = values.get(col.name)
        if not col.ref or v in (None, ""):
            continue
        ref_table, ref_col = col.ref.split(".")
        ref_key = LISTS_BY_NAME[ref_table].key
        if ref_col == ref_key:
            exists = repo.get(ref_table, v) is not None
        else:
            exists = repo.count(ref_table, f"{ref_col} = ?", (v,)) > 0
        if not exists:
            errors[col.name] = f"There's no {label(ref_table).lower().rstrip('s')} with the code {v}."
    return errors


def table_rules(repo, table, values, key):
    """Rules that span fields or rows. Returns {field: message}."""
    e = {}
    if table == "people":
        email = (values.get("email") or "").lower()
        if email and not EMAIL.match(email):
            e["email"] = "Enter an email address in the right format, like name@example.org."
        if values.get("line_manager_email") and values.get("line_manager_email") == email:
            e["line_manager_email"] = "Someone can't be their own line manager."
    if table == "measures":
        if values.get("parent_measure_code") and values.get("parent_measure_code") == key:
            e["parent_measure_code"] = "A measure can't be its own parent."
    if table == "measure_roles" and values.get("role") == "owner" and values.get("active"):
        others = [r for r in repo.by("measure_roles", measure_code=values.get("measure_code"), role="owner", active=True)
                  if r["role_key"] != key]
        if others:
            e["role"] = f"{values.get('measure_code')} already has an owner ({others[0]['email']}). Make that role inactive first."
    if table == "reference_values" and values.get("ref_type") == "tolerance":
        m = repo.get("measures", values.get("measure_code") or "")
        if m and m["measure_class"] not in ("kpi", "okr"):
            e["ref_type"] = "Tolerance only applies to KPIs and OKRs. Use a target instead, or change the measure's class."
    if table == "periods" and values.get("start_date") and values.get("end_date"):
        if values["end_date"] < values["start_date"]:
            e["end_date"] = "The end date must be on or after the start date."
    if table == "settings":
        k = key or values.get("setting_key")
        v = values.get("setting_value")
        if k in ("fy_start_month", "ay_start_month") and (not str(v).isdigit() or not 1 <= int(v) <= 12):
            e["setting_value"] = "Enter a month number from 1 (January) to 12 (December)."
        if k == "wellbeing_min_group_size" and (not str(v).isdigit() or int(v) < 3):
            e["setting_value"] = "Enter a whole number of 3 or more, so individuals can't be identified."
    return e
