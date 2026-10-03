"""Command line: `openpms <command>`.

    openpms init-db --org-name "My Organisation"
    openpms create-admin --email you@example.org --name "Your Name"
    openpms load-demo --password "a long demo password"
    openpms generate-periods --fy 2027
    openpms run                        (development server)
"""
import re
import secrets
from datetime import date

import click
from flask import current_app
from flask.cli import FlaskGroup, with_appcontext

from . import auth, db, seed_data
from .schema import LISTS

DEFAULT_SETTINGS = [
    ("organisation_name", "My Organisation", "Name shown in the header and on exports."),
    ("fy_start_month", "4", "Month the financial year starts (1 to 12). 4 is April (UK). 1 makes the financial year the calendar year."),
    ("ay_start_month", "9", "Month the academic year starts (1 to 12)."),
    ("week_start_day", "monday", "Weeks run Monday to Sunday."),
    ("percent_storage", "0_to_100", "Percentages are stored as 0 to 100, so 58 means 58%."),
    ("wellbeing_min_group_size", "5", "Team wellbeing counts are only shown when at least this many people responded."),
    ("reminder_days_before_expected", "5", "Days before expected_by that updaters get a reminder."),
    ("base_url", "http://localhost:8000", "Web address of this installation, used for links in emails."),
]


def _conn():
    conn = db.connect(current_app.config["DATABASE"])
    db.init(conn)
    return conn


ORG_CODE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")


def _org(conn, name=None, code=None):
    """The organisation a command works on: the one named by --org, or the
    only one. Creates the first organisation on a fresh database."""
    if code:
        row = conn.execute("SELECT id FROM organisations WHERE slug = ?", (code.strip().lower(),)).fetchone()
        if not row:
            raise click.ClickException(f"There's no organisation with the code {code}. See `openpms list-orgs`.")
        return row[0]
    rows = conn.execute("SELECT id FROM organisations ORDER BY id LIMIT 2").fetchall()
    if len(rows) > 1:
        raise click.ClickException("This installation has several organisations. Add --org <code>.")
    if rows:
        return rows[0][0]
    org = db.create_org(conn, name or "My Organisation", "default")
    repo = db.Repo(conn, org)
    for k, v, d in DEFAULT_SETTINGS:
        repo.insert("settings", {"setting_key": k, "setting_value": name if k == "organisation_name" and name else v,
                                 "description": d}, "system")
    return org


@click.command("init-db")
@click.option("--org-name", help="Your organisation's name.")
@with_appcontext
def init_db(org_name):
    """Create the database tables and your organisation."""
    conn = _conn()
    _org(conn, org_name)
    click.echo(f"Database ready at {current_app.config['DATABASE']}.")


ORG_OPTION = click.option("--org", "org_code", help="Organisation code, if this installation hosts several.")


@click.command("create-admin")
@click.option("--email", required=True)
@click.option("--name", required=True)
@ORG_OPTION
@with_appcontext
def create_admin(email, name, org_code):
    """Add an admin and print a link for them to set their password."""
    conn = _conn()
    org = _org(conn, code=org_code)
    _invite_admin(conn, org, email, name)


def _invite_admin(conn, org, email, name):
    repo = db.Repo(conn, org)
    email = email.strip().lower()
    if repo.get("people", email) is None:
        repo.insert("people", {"email": email, "display_name": name, "app_role": "admin", "active": True}, "system")
    else:
        repo.update("people", email, {"app_role": "admin", "active": True}, "system")
    token = auth.issue_token(conn, org, email, "invite")
    base = repo.get("settings", "base_url")
    base = base["setting_value"].rstrip("/") if base else ""
    click.echo(f"Admin {email} is ready. Set a password here (link works once, for {auth.TOKEN_DAYS} days):")
    click.echo(f"{base}/set-password/{token}")
    if single_sign_on_hint():
        click.echo("Or sign in with single sign-on, which is turned on for this installation.")


def single_sign_on_hint():
    from . import sso
    return bool(sso.providers())


@click.command("create-org")
@click.option("--name", required=True, help="The organisation's name.")
@click.option("--code", required=True, help="A short code people enter when they sign in, e.g. riverside-trust.")
@click.option("--admin-email", required=True)
@click.option("--admin-name", required=True)
@click.option("--fy-start-month", type=click.IntRange(1, 12), default=4, show_default=True,
              help="Month the financial year starts: 4 is April, 1 is January.")
