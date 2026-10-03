"""Sign-in, invite links, lockout, CSRF and roles."""
import re
import unittest

from openpms import auth

from .helpers import ADMIN, PASSWORD, STANDARD, VIEWER, AppCase


class SignInTests(AppCase, unittest.TestCase):
    def test_sign_in_and_out(self):
        r = self.login()
        self.assertEqual(r.status_code, 302)
        self.assertIn("Hello, Sam Patel", self.client.get("/").get_data(as_text=True))
        self.post("/logout", {}, csrf_from="/")
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_wrong_password_and_unknown_email_look_the_same(self):
        a = self.login(password="wrong password here").get_data(as_text=True)
        b = self.login(email="nobody@example.org").get_data(as_text=True)
        self.assertIn("The email or password is wrong.", a)
        self.assertIn("The email or password is wrong.", b)

    def test_lockout_after_ten_failures(self):
        for _ in range(auth.MAX_FAILED):
            self.login(password="definitely not it")
        r = self.login()  # right password, but locked
        self.assertIn("Too many failed attempts", r.get_data(as_text=True))

    def test_inactive_person_cannot_sign_in(self):
        r = self.login(email="gary.fox@example.org")
        self.assertEqual(r.status_code, 400)

    def test_csrf_required(self):
        r = self.client.post("/login", data={"email": ADMIN, "password": PASSWORD})
        self.assertEqual(r.status_code, 400)

    def test_no_open_redirect(self):
        token = self.csrf()
        r = self.client.post("/login?next=//evil.example", data={"email": ADMIN, "password": PASSWORD, "csrf_token": token})
        self.assertEqual(r.headers["Location"], "/")

    def test_pages_need_sign_in(self):
        for path in ("/", "/admin/", "/admin/measures"):
            self.assertEqual(self.client.get(path).status_code, 302, path)

    def test_security_headers(self):
        r = self.client.get("/login")
        self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")


class RoleTests(AppCase, unittest.TestCase):
    def test_only_admins_reach_admin(self):
        for email in (STANDARD, VIEWER):
            self.client = self.app.test_client()
            self.login(email=email)
            self.assertEqual(self.client.get("/admin/").status_code, 403, email)
            self.assertNotIn('href="/admin/"', self.client.get("/").get_data(as_text=True))


class InviteTests(AppCase, unittest.TestCase):
    def _invite(self, email):
        self.login()
        r = self.post("/admin/people/invite", {"key": email}, csrf_from=f"/admin/people/item?key={email}")
        return re.search(r'value="(http[^"]+/set-password/[^"]+)"', r.get_data(as_text=True)).group(1)

    def test_invite_link_sets_password_once(self):
        link = self._invite("nadia.hassan@example.org")
        path = link.split("pms.test")[1]
        self.client = self.app.test_client()
        r = self.post(path, {"password": "short", "confirm": "short"})
        self.assertIn("at least 12 characters", r.get_data(as_text=True))
        r = self.post(path, {"password": "a brand new long password", "confirm": "a brand new long password"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get(path).status_code, 404, "links work once")
        self.assertEqual(self.login(email="nadia.hassan@example.org", password="a brand new long password").status_code, 302)

    def test_tokens_stored_hashed(self):
        link = self._invite("nadia.hassan@example.org")
        token = link.rsplit("/", 1)[1]
        stored = self.conn().execute("SELECT token_hash FROM accounts WHERE email = 'nadia.hassan@example.org'").fetchone()[0]
        self.assertNotEqual(stored, token)
        self.assertEqual(len(stored), 64)


if __name__ == "__main__":
    unittest.main()
