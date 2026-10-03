"""Several organisations on one installation, single sign-on, and backups."""
import base64
import json
import os
import re
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from openpms import db, sso

from .helpers import ADMIN, PASSWORD, POSTGRES, STANDARD, AppCase

B_ADMIN = "ada@riverside.example"


def cli(app, *args):
    return app.test_cli_runner().invoke(args=list(args))


def set_password(app, org_code, email, password=PASSWORD):
    from openpms import auth
    conn = db.connect(app.config["DATABASE"])
    org = conn.execute("SELECT id FROM organisations WHERE slug = ?", (org_code,)).fetchone()[0]
    auth.issue_token(conn, org, email, "invite")
    acc = conn.execute("SELECT id FROM accounts WHERE org_id = ? AND email = ?", (org, email)).fetchone()[0]
    auth.set_password(conn, acc, password)
    conn.close()


class SecondOrg(AppCase):
    def setUp(self):
        super().setUp()
        r = cli(self.app, "create-org", "--name", "Riverside Trust", "--code", "riverside", "--admin-email", B_ADMIN,
                "--admin-name", "Ada Admin", "--fy-start-month", "1", "--base-url", "https://pms.example")
        self.assertEqual(r.exit_code, 0, r.output)
        self.created = r.output
        set_password(self.app, "riverside", B_ADMIN)

    def login_org(self, org, email, password=PASSWORD):
        token = self.csrf("/login")
        return self.client.post("/login", data={"org": org, "email": email, "password": password, "csrf_token": token})


class Organisations(SecondOrg, unittest.TestCase):
    def test_create_org(self):
        self.assertIn("People sign in at https://pms.example/login?org=riverside", self.created)
        self.assertIn("/set-password/", self.created)
        out = cli(self.app, "list-orgs").output
        self.assertIn("default", out)
        self.assertIn("riverside", out)
        conn = self.conn()
        org = conn.execute("SELECT id FROM organisations WHERE slug = 'riverside'").fetchone()[0]
        repo = db.Repo(conn, org)
        self.assertEqual(repo.get("settings", "fy_start_month")["setting_value"], "1")
        self.assertTrue(repo.get("periods", "FY-2026"), "calendar-year financial years")
        self.assertEqual(repo.get("people", B_ADMIN)["app_role"], "admin")

    def test_codes_checked(self):
        r = cli(self.app, "create-org", "--name", "X", "--code", "Bad Code!", "--admin-email", "a@b.c", "--admin-name", "A")
        self.assertIn("lower-case letters", r.output)
        r = cli(self.app, "create-org", "--name", "X", "--code", "riverside", "--admin-email", "a@b.c", "--admin-name", "A")
        self.assertIn("already used", r.output)

    def test_commands_need_an_org_once_there_are_several(self):
        r = cli(self.app, "create-admin", "--email", "x@riverside.example", "--name", "X")
        self.assertIn("Add --org <code>", r.output)
        r = cli(self.app, "create-admin", "--email", "x@riverside.example", "--name", "X", "--org", "riverside")
        self.assertEqual(r.exit_code, 0, r.output)
        r = cli(self.app, "run-jobs")
        self.assertIn("default: Values and reminders", r.output)
        self.assertIn("riverside: Values and reminders", r.output)

    def test_sign_in_needs_the_right_org_code(self):
        page = self.client.get("/login?org=riverside").get_data(as_text=True)
        self.assertIn('name="org" value="riverside"', page)
        self.assertEqual(self.login_org("", ADMIN).status_code, 400)
        self.assertEqual(self.login_org("riverside", ADMIN).status_code, 400, "Sam isn't in Riverside")
        r = self.login_org("riverside", ADMIN)
        self.assertIn("The organisation code, email or password is wrong.", r.get_data(as_text=True))
        self.assertEqual(self.login_org("default", ADMIN).status_code, 302)

    def test_organisations_never_see_each_other(self):
        self.login_org("riverside", B_ADMIN)
        home = self.client.get("/").get_data(as_text=True)
        self.assertIn("Riverside Trust", home)
        self.assertNotIn("Example Public Body", home)
        for url in ("/measures/value?key=PM-0002|M-2026-08", "/admin/measures/item?key=PM-0002",
                    "/tasks/TSK-00001", "/problems/PRB-00001", "/admin/people/item?key=sam.patel@example.org"):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        for url in ("/admin/measures", "/admin/people", "/admin/audit", "/measures/?tab=all", "/team"):
            html = self.client.get(url).get_data(as_text=True)
            self.assertNotIn("PM-0002", html, url)
            self.assertNotIn("sam.patel", html, url)
        r = self.post("/exports/download", dict(dataset="full_model", format="csv"), csrf_from="/exports/")
        self.assertNotIn(b"PM-0002", r.data)
        self.assertNotIn(b"sam.patel", r.data)

    def test_data_links_stay_in_their_org(self):
        self.login_org("default", ADMIN)
        self.post("/exports/links", dict(name="A's link", dataset="measures"), csrf_from="/exports/links")
        link_id = self.conn().execute("SELECT id FROM data_links").fetchone()[0]
        self.client = self.app.test_client()
        self.login_org("riverside", B_ADMIN)
        self.assertNotIn("A&#39;s link", self.client.get("/exports/links").get_data(as_text=True))
        r = self.post("/exports/links/revoke", dict(id=link_id), csrf_from="/exports/links")
        self.assertEqual(r.status_code, 404)
        self.assertIsNone(self.conn().execute("SELECT revoked_at FROM data_links").fetchone()[0])

    def test_snapshots_kept_apart(self):
        self.login_org("riverside", B_ADMIN)
        self.post("/admin/export_jobs/new", dict(job_code="EXP-R", job_name="R", dataset="measures", format="csv",
                                                 frequency="daily", folder_path="full_model", active="1"))
        self.post("/exports/scheduled/run", dict(job_code="EXP-R"), csrf_from="/exports/scheduled")
        self.assertTrue((self.tmp / "snapshots" / "riverside" / "full_model" / "latest" / "values_flat.csv").exists())
        self.assertFalse((self.tmp / "snapshots" / "full_model").exists())


