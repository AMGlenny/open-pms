"""Shared test setup: a fresh database with the demo organisation.

Tests use SQLite by default. To run them against PostgreSQL, set
OPENPMS_TEST_POSTGRES to a URL for a user that can create databases, e.g.
postgresql://openpms:openpms@localhost/postgres
"""
import atexit
import itertools
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

from openpms import create_app, db

PASSWORD = "correct horse battery staple"
ADMIN = "sam.patel@example.org"
STANDARD = "priya.shah@example.org"
VIEWER = "ruth.clarke@example.org"
POSTGRES = os.environ.get("OPENPMS_TEST_POSTGRES")
_TEMPLATE = None
_COUNTER = itertools.count()
_CREATED = []


def _pg_admin(sql):
    import psycopg
    with psycopg.connect(POSTGRES, autocommit=True) as c:
        c.execute(sql)


def _pg_url(name):
    base, _, _ = POSTGRES.rpartition("/")
    return f"{base}/{name}"


def new_database(tmp, template=None):
    """A database for one test: a file in tmp (SQLite), or a new PostgreSQL
    database, copied from template if given."""
    if POSTGRES:
        name = f"openpms_t{os.getpid()}_{next(_COUNTER)}"
        _pg_admin(f"CREATE DATABASE {name}" + (f" TEMPLATE {template}" if template else ""))
        _CREATED.append(name)
        return _pg_url(name)
    path = Path(tmp) / f"test{next(_COUNTER)}.db"
    if template:
        src, dst = sqlite3.connect(template), sqlite3.connect(path)
        src.backup(dst)  # copies committed data even while it's still in the write-ahead log
        src.close()
        dst.close()
    return str(path)


def drop_database(target):
    if POSTGRES and db.is_postgres(target):
        name = target.rpartition("/")[2]
        _pg_admin(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        if name in _CREATED:
            _CREATED.remove(name)


@atexit.register
def _drop_leftovers():
    for name in list(_CREATED):
        drop_database(_pg_url(name))


def empty_connection():
    """An empty, initialised database connection (for low-level tests)."""
    target = new_database(tempfile.mkdtemp())
    conn = db.connect(target)
    db.init(conn)
    return conn, target


def _demo_db():
    """Build the demo database once, then copy it for each test."""
    global _TEMPLATE
    if _TEMPLATE is None:
        tmp = Path(tempfile.mkdtemp())
        if POSTGRES:
            name = f"openpms_demo_{os.getpid()}"
            _pg_admin(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
            _pg_admin(f"CREATE DATABASE {name}")
            _CREATED.append(name)
            target = _pg_url(name)
        else:
            target = str(tmp / "demo.db")
        app = create_app({"TESTING": True, "DATABASE": target, "SECRET_KEY": "test",
                          "SNAPSHOT_DIR": str(tmp / "snapshots")})
        result = app.test_cli_runner().invoke(args=["load-demo", "--password", PASSWORD])
        assert result.exit_code == 0, result.output
        _TEMPLATE = name if POSTGRES else target
    return _TEMPLATE


class AppCase:
    """Mixin for unittest.TestCase: self.app, self.client, self.login()."""

    demo = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.database = new_database(self.tmp, _demo_db() if self.demo else None)
        self._conns = []
        self.app = create_app({"TESTING": True, "DATABASE": self.database, "SECRET_KEY": "test",
                               "SERVER_NAME": "pms.test", "DISABLE_DAILY_JOBS": True,
                               "SNAPSHOT_DIR": str(self.tmp / "snapshots"), "JOBS_IN_FOREGROUND": True})
        self.client = self.app.test_client()

    def tearDown(self):
        for c in self._conns:
            c.close()
        drop_database(self.database)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def conn(self):
        c = db.connect(self.app.config["DATABASE"])
        self._conns.append(c)
        return c

    def repo(self):
        return db.Repo(self.conn(), 1)

    def csrf(self, path="/login"):
        r = self.client.get(path)
        m = re.search(r'name="csrf_token" value="([^"]+)"', r.get_data(as_text=True))
        return m.group(1) if m else None

    def login(self, email=ADMIN, password=PASSWORD):
        token = self.csrf("/login")
        return self.client.post("/login", data={"email": email, "password": password, "csrf_token": token})

    def post(self, path, data, csrf_from=None):
        token = self.csrf(csrf_from or path)
        return self.client.post(path, data=dict(data, csrf_token=token))
