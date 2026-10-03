"""First-run setup in the browser."""
import unittest

from .helpers import AppCase

GOOD = dict(setup_code="TESTCODE", org_name="Riverside Trust", display_name="Ada Admin", email="Ada@Riverside.example",
            fy_start_month="1", password="a perfectly long passphrase", confirm="a perfectly long passphrase")


class SetupTests(AppCase, unittest.TestCase):
    demo = False

    def setUp(self):
        import os
        os.environ["OPENPMS_SETUP_CODE"] = "TESTCODE"
        super().setUp()
        del os.environ["OPENPMS_SETUP_CODE"]

    def test_wrong_setup_code_refused(self):
        r = self.post("/setup", dict(GOOD, setup_code="WRONG"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("setup code", r.get_data(as_text=True))
        self.assertEqual(self.conn().execute("SELECT COUNT(*) FROM organisations").fetchone()[0], 0)

    def test_fresh_install_goes_to_setup(self):
        r = self.client.get("/")
        self.assertEqual(r.headers["Location"], "/setup")

    def test_setup_creates_org_admin_and_periods(self):
        r = self.post("/setup", GOOD)
        self.assertEqual(r.status_code, 302)
        repo = self.repo()
        self.assertEqual(repo.get("settings", "organisation_name")["setting_value"], "Riverside Trust")
        self.assertEqual(repo.get("settings", "fy_start_month")["setting_value"], "1")
        self.assertEqual(repo.get("people", "ada@riverside.example")["app_role"], "admin")
        self.assertGreater(repo.count("periods", "period_type = 'annual'"), 1)
        self.assertEqual(self.login(email="ada@riverside.example", password=GOOD["password"]).status_code, 302)

    def test_setup_closes_after_first_use(self):
        self.post("/setup", GOOD)
        self.assertEqual(self.client.get("/setup").status_code, 404)

    def test_setup_validates(self):
        r = self.post("/setup", dict(GOOD, email="nope", confirm="different"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("right format", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