def id_token(**claims):
    def enc(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


GOOGLE = {"OPENPMS_GOOGLE_CLIENT_ID": "gid", "OPENPMS_GOOGLE_CLIENT_SECRET": "gsecret"}
MICROSOFT = {"OPENPMS_MICROSOFT_CLIENT_ID": "mid", "OPENPMS_MICROSOFT_CLIENT_SECRET": "msecret",
             "OPENPMS_MICROSOFT_TENANT_ID": "tenant-1"}


class SingleSignOn(AppCase, unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, dict(GOOGLE, **MICROSOFT))
        self.env.start()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.env.stop()

    def start(self, provider="google", **form):
        token = self.csrf("/login")
        r = self.client.post(f"/login/sso/{provider}", data=dict(form, csrf_token=token))
        self.assertEqual(r.status_code, 302)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.headers["Location"]).query))
        return r.headers["Location"], query

    def finish(self, query, provider="google", **claims):
        base = dict(iss="https://accounts.google.com", aud="gid", exp=time.time() + 300, nonce=query["nonce"],
                    email=STANDARD, email_verified=True)
        if provider == "microsoft":
            base = dict(iss="https://login.microsoftonline.com/tenant-1/v2.0", aud="mid", exp=time.time() + 300,
                        nonce=query["nonce"], tid="tenant-1", preferred_username=STANDARD)
        base.update(claims)
        base = {k: v for k, v in base.items() if v is not None}
        with mock.patch.object(sso, "_post_form", return_value={"id_token": id_token(**base)}) as post:
            r = self.client.get(f"/login/sso/{provider}/callback?code=abc&state={query['state']}")
        return r, post

    def signed_in_as(self):
        html = self.client.get("/").get_data(as_text=True)
        m = re.search(r'<span class="who">([^<]+)</span>', html)
        return m.group(1) if m else None

    def test_buttons_shown(self):
        html = self.client.get("/login").get_data(as_text=True)
        self.assertIn("Sign in with Google", html)
        self.assertIn("Sign in with Microsoft", html)

    def test_google_sign_in(self):
        url, q = self.start(next="/measures/")
        self.assertTrue(url.startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        self.assertEqual((q["client_id"], q["code_challenge_method"], q["redirect_uri"]),
                         ("gid", "S256", "http://pms.test/login/sso/google/callback"))
        r, post = self.finish(q)
        self.assertEqual(r.headers["Location"], "/measures/")
        sent = post.call_args[0][1]
        self.assertEqual((sent["code"], sent["client_secret"]), ("abc", "gsecret"))
        self.assertTrue(sent["code_verifier"], "PKCE verifier sent with the code")
        self.assertEqual(self.signed_in_as(), "Priya Shah")

    def test_microsoft_sign_in_creates_account_for_existing_person(self):
        conn = self.conn()
        conn.execute("DELETE FROM accounts WHERE email = ?", (STANDARD,))
        _, q = self.start("microsoft")
        r, _ = self.finish(q, "microsoft")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.signed_in_as(), "Priya Shah")
        acc = conn.execute("SELECT password_hash FROM accounts WHERE email = ?", (STANDARD,)).fetchone()
        self.assertIsNone(acc[0], "no password needed")

    def test_refused(self):
        cases = [
            ("google", dict(email_verified=False), "unverified email"),
            ("google", dict(aud="someone-else"), "token for another app"),
            ("google", dict(iss="https://evil.example"), "wrong issuer"),
            ("google", dict(exp=time.time() - 3600), "expired"),
            ("google", dict(nonce="replayed"), "wrong nonce"),
            ("google", dict(email="nobody@example.org"), "not a person in Open PMS"),
            ("google", dict(email="ruth.clarke@example.org", email_verified=None), "verification missing"),
            ("microsoft", dict(tid="other-tenant"), "another Microsoft directory"),
        ]
        for provider, claims, why in cases:
            self.client = self.app.test_client()
            _, q = self.start(provider)
            r, _ = self.finish(q, provider, **claims)
            self.assertEqual(r.headers["Location"], "/login", why)
            self.assertIsNone(self.signed_in_as(), why)

    def test_inactive_person_refused(self):
        self.repo().update("people", STANDARD, dict(active=False), "t")
        _, q = self.start()
        self.finish(q)
        self.assertIsNone(self.signed_in_as())

    def test_state_must_match(self):
        _, q = self.start()
        r, post = self.finish(dict(q, state="forged"))
        self.assertEqual(r.headers["Location"], "/login")
        post.assert_not_called()
        self.assertEqual(self.client.get("/login/sso/google/callback?code=x&state=y").status_code, 404,
                         "the failed attempt is forgotten, so there's no sign-in in progress")

    def test_start_needs_csrf(self):
        self.assertEqual(self.client.post("/login/sso/google").status_code, 400)

    def test_shared_microsoft_tenant_refused_at_start_up(self):
        with mock.patch.dict(os.environ, {"OPENPMS_MICROSOFT_TENANT_ID": "common"}):
            with self.assertRaises(RuntimeError):
                sso.providers()

    def test_single_sign_on_only(self):
        with mock.patch.dict(os.environ, {"OPENPMS_PASSWORD_SIGN_IN": "0"}):
            html = self.client.get("/login").get_data(as_text=True)
            self.assertNotIn('name="password"', html)
            self.assertIn("Sign in with Google", html)
            self.assertEqual(self.login().status_code, 404)


