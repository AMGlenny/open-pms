"""Admin screens: create, validate, change, history, and no deleting."""
import unittest

from openpms.admin_config import ADMIN_TABLES

from .helpers import AppCase

MEASURE = dict(measure_name="Visitors to the library", measure_class="measure", measure_type="output", unit="count",
               polarity="higher_is_better", frequency="monthly", aggregation_method="sum", status="active")


class AdminTests(AppCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def test_every_admin_page_loads(self):
        for t in ADMIN_TABLES:
            for path in (f"/admin/{t}", f"/admin/{t}/new", f"/admin/{t}?show=all&q=a"):
                self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_new_measure_gets_next_code_and_is_audited(self):
        r = self.post("/admin/measures/new", MEASURE)
        self.assertEqual(r.status_code, 302)
        self.assertIn("key=PM-0023", r.headers["Location"])
        audit = self.repo().find("audit_log", "item_key = 'PM-0023'")
        self.assertEqual([a["action"] for a in audit], ["create"])

    def test_errors_listed_and_nothing_saved(self):
        r = self.post("/admin/measures/new", dict(MEASURE, measure_name="", unit="furlongs"), csrf_from="/admin/measures/new")
        text = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 400)
        self.assertIn("There is a problem", text)
        self.assertIn('href="#f-measure_name"', text)
        self.assertIn("Choose unit from the list.", text)
        self.assertIsNone(self.repo().get("measures", "PM-0023"))

    def test_edit_records_old_and_new(self):
        row = self.repo().get("measures", "PM-0002")
        form = {k: ("1" if v is True else "" if v in (None, False) else v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in row.items() if not k.startswith("_") and k != "measure_code"}
        form["measure_name"] = "Residents helped into work"
        r = self.post("/admin/measures/edit?key=PM-0002", form)
        self.assertEqual(r.status_code, 302)
        a = self.repo().find("audit_log", "item_key = 'PM-0002' AND field_name = 'measure_name'")[0]
        self.assertEqual((a["old_value"], a["new_value"]), ("Residents supported into work", "Residents helped into work"))
        self.assertIn("Residents helped into work", self.client.get("/admin/measures/history?key=PM-0002").get_data(as_text=True))

    def test_tolerance_only_for_kpis(self):
        r = self.post("/admin/reference_values/new", dict(measure_code="PM-0004", period_key="M-2026-09",
                                                           ref_type="tolerance", ref_value="5", active="1"))
        self.assertIn("Tolerance only applies to KPIs and OKRs", r.get_data(as_text=True))

    def test_one_owner_per_measure(self):
        r = self.post("/admin/measure_roles/new", dict(measure_code="PM-0002", email="priya.shah@example.org",
                                                        role="owner", active="1"))
        self.assertIn("already has an owner", r.get_data(as_text=True))

    def test_references_must_exist(self):
        r = self.post("/admin/measure_links/new", dict(measure_code="PM-0002", group_key="NOPE",
                                                        relationship_type="primary", active="1"))
        self.assertIn("NOPE", r.get_data(as_text=True))
        self.assertEqual(r.status_code, 400)

    def test_people_email_lower_cased_and_checked(self):
        r = self.post("/admin/people/new", dict(email="New.Person@Example.org", display_name="New Person",
                                                 app_role="standard", active="1"))
        self.assertIn("key=new.person@example.org", r.headers["Location"])
        r = self.post("/admin/people/new", dict(email="not-an-email", display_name="X", app_role="standard", active="1"))
        self.assertIn("right format", r.get_data(as_text=True))

    def test_settings_validated(self):
        r = self.post("/admin/settings/edit?key=fy_start_month", dict(setting_value="13", description="x"))
        self.assertIn("month number from 1", r.get_data(as_text=True))

    def test_retired_hidden_unless_asked(self):
        self.assertNotIn("PM-0021", self.client.get("/admin/measures").get_data(as_text=True))
        self.assertIn("PM-0021", self.client.get("/admin/measures?show=all").get_data(as_text=True))

    def test_generate_periods(self):
        before = self.repo().count("periods")
        r = self.post("/admin/periods/generate", {"fy": "2027"}, csrf_from="/admin/periods")
        self.assertEqual(r.status_code, 302)
        repo = self.repo()
        self.assertGreater(repo.count("periods"), before + 400)
        self.assertIsNotNone(repo.get("periods", "FY-2027-28"))
        again = repo.count("periods")
        self.post("/admin/periods/generate", {"fy": "2027"}, csrf_from="/admin/periods")
        self.assertEqual(self.repo().count("periods"), again, "running it twice adds nothing")

    def test_no_delete_routes(self):
        for rule in self.app.url_map.iter_rules():
            self.assertNotIn("delete", rule.rule)
            self.assertNotIn("DELETE", rule.methods)


if __name__ == "__main__":
    unittest.main()
