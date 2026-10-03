"""Export pages: downloads for everyone, scheduled snapshots and data links
for admins, and the data link itself (/data/<token>/...), which BI tools and
spreadsheets read without signing in."""
import hashlib
import secrets
import threading
from datetime import date

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   url_for)

from . import auth, db, exports

bp = Blueprint("exports", __name__, url_prefix="/exports")
data_bp = Blueprint("data", __name__, url_prefix="/data")


TITLES = {k: d["title"] for k, d in exports.DATASETS.items()}


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------
def _choices():
    today = date.today()
    quarters = [(q["period_key"], q["financial_quarter"] + (" (in progress)" if q["end_date"] >= today else ""))
                for q in exports.quarters(g.repo, today)]
    last = exports.last_completed_quarter(g.repo, today)
    return dict(datasets=list(exports.DATASETS.items()), titles=TITLES, formats=list(exports.FORMATS.items()),
                years=exports.financial_years(g.repo), quarters=quarters,
                default_quarter=last["period_key"] if last else None)


def _recent():
    if g.role == "admin":
        return g.repo.find("export_requests", order="requested_at DESC", limit=10)
    return g.repo.find("export_requests", "requested_by = ?", (g.person["email"],), order="requested_at DESC", limit=10)


@bp.route("/")
@auth.login_required
def index():
    return render_template("exports/index.html", errors={}, form={}, recent=_recent(), **_choices())


