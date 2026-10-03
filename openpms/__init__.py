"""Open PMS: a free, open-source performance management system.

Run it with `openpms run` (development) or the Docker image (production).
"""
import os
import secrets
from pathlib import Path

from flask import Flask, g, render_template

from . import db

__version__ = "0.1.0"


def _secret_key(instance):
    env = os.environ.get("OPENPMS_SECRET_KEY")
    if env:
        return env
    path = Path(instance) / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()


def create_app(config=None):
    # OPENPMS_INSTANCE: folder for the database, secret key and setup code (a volume in Docker).
    app = Flask(__name__, instance_relative_config=True, instance_path=os.environ.get("OPENPMS_INSTANCE"))
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.update(
        DATABASE=os.environ.get("OPENPMS_DATABASE", str(Path(app.instance_path) / "openpms.db")),
        SECRET_KEY=None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("OPENPMS_SECURE_COOKIES", "0") == "1",
        PERMANENT_SESSION_LIFETIME=12 * 3600,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _secret_key(app.instance_path)

    conn = db.connect(app.config["DATABASE"])
    db.init(conn)  # creates any missing tables; safe to run every time
    if conn.execute("SELECT COUNT(*) FROM organisations").fetchone()[0] == 0:
        # Fresh install: setup in the browser needs this code, printed to the
        # server log, so nobody else can claim the installation first.
        code = os.environ.get("OPENPMS_SETUP_CODE") or app.config.get("SETUP_CODE")
        if not code:
            path = Path(app.instance_path) / "setup_code"
            if not path.exists():
                path.write_text(secrets.token_hex(4).upper())
                path.chmod(0o600)
            code = path.read_text().strip()
        app.config["SETUP_CODE"] = code
        app.logger.warning("Open PMS is not set up yet. Open /setup in a browser and enter setup code %s", code)
    conn.close()

    @app.before_request
    def open_db():
        g.conn = db.connect(app.config["DATABASE"])

    @app.teardown_appcontext
    def close_db(exc):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    from datetime import date, datetime

    def fmt(value):
        """How a stored value is shown on screen."""
        if value is None or value == "":
            return ""
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M UTC")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str) and len(value) > 10 and value.endswith("Z") and value[4] == "-" and "T" in value:
            return value.replace("T", " ").replace("Z", " UTC")
        return value

    app.jinja_env.filters["fmt"] = fmt
    app.jinja_env.globals["version"] = __version__

    from . import admin, auth, measures, security, web, weekly
    security.init_app(app)
    auth.init_app(app)
    app.register_blueprint(web.bp)
    app.register_blueprint(weekly.bp)
    app.register_blueprint(measures.bp)

    @app.before_request
    def daily_jobs():
        """Create expected submissions (and send Monday reminders) once a day,
        on the first signed-in request, so no cron job is needed."""
        if g.get("repo") is None or app.config.get("DISABLE_DAILY_JOBS"):
            return
        from . import measures_service
        try:
            measures_service.run_daily(g.repo)
        except Exception:  # never block someone's page because a background job failed
            app.logger.exception("Daily jobs failed")
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)

    for code in (400, 403, 404):
        app.register_error_handler(code, lambda e, code=code: (render_template("error.html", code=code, error=e), code))

    from .cli import register
    register(app)
    return app