@click.option("--base-url", default="", help="Web address of this installation, for links in emails.")
@with_appcontext
def create_org(name, code, admin_email, admin_name, fy_start_month, base_url):
    """Host another organisation on this installation. Each organisation's
    data is kept completely apart."""
    from .admin import add_periods
    from .periods import fy_start_year
    code = code.strip().lower()
    if not ORG_CODE.match(code):
        raise click.ClickException("Use 2 to 40 lower-case letters, numbers and hyphens for the code.")
    conn = _conn()
    if conn.execute("SELECT 1 FROM organisations WHERE slug = ?", (code,)).fetchone():
        raise click.ClickException(f"The code {code} is already used.")
    org = db.create_org(conn, name, code)
    repo = db.Repo(conn, org)
    for k, v, d in DEFAULT_SETTINGS:
        v = {"organisation_name": name, "fy_start_month": str(fy_start_month), "base_url": base_url or v}.get(k, v)
        repo.insert("settings", {"setting_key": k, "setting_value": v, "description": d}, "system")
    this_fy = fy_start_year(date.today(), fy_start_month)
    for fy in (this_fy, this_fy + 1):
        add_periods(repo, fy, "system")
    click.echo(f"Created {name} (code {code}). People sign in at {base_url.rstrip('/')}/login?org={code}")
    _invite_admin(conn, org, admin_email, admin_name)


@click.command("list-orgs")
@with_appcontext
def list_orgs():
    """List the organisations on this installation."""
    conn = _conn()
    for r in conn.execute("SELECT o.slug, o.name, o.created_at, (SELECT COUNT(*) FROM people p WHERE p.org_id = o.id"
                          " AND p.active = 1) AS people FROM organisations o ORDER BY o.id"):
        click.echo(f"{r['slug']:<24} {r['name']}  ({r['people']} active people, since {r['created_at'][:10]})")


@click.command("load-demo")
@click.option("--password", help="Password for every demo person. Leave out to get a random one.")
@with_appcontext
def load_demo(password):
    """Load the fictional demo organisation, for trying things out."""
    conn = _conn()
    if conn.execute("SELECT COUNT(*) FROM organisations").fetchone()[0]:
        raise click.ClickException("This database already has an organisation. Use a fresh database for the demo.")
    org = db.create_org(conn, "Example Public Body", "default")
    repo = db.Repo(conn, org)
    data = seed_data.build()
    with repo.transaction():
        for lst in LISTS:
            for row in data.get(lst.name, []):
                repo.insert(lst.name, row, "system", audit=False)
    password = password or secrets.token_urlsafe(12)
    for p in data["people"]:
        auth.issue_token(conn, org, p["email"], "invite")
        acc = conn.execute("SELECT id FROM accounts WHERE org_id = ? AND email = ?", (org, p["email"])).fetchone()
        auth.set_password(conn, acc["id"], password)
    click.echo(f"Demo loaded: {sum(len(v) for v in data.values()):,} rows.")
    click.echo(f"Sign in as sam.patel@example.org (admin) or any demo person with password: {password}")


@click.command("generate-periods")
@click.option("--fy", type=int, required=True, help="Year the financial year starts in, e.g. 2027.")
@ORG_OPTION
@with_appcontext
def generate_periods(fy, org_code):
    """Add the periods for one financial year."""
    from .admin import add_periods
    conn = _conn()
    added = add_periods(db.Repo(conn, _org(conn, code=org_code)), fy, "system")
    click.echo(f"Added {added} periods. Check the term dates in Admin > Periods.")


@click.command("run-jobs")
@click.option("--force", is_flag=True, help="Run even if today's jobs have already run.")
@with_appcontext
def run_jobs(force):
    """Daily jobs, for every organisation: expected submissions, reminders on
    Mondays and scheduled exports. The app also runs these by itself on the
    first request each day."""
    from . import exports, measures_service
    conn = _conn()
    orgs = conn.execute("SELECT id, slug FROM organisations ORDER BY id").fetchall()
    for org in orgs:
        repo = db.Repo(conn, org["id"])
        label = f"{org['slug']}: " if len(orgs) > 1 else ""
        if force:
            conn.execute("DELETE FROM meta WHERE key IN (?, ?)", (f"daily_jobs_{repo.org_id}", f"snapshots_{repo.org_id}"))
        result = measures_service.run_daily(repo)
        click.echo(f"{label}Values and reminders: " + ("already ran today." if result is None else str(result)))
        if db.claim_today(conn, f"snapshots_{repo.org_id}", date.today()):
            ran = exports.run_due_jobs(repo, current_app.config["SNAPSHOT_DIR"], org["slug"])
            click.echo(f"{label}Scheduled exports: {ran or 'none due'}")
        else:
            click.echo(f"{label}Scheduled exports: already ran today.")


BACKUP_TABLES = ("organisations", "people", "measures", "submissions", "rpt_values", "tasks", "audit_log")


def _stamp():
    return db.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _check_sqlite(path):
    """(ok, message) for a SQLite backup file."""
    import sqlite3
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            return False, f"integrity check failed: {result}"
        counts = ", ".join(f"{t} {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:,}" for t in BACKUP_TABLES)
        conn.close()
        return True, counts
    except sqlite3.DatabaseError as exc:
        return False, str(exc)


