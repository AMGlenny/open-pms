"""Sign-in with email and password.

- Admins invite people; an invite link lets them set a password. Links
  expire after 7 days and work once. Only a hash of each link is stored.
- Ten failed sign-ins lock the account for 15 minutes.
- Passwords are at least 12 characters and are stored as salted hashes.

Google and Microsoft sign-in can be added alongside this later.
"""
import functools
import hashlib
import secrets
from datetime import timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import db

bp = Blueprint("auth", __name__)

MIN_PASSWORD = 12
MAX_FAILED = 10
LOCK_MINUTES = 15
TOKEN_DAYS = 7

# Used when an email has no account, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(conn, org_id, email, purpose):
    """Create (or refresh) an account and return a one-time link token."""
    token = secrets.token_urlsafe(32)
    now = db.utcnow()
    expires = db.iso(now + timedelta(days=TOKEN_DAYS))
    row = conn.execute("SELECT id FROM accounts WHERE org_id = ? AND email = ?", (org_id, email)).fetchone()
    if row:
        conn.execute("UPDATE accounts SET token_hash = ?, token_purpose = ?, token_expires_at = ? WHERE id = ?",
                     (_hash_token(token), purpose, expires, row["id"]))
    else:
        conn.execute("INSERT INTO accounts (org_id, email, token_hash, token_purpose, token_expires_at, created_at)"
                     " VALUES (?, ?, ?, ?, ?, ?)", (org_id, email, _hash_token(token), purpose, expires, db.iso(now)))
    return token


def set_password(conn, account_id, password):
    conn.execute("UPDATE accounts SET password_hash = ?, token_hash = NULL, token_purpose = NULL, "
                 "token_expires_at = NULL, failed_logins = 0, locked_until = NULL WHERE id = ?",
                 (generate_password_hash(password), account_id))


def password_problems(password, email):
    problems = []
    if len(password) < MIN_PASSWORD:
        problems.append(f"Use at least {MIN_PASSWORD} characters. A short phrase of four or five words works well.")
    if password.strip().lower() == (email or "").lower():
        problems.append("Don't use your email address as your password.")
    return problems


def init_app(app):
    @app.before_request
    def load_user():
        g.account = g.person = g.repo = None
        g.role = None
        aid, oid = session.get("aid"), session.get("oid")
        if not aid:
            return
        acc = g.conn.execute("SELECT * FROM accounts WHERE id = ? AND org_id = ?", (aid, oid)).fetchone()
        if not acc:
            session.clear()
            return
        repo = db.Repo(g.conn, oid)
        person = repo.get("people", acc["email"])
        if not person or not person["active"]:
            session.clear()
            return
        g.account, g.person, g.repo, g.role = acc, person, repo, person["app_role"]

    @app.context_processor
    def user_context():
        org_name = None
        if g.get("repo"):
            s = g.repo.get("settings", "organisation_name")
            org_name = s["setting_value"] if s else None
        return {"person": g.get("person"), "role": g.get("role"), "org_name": org_name}


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.person is None:
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else url_for("web.home")


@bp.route("/login", methods=["GET", "POST"])
def login():
    errors = {}
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        rows = g.conn.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchall()
        acc = rows[0] if len(rows) == 1 else None
        now = db.utcnow()
        if acc and acc["locked_until"] and acc["locked_until"] > db.iso(now):
            errors["email"] = "Too many failed attempts. Try again in 15 minutes, or ask an admin to reset your password."
        else:
            ok = check_password_hash(acc["password_hash"], password) if acc and acc["password_hash"] else \
                check_password_hash(_DUMMY_HASH, password) and False
            person = db.Repo(g.conn, acc["org_id"]).get("people", email) if acc else None
            if ok and person and person["active"]:
                g.conn.execute("UPDATE accounts SET failed_logins = 0, locked_until = NULL, last_login_at = ? "
                               "WHERE id = ?", (db.iso(now), acc["id"]))
                session.clear()
                session.permanent = True
                session["aid"], session["oid"] = acc["id"], acc["org_id"]
                return redirect(_safe_next(request.args.get("next")))
            if acc:
                failed = acc["failed_logins"] + 1
                locked = db.iso(now + timedelta(minutes=LOCK_MINUTES)) if failed >= MAX_FAILED else None
                g.conn.execute("UPDATE accounts SET failed_logins = ?, locked_until = ? WHERE id = ?",
                               (0 if locked else failed, locked, acc["id"]))
            errors["email"] = "The email or password is wrong."
    return render_template("auth/login.html", errors=errors, email=email), (400 if errors else 200)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You've signed out.")
    return redirect(url_for("auth.login"))


@bp.route("/set-password/<token>", methods=["GET", "POST"])
def set_password_page(token):
    acc = g.conn.execute("SELECT * FROM accounts WHERE token_hash = ?", (_hash_token(token),)).fetchone()
    if not acc or not acc["token_expires_at"] or acc["token_expires_at"] < db.iso(db.utcnow()):
        return render_template("auth/link_expired.html"), 404
    errors = {}
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        problems = password_problems(password, acc["email"])
        if problems:
            errors["password"] = " ".join(problems)
        elif password != confirm:
            errors["confirm"] = "The passwords don't match."
        else:
            set_password(g.conn, acc["id"], password)
            flash("Your password is set. You can now sign in.")
            return redirect(url_for("auth.login"))
    return render_template("auth/set_password.html", errors=errors, email=acc["email"],
                           purpose=acc["token_purpose"]), (400 if errors else 200)
