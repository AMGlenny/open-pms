"""Command line: `openpms <command>`.

    openpms init-db --org-name "My Organisation"
    openpms create-admin --email you@example.org --name "Your Name"
    openpms load-demo --password "a long demo password"
    openpms generate-periods --fy 2027
    openpms run                        (development server)
"""
import secrets

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


def _org(conn, name=None):
    row = conn.execute("SELECT id FROM organisations ORDER BY id LIMIT 1").fetchone()
    if row:
        return row[0]
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


@click.command("create-admin")
@click.option("--email", required=True)
@click.option("--name", required=True)
@with_appcontext
def create_admin(email, name):
    """Add an admin and print a link for them to set their password."""
    conn = _conn()
    org = _org(conn)
    repo = db.Repo(conn, org)
    email = email.strip().lower()
    if repo.get("people", email) is None:
        repo.insert("people", {"email": email, "display_name": name, "app_role": "admin", "active": True}, "system")
    else:
        repo.update("people", email, {"app_role": "admin", "active": True}, "system")
    token = auth.issue_token(conn, org, email, "invite")
    base = repo.get("settings", "base_url")
    click.echo(f"Admin {email} is ready. Set a password here (link works once, for {auth.TOKEN_DAYS} days):")
    click.echo(f"{base['setting_value'].rstrip('/') if base else ''}/set-password/{token}")


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
@with_appcontext
def generate_periods(fy):
    """Add the periods for one financial year."""
    from .admin import add_periods
    conn = _conn()
    added = add_periods(db.Repo(conn, _org(conn)), fy, "system")
    click.echo(f"Added {added} periods. Check the term dates in Admin > Periods.")


COMMANDS = [init_db, create_admin, load_demo, generate_periods]


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
  openpms run                      (development server)
"""