@unittest.skipIf(POSTGRES, "file backups are for SQLite; PostgreSQL uses pg_dump")
class Backups(AppCase, unittest.TestCase):
    def test_backup_check_and_keep(self):
        folder = self.tmp / "backups"
        for _ in range(3):
            r = cli(self.app, "backup", "--to", str(folder), "--keep", "2")
            self.assertEqual(r.exit_code, 0, r.output)
            self.assertIn("checked it", r.output)
            time.sleep(1.01)
        files = sorted(folder.glob("openpms-*.db"))
        self.assertEqual(len(files), 2, "oldest removed")
        self.assertEqual(oct(files[0].stat().st_mode)[-3:], "600")
        r = cli(self.app, "check-backup", str(files[-1]))
        self.assertIn("looks good", r.output)
        self.assertIn("measures 22", r.output)
        bad = self.tmp / "bad.db"
        bad.write_bytes(b"not a database" * 100)
        r = cli(self.app, "check-backup", str(bad))
        self.assertNotEqual(r.exit_code, 0)
        self.assertIn("not a good backup", r.output)

    def test_restore(self):
        folder = self.tmp / "backups"
        cli(self.app, "backup", "--to", str(folder))
        backup = next(folder.glob("*.db"))
        self.repo().update("measures", "PM-0002", dict(measure_name="Changed after the backup"), "t")
        r = cli(self.app, "restore", str(backup))
        self.assertIn("--yes", r.output)
        self.assertEqual(self.repo().get("measures", "PM-0002")["measure_name"], "Changed after the backup")
        r = cli(self.app, "restore", str(backup), "--yes")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertNotEqual(self.repo().get("measures", "PM-0002")["measure_name"], "Changed after the backup")
        kept = list(Path(self.database).parent.glob("*.before-restore-*"))
        self.assertEqual(len(kept), 1, "the old database is kept")


if __name__ == "__main__":
    unittest.main()
