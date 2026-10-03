"""Admin screens, generated from schema.py and admin_config.py.

Every change goes through Repo.insert/update, so it's validated by the
database and written to the audit log. There is no delete button: rows
are retired or made inactive.
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import auth, db, forms, periods
from .admin_config import ADMIN_TABLES, LARGE_REFS, REF_LABELS
from .schema import LISTS_BY_NAME

bp = Blueprint("admin", __name__, url_prefix="/admin")
PAGE_SIZE = 50


def _conf(table):
    if table not in ADMIN_TABLES:
        abort(404)
    return ADMIN_TABLES[table]


def _options(col):
    """Dropdown options for a choice or reference column: [(value, text)]."""
    if col.choices:
        return [(c, forms.label(c)) for c in col.choices]
    if col.ref:
        ref_table, ref_col = col.ref.split(".")
        if ref_table in LARGE_REFS:
            return None
        lbl = REF_LABELS.get(ref_table)
        rows = g.repo.find(ref_table)
        if ref_table == "lookups":
            rows = [r for r in rows if r["lookup_type"] == "category"]
        out = []
        for r in rows:
            v = r[ref_col]
            text = f"{r[lbl]} ({v})" if lbl and r.get(lbl) and r[lbl] != v else v
            out.append((v, text))
        return sorted(out, key=lambda o: o[1].lower())
    return None


def _fields(table, conf, row=None, creating=False):
    lst = LISTS_BY_NAME[table]
    fields = []
    for i, col in enumerate(lst.all_columns):
        is_key = i == 0
        if is_key and conf["key"][0] != "manual":
            continue
        fields.append(dict(col=col, name=col.name, label=forms.label(col.name), hint=col.description,
                           value=None if row is None else row.get(col.name),
                           readonly=(is_key and not creating) or col.name in conf.get("app_fields", ()),
                           options=_options(col)))
    return fields


def _read_form(table, conf, creating, existing=None):
    lst = LISTS_BY_NAME[table]
    values, errors = {}, {}
    for i, col in enumerate(lst.all_columns):
        if i == 0 or col.name in conf.get("app_fields", ()):
            continue
        v, err = forms.parse_field(col, request.form.get(col.name))
        values[col.name] = v
        if err:
            errors[col.name] = err
    if conf["key"][0] == "manual":
        if creating:
            key, err = forms.parse_field(lst.all_columns[0], request.form.get(lst.key))
            if table == "people" and key:
                key = key.lower()
            if err:
                errors[lst.key] = err
        else:
            key = existing[lst.key]
    elif creating:
        key = forms.make_key(conf, values, g.repo, table)
    else:
        key = existing[lst.key]
    values[lst.key] = key
    if not errors:
        errors.update(forms.check_refs(g.repo, table, values))
        errors.update(forms.table_rules(g.repo, table, values, key if not creating else None))
        if creating and key and g.repo.get(table, key):
            target = lst.key if conf["key"][0] == "manual" else next(iter(values))
            errors[target] = f"{key} already exists. Open it from the list to change it."
        if not creating and conf["key"][0] == "template":
            new_key = forms.make_key(conf, values, g.repo, table)
            if new_key != key:
                errors["_form"] = ("The fields that make up this row's key can't be changed. Make this row inactive "
                                   "and add a new one instead.")
    return key, values, errors


@bp.route("/")
@auth.admin_required
def index():
    tables = [(t, c["title"], g.repo.count(t)) for t, c in ADMIN_TABLES.items()]
    return render_template("admin/index.html", tables=tables)


@bp.route("/<table>")
@auth.admin_required
def list_rows(table):
    conf = _conf(table)
    lst = LISTS_BY_NAME[table]
    q = request.args.get("q", "").strip()
    show_all = request.args.get("show") == "all"
    page = max(1, request.args.get("page", 1, type=int))
    where, params = [], []
    if q:
        where.append("(" + " OR ".join(f"lower({c}) LIKE ?" for c in conf["search"]) + ")")
        params += [f"%{q.lower()}%"] * len(conf["search"])
    if conf.get("inactive") and not show_all:
        col, val = conf["inactive"]
        where.append(f"({col} IS NULL OR {col} <> ?)")
        params.append(1 if val is True else 0 if val is False else val)
    clause = " AND ".join(where)
    total = g.repo.count(table, clause, params)
    rows = g.repo.find(table, clause, params, order=conf.get("order", lst.key), limit=PAGE_SIZE,
                       offset=(page - 1) * PAGE_SIZE)
    cols = [next(c for c in lst.all_columns if c.name == n) for n in conf["list_cols"]]
    return render_template("admin/list.html", table=table, conf=conf, rows=rows, cols=cols, key=lst.key, q=q,
                           show_all=show_all, page=page, pages=max(1, -(-total // PAGE_SIZE)), total=total,
                           label=forms.label)


@bp.route("/<table>/new", methods=["GET", "POST"])
@auth.admin_required
def new_row(table):
    conf = _conf(table)
    errors, row = {}, None
    if request.method == "POST":
        key, values, errors = _read_form(table, conf, creating=True)
        if not errors:
            try:
                with g.repo.transaction():
                    g.repo.insert(table, values, g.person["email"])
            except Exception as exc:  # database constraint as a last line of defence
                errors["_form"] = f"That couldn't be saved: {exc}"
            else:
                flash(f"Added {key}.")
                return redirect(url_for("admin.view_row", table=table, key=key))
        row = values
    return render_template("admin/form.html", table=table, conf=conf, creating=True, errors=errors,
                           fields=_fields(table, conf, row, creating=True), label=forms.label), (400 if errors else 200)


@bp.route("/<table>/item")
@auth.admin_required
def view_row(table):
    conf = _conf(table)
    row = g.repo.get(table, request.args.get("key", ""))
    if row is None:
        abort(404)
    account = None
    if table == "people":
        account = g.conn.execute("SELECT password_hash IS NOT NULL AS has_password, token_purpose, last_login_at "
                                 "FROM accounts WHERE org_id = ? AND email = ?", (g.repo.org_id, row["email"])).fetchone()
    return render_template("admin/view.html", table=table, conf=conf, row=row, key=row[LISTS_BY_NAME[table].key],
                           fields=_fields(table, conf, row), label=forms.label, account=account)


@bp.route("/<table>/edit", methods=["GET", "POST"])
@auth.admin_required
def edit_row(table):
    conf = _conf(table)
    row = g.repo.get(table, request.args.get("key", ""))
    if row is None:
        abort(404)
    lst = LISTS_BY_NAME[table]
    errors = {}
    if request.method == "POST":
        key, values, errors = _read_form(table, conf, creating=False, existing=row)
        if not errors:
            changes = {k: v for k, v in values.items() if k != lst.key}
            try:
                with g.repo.transaction():
                    g.repo.update(table, key, changes, g.person["email"])
            except Exception as exc:
                errors["_form"] = f"That couldn't be saved: {exc}"
            else:
                flash("Changes saved.")
                return redirect(url_for("admin.view_row", table=table, key=key))
        row = dict(row, **values)
    return render_template("admin/form.html", table=table, conf=conf, creating=False, errors=errors,
                           key=row[lst.key], fields=_fields(table, conf, row), label=forms.label), (400 if errors else 200)


@bp.route("/<table>/history")
@auth.admin_required
def history(table):
    conf = _conf(table)
    key = request.args.get("key", "")
    rows = g.repo.find("audit_log", "list_name = ? AND item_key = ?", (table, key), order="changed_at DESC, id DESC")
    return render_template("admin/history.html", table=table, conf=conf, key=key, rows=rows, label=forms.label)


@bp.route("/people/invite", methods=["POST"])
@auth.admin_required
def invite():
    email = request.form.get("key", "")
    person = g.repo.get("people", email)
    if person is None or not person["active"]:
        abort(404)
    has_password = g.conn.execute("SELECT password_hash IS NOT NULL FROM accounts WHERE org_id = ? AND email = ?",
                                  (g.repo.org_id, email)).fetchone()
    purpose = "reset" if has_password and has_password[0] else "invite"
    token = auth.issue_token(g.conn, g.repo.org_id, email, purpose)
    link = url_for("auth.set_password_page", token=token, _external=True)
    return render_template("admin/invite.html", person=person, link=link, purpose=purpose,
                           days=auth.TOKEN_DAYS)


@bp.route("/audit")
@auth.admin_required
def audit():
    q = request.args.get("q", "").strip()
    where, params = "", ()
    if q:
        where, params = "lower(item_key) LIKE ? OR lower(changed_by) LIKE ? OR list_name LIKE ?", (f"%{q.lower()}%",) * 3
    rows = g.repo.find("audit_log", where, params, order="changed_at DESC, id DESC", limit=200)
    return render_template("admin/audit.html", rows=rows, q=q)


def setting(repo, key, default=None):
    row = repo.get("settings", key)
    return row["setting_value"] if row else default


@bp.route("/periods/generate", methods=["POST"])
@auth.admin_required
def generate_periods():
    fy = request.form.get("fy", type=int)
    if not fy or not 2000 <= fy <= 2100:
        flash("Enter the year the financial year starts in, for example 2027.", "error")
        return redirect(url_for("admin.list_rows", table="periods"))
    added = add_periods(g.repo, fy, g.person["email"])
    flash(f"Added {added} periods for the financial year starting in {fy}. Check the term dates.")
    return redirect(url_for("admin.list_rows", table="periods"))


def add_periods(repo, fy, who, daily=True):
    fy_month = int(setting(repo, "fy_start_month", periods.DEFAULT_FY_START_MONTH))
    ay_month = int(setting(repo, "ay_start_month", periods.DEFAULT_AY_START_MONTH))
    anchor = setting(repo, "fortnight_anchor_date")
    from datetime import date
    rows = periods.generate(fy, fy, None if daily else fy + 1, fy_start_month=fy_month, ay_start_month=ay_month,
                            fortnight_anchor=date.fromisoformat(anchor) if anchor else None)
    added = 0
    with repo.transaction():
        for r in rows:
            if repo.get("periods", r["period_key"]) is None:
                repo.insert("periods", r, who)
                added += 1
    return added
