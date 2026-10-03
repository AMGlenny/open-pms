"""WCAG 2.2 AA checks a machine can do, run on the real rendered pages.

docs/accessibility.md lists the manual checks still needed (screen reader,
keyboard-only, zoom and phone).
"""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

from .helpers import AppCase

CSS = (Path(__file__).resolve().parent.parent / "openpms" / "static" / "app.css").read_text()


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags, self.labels_for, self.ids, self.h1, self.title = [], set(), [], 0, ""
        self._in_title = False
        self.lang = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if a.get("id"):
            self.ids.append(a["id"])
        if tag == "label" and a.get("for"):
            self.labels_for.add(a["for"])
        if tag == "h1":
            self.h1 += 1
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def luminance(hex6):
    def ch(v):
        c = int(v, 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(hex6[0:2]) + 0.7152 * ch(hex6[2:4]) + 0.0722 * ch(hex6[4:6])


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class PageTests(AppCase, unittest.TestCase):
    PAGES = ["/", "/week?week=2026-09-21&team=ST-SDS-A", "/team?week=2026-09-21&team=ST-SDS-A", "/tasks/new",
             "/tasks/TSK-00001", "/problems/new", "/problems/PRB-00001", "/measures/", "/measures/?tab=review",
             "/measures/?tab=all", "/measures/value?key=PM-0002|M-2026-08", "/measures/value?key=PM-0010|F-2026-09-07",
             "/measures/value?key=PM-0020|FY-2025-26", "/measures/targets",
             "/measures/targets?measure_code=PM-0002&ref_type=target&from_date=2026-04-01&to_date=2027-03-31", "/admin/", "/admin/audit", "/admin/measures", "/admin/measures/new", "/admin/measures/item?key=PM-0002",
             "/admin/measures/edit?key=PM-0002", "/admin/measures/history?key=PM-0002", "/admin/people",
             "/admin/people/new", "/admin/people/item?key=priya.shah@example.org", "/admin/periods",
             "/admin/settings/edit?key=fy_start_month", "/admin/reference_values/new", "/exports/",
             "/exports/scheduled", "/exports/links", "/admin/export_jobs/new", "/no-such-page"]

    def pages(self):
        out = [("/login", self.client.get("/login").get_data(as_text=True))]
        self.login()
        for p in self.PAGES:
            out.append((p, self.client.get(p).get_data(as_text=True)))
        r = self.post("/exports/links", dict(name="Dashboard", dataset="measures"), csrf_from="/exports/links")
        out.append(("/exports/links (made)", r.get_data(as_text=True)))
        token = self.csrf("/exports/")
        r = self.client.post("/exports/download", data={"csrf_token": token, "dataset": "quarter_pack", "quarter": "x"})
        out.append(("/exports/download (errors)", r.get_data(as_text=True)))
        url = re.search(r'value="http://pms\.test(/data/[^"]+)"', out[-2][1]).group(1)
        out.append((url, self.app.test_client().get(url).get_data(as_text=True)))
        # A form with errors, so the error summary and field errors are checked too.
        token = self.csrf("/admin/measures/new")
        r = self.client.post("/admin/measures/new", data={"csrf_token": token, "unit": "nonsense"})
        out.append(("/admin/measures/new (errors)", r.get_data(as_text=True)))
        return out

    def test_structure(self):
        for path, html in self.pages():
            p = Page(html)
            self.assertEqual(p.lang, "en", path)
            self.assertTrue(p.title.strip(), f"{path}: page title (2.4.2)")
            self.assertEqual(p.h1, 1, f"{path}: exactly one h1 (1.3.1)")
            self.assertIn("main", p.ids, f"{path}: main landmark")
            self.assertTrue(any(t == "a" and a.get("href") == "#main" for t, a in p.tags), f"{path}: skip link (2.4.1)")
            dupes = {i for i in p.ids if p.ids.count(i) > 1}
            self.assertFalse(dupes, f"{path}: duplicate ids {dupes} (4.1.1)")

    def test_every_field_has_a_label(self):
        for path, html in self.pages():
            p = Page(html)
            for tag, a in p.tags:
                if tag in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit"):
                    labelled = a.get("id") in p.labels_for or a.get("aria-label") or a.get("aria-labelledby")
                    self.assertTrue(labelled, f"{path}: <{tag} name={a.get('name')}> has no label (1.3.1, 4.1.2)")
                for ref in (a.get("aria-describedby") or "").split():
                    self.assertIn(ref, p.ids, f"{path}: aria-describedby points at missing #{ref}")

    def test_errors_announced_and_linked(self):
        _, html = self.pages()[-1]
        self.assertIn('class="error-summary" role="alert"', html)
        for target in re.findall(r'href="#(f-[a-z_]+)"', html):
            self.assertIn(f'id="{target}"', html, "each error links to its field")
        self.assertIn('aria-invalid="true"', html)

    def test_tables_have_header_cells(self):
        for path, html in self.pages():
            if "<table" in html:
                self.assertIn('scope="col"', html, path)

    def test_current_page_marked_in_navigation(self):
        self.login()
        self.assertIn('aria-current="page"', self.client.get("/admin/").get_data(as_text=True))


class ColourTests(unittest.TestCase):
    vars = {k: v.lower() for k, v in re.findall(r"--(c-[a-z-]+):\s*#([0-9a-fA-F]{6})", CSS)}

    def test_text_contrast(self):
        for fg in ("c-text", "c-muted", "c-accent", "c-accent-dark", "c-error", "c-success"):
            for bg in ("c-panel", "c-page"):
                self.assertGreaterEqual(contrast(self.vars[fg], self.vars[bg]), 4.5, f"{fg} on {bg} (1.4.3)")
        for bg in ("c-header", "c-accent", "c-accent-dark"):
            self.assertGreaterEqual(contrast("ffffff", self.vars[bg]), 4.5, f"white on {bg}")

    def test_borders_and_focus(self):
        self.assertGreaterEqual(contrast(self.vars["c-border"], "ffffff"), 3, "input borders (1.4.11)")
        self.assertGreaterEqual(contrast(self.vars["c-focus"], self.vars["c-header"]), 3, "focus ring on the header")
        self.assertIn("box-shadow: 0 0 0 6px var(--c-text)", CSS, "dark outer ring keeps focus visible on white (2.4.7)")

    def test_targets_at_least_44px(self):
        self.assertIn("min-height: 2.75rem", CSS)


if __name__ == "__main__":
    unittest.main()


class UpdaterFormTests(AppCase, unittest.TestCase):
    def test_value_entry_form_is_labelled(self):
        self.login(email="nadia.hassan@example.org")
        for key in ("PM-0020|FY-2025-26", "PM-0012|D-2026-09-29"):  # yes/no radios, and a number
            html = self.client.get(f"/measures/value?key={key}").get_data(as_text=True)
            p = Page(html)
            fields = [(t, a) for t, a in p.tags if t in ("input", "select", "textarea") and a.get("type") not in ("hidden",)]
            self.assertIn('name="value_missing"', html, f"{key}: Nadia is an updater, so the form shows")
            for tag, a in fields:
                self.assertIn(a.get("id"), p.labels_for, f"{key}: <{tag} name={a.get('name')}> has no label")
            if 'type="radio"' in html:
                self.assertIn("<legend>", html, "radio buttons need a group label (1.3.1)")