def _check_dump(path):
    import shutil
    import subprocess
    if not shutil.which("pg_restore"):
        return False, "pg_restore isn't installed, so the dump can't be checked here."
    r = subprocess.run(["pg_restore", "--list", str(path)], capture_output=True, text=True)
    if r.returncode:
        return False, r.stderr.strip()
    tables = sum(1 for line in r.stdout.splitlines() if " TABLE DATA " in line)
    return True, f"{tables} tables of data"


@click.command("backup")
@click.option("--to", "folder", type=click.Path(file_okay=False), help="Folder for backups. Default: backups in the data folder.")
@click.option("--keep", type=click.IntRange(0), default=14, show_default=True, help="How many backups to keep. 0 keeps them all.")
@with_appcontext
def backup(folder, keep):
    """Take a consistent backup while Open PMS is running, check it, and
    remove the oldest beyond --keep."""
    import shutil
    import sqlite3
    import subprocess
    from pathlib import Path
    target = current_app.config["DATABASE"]
    folder = Path(folder or Path(current_app.instance_path) / "backups")
    folder.mkdir(parents=True, exist_ok=True)
    if db.is_postgres(target):
        if not shutil.which("pg_dump"):
            raise click.ClickException("pg_dump isn't installed. Install the PostgreSQL client tools, "
                                       "or back up with your database host's own tools.")
        out, pattern = folder / f"openpms-{_stamp()}.dump", "openpms-*.dump"
        r = subprocess.run(["pg_dump", "--format=custom", "--no-owner", f"--file={out}", target],
                           capture_output=True, text=True)
        if r.returncode:
            raise click.ClickException(f"pg_dump failed: {r.stderr.strip()}")
        ok, message = _check_dump(out)
    else:
        out, pattern = folder / f"openpms-{_stamp()}.db", "openpms-*.db"
        src, dst = sqlite3.connect(target), sqlite3.connect(out)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        ok, message = _check_sqlite(out)
    if not ok:
        raise click.ClickException(f"The backup at {out} failed its check: {message}")
    out.chmod(0o600)
    removed = 0
    if keep:
        for old in sorted(folder.glob(pattern))[:-keep]:
            old.unlink()
            removed += 1
    click.echo(f"Backed up to {out} and checked it: {message}.")
    if removed:
        click.echo(f"Removed {removed} older backup(s), keeping {keep}.")


@click.command("check-backup")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@with_appcontext
def check_backup(path):
    """Check that a backup file is readable and complete."""
    ok, message = _check_dump(path) if path.endswith(".dump") else _check_sqlite(path)
    if not ok:
        raise click.ClickException(f"{path} is not a good backup: {message}")
    click.echo(f"{path} looks good: {message}.")


@click.command("restore")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--yes", is_flag=True, help="Confirm: replace the current database with the backup.")
@with_appcontext
def restore(path, yes):
    """Replace the current SQLite database with a backup. Stop Open PMS
    first. The current database is kept alongside, just in case."""
    import sqlite3
    target = current_app.config["DATABASE"]
    if db.is_postgres(target):
        raise click.ClickException("For PostgreSQL, restore with pg_restore. See docs/install.md.")
    ok, message = _check_sqlite(path)
    if not ok:
        raise click.ClickException(f"{path} is not a good backup: {message}")
    if not yes:
        raise click.ClickException("This replaces everything in the current database. Stop Open PMS, "
                                   "then run this again with --yes.")
    keep = f"{target}.before-restore-{_stamp()}"
    for src_path, dst_path in ((target, keep), (path, target)):
        src, dst = sqlite3.connect(src_path), sqlite3.connect(dst_path)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
    click.echo(f"Restored from {path} ({message}). The database as it was is kept at {keep}.")


COMMANDS = [init_db, create_admin, create_org, list_orgs, load_demo, generate_periods, run_jobs, backup,
            check_backup, restore]


def register(app):
    for c in COMMANDS:
        app.cli.add_command(c)


def main():
    from . import create_app
    FlaskGroup(create_app=create_app, help=HELP)()


HELP = """Open PMS command line.

\b
  openpms init-db --org-name "My Organisation"
  openpms create-admin --email you@example.org --name "Your Name"
  openpms load-demo --password "a long demo password"
  openpms generate-periods --fy 2027
  openpms run-jobs                 (daily jobs; the app also runs them itself)
  openpms backup --keep 14         (a checked backup, safe while running)
  openpms check-backup FILE
  openpms restore FILE --yes       (SQLite; stop Open PMS first)
  openpms create-org ...           (host another organisation)
  openpms list-orgs
  openpms run                      (development server)
"""