@bp.route("/download", methods=["POST"])
@auth.login_required
def download():
    f = request.form
    choices = _choices()
    errors = {}
    dataset, fmt = f.get("dataset"), f.get("format")
    if dataset not in exports.DATASETS:
        errors["dataset"] = "Choose what to export."
    if fmt not in exports.FORMATS:
        errors["format"] = "Choose a format."
    year = f.get("financial_year") or None
    if dataset == "measures" and year and year not in choices["years"]:
        errors["financial_year"] = "Choose a financial year from the list."
    quarter = None
    if dataset == "quarter_pack":
        quarter = g.repo.get("periods", f.get("quarter") or "")
        if not quarter or quarter["period_type"] != "quarterly":
            errors["quarter"] = "Choose a quarter from the list."
    if errors:
        return render_template("exports/index.html", errors=errors, form=f, recent=_recent(), **choices), 400
    exp = exports.build(g.repo, dataset, quarter=quarter, financial_year=year)
    name, mimetype, data = exports.download(exp, fmt)
    exports.log_download(g.repo, exp, fmt, g.person["email"])
    return Response(data, mimetype=mimetype, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------------------
# Scheduled snapshots
# ---------------------------------------------------------------------------
def snapshot_dir():
    return exports.snapshot_root(current_app.config["SNAPSHOT_DIR"], db.org_slug(g.conn, g.repo.org_id))


@bp.route("/scheduled")
@auth.admin_required
def scheduled():
    jobs = g.repo.find("export_jobs", order="job_code")
    runs = g.repo.find("export_requests", "job_code IS NOT NULL", order="requested_at DESC", limit=10)
    return render_template("exports/scheduled.html", jobs=jobs, runs=runs, folder=snapshot_dir())


@bp.route("/scheduled/run", methods=["POST"])
@auth.admin_required
def run_now():
    job = g.repo.get("export_jobs", request.form.get("job_code", ""))
    if job is None:
        abort(404)
    status = exports.run_job(g.repo, job, current_app.config["SNAPSHOT_DIR"], db.org_slug(g.conn, g.repo.org_id),
                             who=g.person["email"])
    job = g.repo.get("export_jobs", job["job_code"])
    if status == "done":
        flash(f"{job['job_name']}: files written.")
    else:
        flash(f"{job['job_name']} failed. {job['last_run_status']}", "error")
    return redirect(url_for("exports.scheduled"))


def start_due_jobs(app, org_id):
    """Scheduled snapshots, once a day, in the background so nobody waits."""
    def work():
        conn = db.connect(app.config["DATABASE"])
        try:
            exports.run_due_jobs(db.Repo(conn, org_id), app.config["SNAPSHOT_DIR"], db.org_slug(conn, org_id))
        except Exception:  # each job records its own failure; this catches anything else
            app.logger.exception("Scheduled exports failed")
        finally:
            conn.close()
    if app.config.get("JOBS_IN_FOREGROUND"):
        work()
    else:
        threading.Thread(target=work, name="openpms-exports", daemon=True).start()


# ---------------------------------------------------------------------------
# Data links
# ---------------------------------------------------------------------------
def _links():
    return g.conn.execute("SELECT * FROM data_links WHERE org_id = ? ORDER BY revoked_at IS NOT NULL, created_at DESC",
                          (g.repo.org_id,)).fetchall()


@bp.route("/links", methods=["GET", "POST"])
@auth.admin_required
def links():
    errors, form = {}, request.form
    if request.method == "POST":
        name = (form.get("name") or "").strip()
        dataset = form.get("dataset")
        if not name:
            errors["name"] = "Enter a name, so you know later what the link is for."
        elif len(name) > 100:
            errors["name"] = "Use 100 characters or fewer."
        if dataset not in exports.DATA_LINK_DATASETS:
            errors["dataset"] = "Choose what the link shares."
        if not errors:
            token = secrets.token_urlsafe(32)
            now = db.iso(db.utcnow())
            with g.repo.transaction():
                link_id = g.conn.execute(
                    "INSERT INTO data_links (org_id, name, dataset, token_hash, created_by, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
                    (g.repo.org_id, name, dataset, _hash(token), g.person["email"], now)).fetchone()[0]
                g.repo._audit("data_links", f"LINK-{link_id}", "create", None, None, None, g.person["email"],
                              db.utcnow())
            url = url_for("data.listing", token=token, _external=True)
            return render_template("exports/link_created.html", name=name, dataset=dataset, url=url,
                                   tables=[t["name"] for t in exports.DATASETS[dataset]["tables"]])
    return render_template("exports/links.html", links=_links(), errors=errors, form=form,
                           datasets=[(k, exports.DATASETS[k]) for k in exports.DATA_LINK_DATASETS], titles=TITLES), \
        (400 if errors else 200)


@bp.route("/links/revoke", methods=["POST"])
@auth.admin_required
def revoke_link():
    link_id = request.form.get("id", type=int)
    with g.repo.transaction():
        cur = g.conn.execute("UPDATE data_links SET revoked_at = ?, revoked_by = ? WHERE id = ? AND org_id = ?"
                             " AND revoked_at IS NULL", (db.iso(db.utcnow()), g.person["email"], link_id, g.repo.org_id))
        if cur.rowcount:
            g.repo._audit("data_links", f"LINK-{link_id}", "retire", "revoked_at", None, "revoked", g.person["email"],
                          db.utcnow())
    if not cur.rowcount:
        abort(404)
    flash("Link turned off. Anything using it will stop updating.")
    return redirect(url_for("exports.links"))


def _link_or_404(token):
    row = g.conn.execute("SELECT * FROM data_links WHERE token_hash = ? AND revoked_at IS NULL",
                         (_hash(token),)).fetchone()
    if row is None:
        abort(404)
    g.conn.execute("UPDATE data_links SET last_used_at = ?, use_count = use_count + 1 WHERE id = ?",
                   (db.iso(db.utcnow()), row["id"]))
    return row


def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@data_bp.route("/<token>/")
def listing(token):
    link = _link_or_404(token)
    d = exports.DATASETS[link["dataset"]]
    names = [f"{t['name']}.csv" for t in d["tables"]] + ["data_dictionary.csv", "README_for_AI.md", "export_info.txt"]
    return _no_cache(Response(render_template("exports/data_index.html", title=d["title"], names=names),
                              mimetype="text/html"))


@data_bp.route("/<token>/<name>")
def file(token, name):
    link = _link_or_404(token)
    # Read only the table asked for: BI tools fetch each file separately.
    exp = exports.build(db.Repo(g.conn, link["org_id"]), link["dataset"], only={name.removesuffix(".csv")})
    if name.endswith(".csv"):
        files = exports.csv_files(exp)
        mimetype = "text/csv"
    else:
        files = {k: v.encode("utf-8") for k, v in exp.files.items()}
        mimetype = "text/markdown" if name.endswith(".md") else "text/plain"
    if name not in files:
        abort(404)
    return _no_cache(Response(files[name], mimetype=mimetype, headers={"Content-Disposition": f'inline; filename="{name}"'}))
