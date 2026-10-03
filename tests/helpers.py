"""Shared test setup: a fresh database with the demo organisation."""
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
_TEMPLATE = None


def _demo_db():
    """Build the demo database once, then copy it for each test."""
    global _TEMPLATE
    if _TEMPLATE is None:
        tmp = Path(tempfile.mkdtemp())
        app = create_app({"TESTING": True, "DATABASE": str(tmp / "demo.db"), "SECRET_KEY": "test"})
        result = app.test_cli_runner().invoke(args=["load-demo", "--password", PASSWORD])
        assert result.exit_code == 0, result.output
        _TEMPLATE = tmp / "demo.db"
    return _TEMPLATE


class AppCase:
    """Mixin for unittest.TestCase: self.app, self.client, self.login()."""

    demo = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        path = self.tmp / "test.db"
        if self.demo:
            src, dst = sqlite3.connect(_demo_db()), sqlite3.connect(path)
            src.backup(dst)  # copies committed data even while it's still in the write-ahead log
            src.close()
            dst.close()
        self.app = create_app({"TESTING": True, "DATABASE": str(path), "SECRET_KEY": "test",
                               "SERVER_NAME": "pms.test"})
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def conn(self):
        return db.connect(self.app.config["DATABASE"])

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
