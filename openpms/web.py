"""Home page and health check."""
from flask import Blueprint, g, render_template

from . import auth

bp = Blueprint("web", __name__)


@bp.route("/")
@auth.login_required
def home():
    roles = g.repo.by("measure_roles", email=g.person["email"], active=True)
    counts = {r: sum(1 for x in roles if x["role"] == r) for r in ("owner", "updater", "approver")}
    return render_template("home.html", counts=counts)


@bp.route("/healthz")
def health():
    g.conn.execute("SELECT 1").fetchone()
    return {"status": "ok"}


def _needs_setup():
    return g.conn.execute("SELECT COUNT(*) FROM organisations").fetchone()[0] == 0


@bp.before_app_request
def redirect_to_setup():
    from flask import redirect, request, url_for
    if request.endpoint in ("web.setup", "web.health", "static"):
        return None
    if _needs_setup():
        return redirect(url_for("web.setup"))
    return None


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """First run only: name the organisation and create the first admin.
    Gone for good once an organisation exists."""
    from datetime import date

    from flask import abort, flash, redirect, request, url_for

    from . import db, forms
    from .admin import add_periods
    from .auth import password_problems, set_password, issue_token
    from .cli import DEFAULT_SETTINGS
    from .periods import fy_start_year

    if not _needs_setup():
        abort(404)
    errors, values = {}, {}
    if request.method == "POST":
        import hmac

        from flask import current_app
        values = {k: request.form.get(k, "").strip() for k in ("org_name", "display_name", "email", "fy_start_month")}
        code = request.form.get("setup_code", "").strip().upper()
        if not hmac.compare_digest(code, str(current_app.config.get("SETUP_CODE", "")).upper()):
            errors["setup_code"] = "Enter the setup code shown in the server log when Open PMS started."
        password, confirm = request.form.get("password", ""), request.form.get("confirm", "")
        if not values["org_name"]:
            errors["org_name"] = "Enter your organisation's name."
        if not values["display_name"]:
            errors["display_name"] = "Enter your name."
        if not forms.EMAIL.match(values["email"]):
            errors["email"] = "Enter an email address in the right format, like name@example.org."
        if not values["fy_start_month"].isdigit() or not 1 <= int(values["fy_start_month"]) <= 12:
            errors["fy_start_month"] = "Choose the month your financial year starts."
        problems = password_problems(password, values["email"])
        if problems:
            errors["password"] = " ".join(problems)
        elif password != confirm:
            errors["confirm"] = "The passwords don't match."
        if not errors:
            email = values["email"].lower()
            g.conn.execute("BEGIN IMMEDIATE")
            if not _needs_setup():  # someone else finished setup a moment ago
                g.conn.execute("ROLLBACK")
                abort(404)
            org = db.create_org(g.conn, values["org_name"], "default")
            repo = db.Repo(g.conn, org)
            for k, v, d in DEFAULT_SETTINGS:
                v = {"organisation_name": values["org_name"], "fy_start_month": values["fy_start_month"],
                     "base_url": request.host_url.rstrip("/")}.get(k, v)
                repo.insert("settings", {"setting_key": k, "setting_value": v, "description": d}, email)
            repo.insert("people", {"email": email, "display_name": values["display_name"], "app_role": "admin",
                                   "active": True}, email)
            issue_token(g.conn, org, email, "invite")
            acc = g.conn.execute("SELECT id FROM accounts WHERE org_id = ? AND email = ?", (org, email)).fetchone()
            set_password(g.conn, acc["id"], password)
            g.conn.execute("COMMIT")
            this_fy = fy_start_year(date.today(), int(values["fy_start_month"]))
            for fy in (this_fy, this_fy + 1):
                add_periods(repo, fy, email)
            flash("Your organisation is set up. Sign in to add teams, people and measures.")
            return redirect(url_for("auth.login"))
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]
    return render_template("setup.html", errors=errors, values=values, months=months), (400 if errors else 200)
