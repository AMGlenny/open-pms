"""Realistic, fictional sample data for a made-up public body, covering every
frequency and workflow state.

All people are made up and use example.org addresses. Values are generated
from a fixed random seed so every build produces identical files.
"""
import random
from datetime import date, datetime, time, timedelta, timezone

from . import periods as periods_mod
from . import rules, workflow

AS_OF = date(2026, 9, 30)

# Sample term dates (England-style). Admins edit the term rows in periods.
TERM_DATES = [
    ("2025-26", "AUT", "Autumn Term 2025", date(2025, 9, 3), date(2025, 12, 19)),
    ("2025-26", "SPR", "Spring Term 2026", date(2026, 1, 5), date(2026, 3, 27)),
    ("2025-26", "SUM", "Summer Term 2026", date(2026, 4, 13), date(2026, 7, 22)),
    ("2026-27", "AUT", "Autumn Term 2026", date(2026, 9, 2), date(2026, 12, 18)),
    ("2026-27", "SPR", "Spring Term 2027", date(2027, 1, 4), date(2027, 3, 26)),
    ("2026-27", "SUM", "Summer Term 2027", date(2027, 4, 12), date(2027, 7, 21)),
]
FORTNIGHT_ANCHOR = date(2025, 4, 7)
FIRST_FY, LAST_FY, DAILY_FROM_FY = 2025, 2026, 2026
DOMAIN = "example.org"


def _email(name):
    return f"{name}@{DOMAIN}"


def _dt(d, hour=10, minute=0):
    return datetime.combine(d, time(hour, minute), tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
ORG_UNITS = [
    ("WS-JOBS", "Good Jobs and Skills", "workstream", None),
    ("TM-SDS", "Supply Delivery Strategies", "team", "WS-JOBS"),
    ("ST-SDS-A", "Team A", "sub_team", "TM-SDS"),
    ("ST-SDS-B", "Team B", "sub_team", "TM-SDS"),
    ("TM-EMP", "Employer Engagement", "team", "WS-JOBS"),
    ("WS-HOMES", "Homes", "workstream", None),
    ("TM-HSG", "Housing Delivery", "team", "WS-HOMES"),
    ("WS-TRANS", "Transport", "workstream", None),
    ("TM-BUS", "Bus Performance", "team", "WS-TRANS"),
    ("WS-CORP", "Corporate Performance and Insight", "workstream", None),
    ("TM-DATA", "Data and Analytics", "team", "WS-CORP"),
    ("TM-EDU", "Education and Skills", "team", "WS-JOBS"),
]

# email name, display name, org unit, line manager, app role, active
PEOPLE = [
    ("sam.patel", "Sam Patel", "WS-CORP", None, "admin", True),
    ("jordan.hughes", "Jordan Hughes", "ST-SDS-A", "sam.patel", "standard", True),
    ("priya.shah", "Priya Shah", "ST-SDS-A", "jordan.hughes", "standard", True),
    ("tom.walsh", "Tom Walsh", "ST-SDS-A", "jordan.hughes", "standard", True),
    ("chloe.bennett", "Chloe Bennett", "ST-SDS-A", "jordan.hughes", "standard", True),
    ("marcus.reid", "Marcus Reid", "ST-SDS-B", "jordan.hughes", "standard", True),
    ("aisha.khan", "Aisha Khan", "ST-SDS-A", "jordan.hughes", "standard", True),
    ("daniel.okafor", "Daniel Okafor", "TM-HSG", "sam.patel", "standard", True),
    ("ellie.brooks", "Ellie Brooks", "TM-HSG", "daniel.okafor", "standard", True),
    ("rhys.evans", "Rhys Evans", "TM-BUS", "sam.patel", "standard", True),
    ("nadia.hassan", "Nadia Hassan", "TM-DATA", "sam.patel", "standard", True),
    ("owen.price", "Owen Price", "TM-EDU", "sam.patel", "standard", True),
    ("ruth.clarke", "Ruth Clarke", "WS-CORP", "sam.patel", "viewer", True),
    ("gary.fox", "Gary Fox", "TM-EMP", "sam.patel", "standard", False),
]

GROUPS = [
    ("TH-JOBS", "Good jobs and skills", "theme"),
    ("TH-HOMES", "Safe, decent and affordable homes", "theme"),
    ("TH-TRANSPORT", "An integrated transport network", "theme"),
    ("TH-NETZERO", "Net zero and the environment", "theme"),
    ("TH-CYP", "Children and young people", "theme"),
    ("PG-BUSREFORM", "Bus franchising programme", "programme"),
    ("PG-BOOTCAMPS", "Skills Bootcamps", "programme"),
    ("OB-DATA", "Better use of data in decisions", "objective"),
    ("OB-SERVICE", "Reliable, responsive corporate services", "objective"),
]

LOOKUPS = [
    ("category", "economy", "Economy and jobs", 1),
    ("category", "housing", "Housing", 2),
    ("category", "transport", "Transport", 3),
    ("category", "environment", "Environment", 4),
    ("category", "education", "Education", 5),
    ("category", "corporate", "Corporate", 6),
    ("data_source", "internal_mi", "Internal management information", 1),
    ("data_source", "ons", "Office for National Statistics", 2),
    ("data_source", "dfe", "Department for Education", 3),
    ("data_source", "dluhc", "MHCLG returns", 4),
    ("data_source", "operator", "Bus operator returns", 5),
]

SETTINGS = [
    ("organisation_name", "Example Public Body", "Name shown in the header and on exports."),
    ("fy_start_month", "4", "Month the financial year starts (1 to 12). 4 is April (UK). 1 makes the financial year the calendar year."),
    ("ay_start_month", "9", "Month the academic year starts (1 to 12)."),
    ("fortnight_anchor_date", FORTNIGHT_ANCHOR.isoformat(), "Monday that fortnightly periods count from."),
    ("week_start_day", "monday", "Weeks run Monday to Sunday."),
    ("percent_storage", "0_to_100", "Percentages are stored as 0 to 100, so 58 means 58%."),
    ("wellbeing_min_group_size", "5", "Team wellbeing counts are only shown when at least this many people responded."),
    ("archive_closed_after_days", "730", "Closed tasks and problems older than this move to the archive lists."),
    ("reminder_days_before_expected", "5", "Days before expected_by that updaters get a reminder."),
    ("reopen_allowed_role", "admin", "App role allowed to reopen an approved value."),
    ("base_url", "http://localhost:8000", "Web address of this installation, used for links in emails."),
]

# ---------------------------------------------------------------------------
# Measures. sim = (start, trend per period, noise, target, tolerance)
# roles = (owner, [updaters], approver)
# ---------------------------------------------------------------------------
DOC_A = "Corporate Strategy Framework 2025-28"
DOC_B = "Housing Delivery Plan 2025-30"
DOC_T = "Transport Delivery Plan"
DOC_C = "Corporate Plan 2026-27"
DOC_E = "Education and Skills Plan"
DOC_N = "Five-Year Environment Plan"

MEASURES = [
    dict(code="PM-0001", name="Good jobs and skills: overall assessment", ref="1", doc=DOC_A, parent=None,
         cls="measure", type="summary", unit="text", dp=0, pol="neither", freq="quarterly", agg="do_not_combine", lag=45,
         cat="economy", src="Internal assessment", org="TM-SDS",
         desc="Quarterly narrative judgement on progress across the good jobs measures.",
         defn="Owner's summary of measures 1.01 to 1.03, agreed at the quarterly board.",
         roles=("jordan.hughes", ["priya.shah"], "sam.patel"), groups=[("TH-JOBS", "primary")]),
    dict(code="PM-0002", name="Residents supported into work", ref="1.01", doc=DOC_A, parent="PM-0001",
         cls="kpi", type="output", unit="count", dp=0, pol="higher_is_better", freq="monthly", agg="sum", lag=30,
         cat="economy", src="Work and Skills programme MI", org="ST-SDS-A",
         desc="Residents who started paid work after support from a local employment programme.",
         defn="Count of job starts verified by providers in the month. Excludes starts under 16 hours a week.",
         roles=("jordan.hughes", ["priya.shah", "tom.walsh"], "sam.patel"), groups=[("TH-JOBS", "primary"), ("PG-BOOTCAMPS", "contributes_to")],
         sim=(410, 6, 45, 450, 400)),
    dict(code="PM-0003", name="Apprenticeship achievement rate", ref="1.02", doc=DOC_A, parent="PM-0001",
         cls="okr", type="outcome", unit="percent", dp=1, pol="higher_is_better", freq="quarterly", agg="average", lag=45,
         cat="economy", src="DfE apprenticeship data", org="ST-SDS-A",
         desc="Share of apprentices who complete and pass their apprenticeship.",
         defn="Achievements divided by leavers in the quarter, times 100.",
         roles=("jordan.hughes", ["chloe.bennett"], "sam.patel"), groups=[("TH-JOBS", "primary"), ("TH-CYP", "contributes_to")],
         sim=(55.0, 0.8, 2.5, 58.0, 55.0)),
    dict(code="PM-0004", name="Good Employment Charter members", ref="1.03", doc=DOC_A, parent="PM-0001",
         cls="measure", type="output", unit="count", dp=0, pol="higher_is_better", freq="monthly", agg="latest", lag=10,
         cat="economy", src="Charter membership database", org="TM-EMP",
         desc="Employers signed up as members of the Good Employment Charter.",
         defn="Count of member organisations on the last day of the month.",
         roles=("jordan.hughes", ["aisha.khan"], "sam.patel"), groups=[("TH-JOBS", "primary")],
         sim=(820, 9, 4, None, None), target_only=880),
    dict(code="PM-0005", name="Housing supply summary: net additional homes", ref="1.01", doc=DOC_B, parent=None,
         cls="kpi", type="summary", unit="count", dp=0, pol="higher_is_better", freq="annual", agg="sum", lag=90,
         cat="housing", src="MHCLG housing supply returns", org="TM-HSG",
         desc="All net additional homes delivered across the area.",
         defn="Net additions (new build plus conversions minus demolitions) in the financial year.",
         roles=("daniel.okafor", ["ellie.brooks"], "sam.patel"), groups=[("TH-HOMES", "primary")],
         sim=(11800, 0, 300, 12500, 11500)),
    dict(code="PM-0006", name="Affordable homes delivered", ref="1.01", doc=DOC_B, parent="PM-0005",
         cls="kpi", type="output", unit="count", dp=0, pol="higher_is_better", freq="annual", agg="sum", lag=90,
         cat="housing", src="MHCLG affordable housing returns", org="TM-HSG",
         desc="Affordable homes completed. Shares reference 1.01 with its parent in the source plan.",
         defn="Completions of social rent, affordable rent and shared ownership homes in the financial year.",
         roles=("daniel.okafor", ["ellie.brooks"], "sam.patel"), groups=[("TH-HOMES", "primary")],
         sim=(2650, 0, 150, 3000, 2700)),
    dict(code="PM-0007", name="Households in temporary accommodation", ref="1.02", doc=DOC_B, parent="PM-0005",
         cls="kpi", type="outcome", unit="count", dp=0, pol="lower_is_better", freq="monthly", agg="latest", lag=45,
         cat="housing", src="Local authority H-CLIC returns", org="TM-HSG",
         desc="Households living in temporary accommodation at month end.",
         defn="Snapshot count on the last day of the month across all districts.",
         roles=("daniel.okafor", ["ellie.brooks"], "sam.patel"), groups=[("TH-HOMES", "primary")],
         sim=(5200, -12, 60, 5000, 5250)),
    dict(code="PM-0008", name="People sleeping rough (annual snapshot)", ref="1.03", doc=DOC_B, parent="PM-0005",
         cls="measure", type="outcome", unit="count", dp=0, pol="lower_is_better", freq="calendar_year", agg="latest", lag=120,
         cat="housing", src="Annual rough sleeping snapshot", org="TM-HSG",
         desc="People found sleeping rough on a single autumn night.",
         defn="Official autumn count or estimate, summed across all districts.",
         roles=("daniel.okafor", ["ellie.brooks"], "sam.patel"), groups=[("TH-HOMES", "contributes_to")],
         sim=(145, -8, 6, None, None)),
    dict(code="PM-0009", name="Bus journeys", ref="T.01", doc=DOC_T, parent=None,
         cls="kpi", type="output", unit="count", dp=0, pol="higher_is_better", freq="weekly", agg="sum", lag=7,
         cat="transport", src="Operator ticketing returns", org="TM-BUS",
         desc="Passenger journeys on franchised bus services.",
         defn="Boardings recorded by ticket machines, Monday to Sunday.",
         roles=("rhys.evans", ["rhys.evans"], "sam.patel"), groups=[("TH-TRANSPORT", "primary"), ("PG-BUSREFORM", "primary")],
         sim=(3_950_000, 4_000, 60_000, 4_000_000, 3_900_000)),
    dict(code="PM-0010", name="Bus services running on time", ref="T.02", doc=DOC_T, parent=None,
         cls="kpi", type="outcome", unit="percent", dp=1, pol="higher_is_better", freq="fortnightly", agg="average", lag=5,
         cat="transport", src="Automatic vehicle location data", org="TM-BUS",
         desc="Share of timed stops served between 1 minute early and 5 minutes late.",
         defn="On-time departures divided by all timed departures, times 100.",
         roles=("rhys.evans", ["rhys.evans", "nadia.hassan"], "sam.patel"), groups=[("TH-TRANSPORT", "primary"), ("PG-BUSREFORM", "contributes_to")],
         sim=(82.0, 0.2, 1.8, 85.0, 80.0)),
    dict(code="PM-0011", name="Contact centre calls answered", ref="C.01", doc=DOC_C, parent=None,
         cls="measure", type="output", unit="count", dp=0, pol="higher_is_better", freq="daily", agg="sum", lag=1,
         cat="corporate", src="Telephony system", org="TM-DATA",
         desc="Calls answered by the customer contact centre.",
         defn="Answered inbound calls, 08:00 to 18:00.",
         roles=("sam.patel", ["nadia.hassan"], "jordan.hughes"), groups=[("OB-SERVICE", "primary")],
         sim=(1750, 0, 140, None, None), target_only=1700, capacity=2000),
    dict(code="PM-0012", name="Website availability", ref="C.02", doc=DOC_C, parent=None,
         cls="kpi", type="outcome", unit="percent", dp=2, pol="higher_is_better", freq="daily", agg="average", lag=1,
         cat="corporate", src="Uptime monitoring", org="TM-DATA",
         desc="Share of the day the public website was available.",
         defn="Minutes available divided by 1,440, times 100.",
         roles=("sam.patel", ["nadia.hassan"], "jordan.hughes"), groups=[("OB-SERVICE", "primary")],
         sim=(99.9, 0, 0.12, 99.9, 99.5)),
    dict(code="PM-0013", name="Revenue spend", ref="C.03", doc=DOC_C, parent=None,
         cls="measure", type="output", unit="gbp", dp=0, pol="neither", freq="monthly", agg="sum", lag=20,
         cat="corporate", src="Finance ledger", org="WS-CORP",
         desc="Revenue spend in the month. Under and overspend are both a concern, so no RAG.",
         defn="Actual revenue expenditure posted to the ledger for the month.",
         roles=("sam.patel", ["nadia.hassan"], "jordan.hughes"), groups=[("OB-SERVICE", "related")],
         sim=(2_450_000, 5_000, 120_000, None, None)),
    dict(code="PM-0014", name="Territorial carbon emissions", ref="N.01", doc=DOC_N, parent=None,
         cls="okr", type="outcome", unit="number", dp=1, pol="lower_is_better", freq="calendar_year", agg="sum", lag=540,
         cat="environment", src="DESNZ local authority emissions", org="WS-CORP",
         desc="Greenhouse gas emissions in kilotonnes CO2 equivalent.",
         defn="Territorial emissions within the scope of influence of local authorities, ktCO2e.",
         roles=("sam.patel", ["nadia.hassan"], "jordan.hughes"), groups=[("TH-NETZERO", "primary")],
         sim=(11250.0, -300, 80, 11000.0, 11400.0)),
    dict(code="PM-0015", name="School attendance rate", ref="E.01", doc=DOC_E, parent=None,
         cls="kpi", type="outcome", unit="percent", dp=1, pol="higher_is_better", freq="term", agg="average", lag=30,
         cat="education", src="DfE school attendance data", org="TM-EDU",
         desc="Sessions attended as a share of possible sessions.",
         defn="Attended sessions divided by possible sessions, times 100, all state schools.",
         roles=("owen.price", ["owen.price"], "sam.patel"), groups=[("TH-CYP", "primary")],
         sim=(93.2, 0.1, 0.4, 94.0, 93.0)),
    dict(code="PM-0016", name="Persistent absence rate", ref="E.02", doc=DOC_E, parent=None,
         cls="kpi", type="outcome", unit="percent", dp=1, pol="lower_is_better", freq="term", agg="average", lag=30,
         cat="education", src="DfE school attendance data", org="TM-EDU",
         desc="Pupils missing 10% or more of possible sessions.",
         defn="Persistently absent pupils divided by all pupils, times 100.",
         roles=("owen.price", ["owen.price"], "sam.patel"), groups=[("TH-CYP", "primary")],
         sim=(19.5, -0.4, 0.6, 18.0, 20.0)),
    dict(code="PM-0017", name="16 and 17 year olds not in education, employment or training", ref="E.03", doc=DOC_E, parent=None,
         cls="measure", type="outcome", unit="percent", dp=1, pol="lower_is_better", freq="academic_year", agg="latest", lag=60,
         cat="education", src="DfE NEET and participation data", org="TM-EDU",
         desc="Share of 16 and 17 year olds who are NEET or whose activity is not known.",
         defn="December to February average, NEET plus not known, times 100.",
         roles=("owen.price", ["owen.price"], "sam.patel"), groups=[("TH-CYP", "primary"), ("TH-JOBS", "contributes_to")],
         sim=(5.4, 0, 0.1, None, None), target_only=5.0),
    dict(code="PM-0018", name="Skills Bootcamp starts", ref="S.01", doc=DOC_E, parent=None,
         cls="okr", type="output", unit="count", dp=0, pol="higher_is_better", freq="quarterly", agg="sum", lag=30,
         cat="economy", src="Bootcamp provider returns", org="TM-EDU",
         desc="Learners starting a Skills Bootcamp.",
         defn="Learners who attended the first session in the quarter.",
         roles=("owen.price", ["chloe.bennett", "owen.price"], "sam.patel"), groups=[("PG-BOOTCAMPS", "primary"), ("TH-JOBS", "contributes_to")],
         sim=(620, 25, 40, 700, 620)),
    dict(code="PM-0019", name="Data requests completed within SLA", ref="D.01", doc=DOC_C, parent=None,
         cls="measure", type="output", unit="percent", dp=0, pol="higher_is_better", freq="weekly", agg="average", lag=None,
         cat="corporate", src="Service desk", org="TM-DATA",
         desc="Data and analysis requests closed within the agreed 10 working days.",
         defn="Requests closed within SLA divided by all requests closed in the week, times 100.",
         roles=("sam.patel", ["nadia.hassan"], "jordan.hughes"), groups=[("OB-DATA", "primary")],
         sim=(88, 0, 5, None, None), target_only=90),
    dict(code="PM-0020", name="Gender pay gap report published on time", ref="C.04", doc=DOC_C, parent=None,
         cls="measure", type="output", unit="yes_no", dp=0, pol="higher_is_better", freq="annual", agg="latest", lag=180,
         cat="corporate", src="HR", org="WS-CORP",
         desc="Whether the statutory gender pay gap report was published by the deadline.",
         defn="1 if published by the statutory deadline, otherwise 0.",
         roles=("sam.patel", ["nadia.hassan"], "jordan.hughes"), groups=[("OB-SERVICE", "related")],
         sim=(1, 0, 0, None, None), target_only=1),
    dict(code="PM-0021", name="Jobseekers attending recruitment events", ref="1.04", doc=DOC_A, parent="PM-0001",
         cls="measure", type="output", unit="count", dp=0, pol="higher_is_better", freq="monthly", agg="sum", lag=15,
         cat="economy", src="Event booking system", org="TM-EMP", status="retired",
         retired=(date(2026, 1, 15), "Replaced by measure 1.01 when events moved into the employment programme."),
         desc="Residents attending jobs fairs and recruitment events.",
         defn="Unique attendees signed in at events in the month.",
         roles=("jordan.hughes", ["aisha.khan"], "sam.patel"), groups=[("TH-JOBS", "related")],
         sim=(640, -10, 70, None, None)),
    dict(code="PM-0022", name="Housing case reviews completed", ref="H.03", doc=DOC_B, parent=None,
         cls="measure", type="output", unit="count", dp=0, pol="higher_is_better", freq="fortnightly", agg="sum", lag=7,
         cat="housing", src="Case management system", org="TM-HSG",
         desc="Temporary accommodation case reviews completed.",
         defn="Reviews signed off by a team leader in the fortnight.",
         roles=("daniel.okafor", ["ellie.brooks"], "sam.patel"), groups=[("TH-HOMES", "contributes_to")],
         sim=(95, 1, 8, None, None), target_only=100),
]

HISTORY = {"daily": 14, "weekly": 12, "fortnightly": 8, "monthly": 12}

TEXT_ASSESSMENTS = [
    "Steady progress. Job starts are ahead of profile and charter membership keeps growing. Achievement rates remain the main risk.",
    "Mixed quarter. Job starts dipped over the summer but recovered in September. Apprenticeship achievement improved.",
    "Good quarter overall. Two of three child measures on track; achievement rate still below target.",
    "Positive. Employment support is performing well and bootcamp referrals are adding to job starts.",
    "Early signs of improvement in achievement rates after the provider review.",
]

# Special workflow states so every screen has something to show.
SPECIAL = {
    ("PM-0002", "latest"): "submitted",
    ("PM-0007", "latest"): "returned",
    ("PM-0010", "latest"): "resubmitted",
    ("PM-0012", "latest"): "draft",
    ("PM-0004", "latest"): "reopened",
    ("PM-0020", "latest"): "not_started",
    ("PM-0003", "Q-2025-26-Q3"): "missing",
}


def _narrative(m, rag, value, period_label):
    if rag == "red":
        return f"{period_label} is below where we need to be. Causes have been reviewed with delivery partners and a recovery plan is in place."
    if rag == "amber":
        return f"{period_label} is within tolerance but short of target. We expect to close the gap next period."
    if rag == "green":
        return f"On track for {period_label}."
    return "Figures checked against the source system."


def _value(m, i, rng):
    start, trend, noise, _, _ = m["sim"]
    if m["unit"] == "yes_no":
        return 1
    v = start + trend * i + rng.gauss(0, noise)
    if m["unit"] == "percent":
        v = max(0.0, min(100.0, v))
    if m["unit"] in ("count", "gbp"):
        v = max(0, round(v))
    else:
        v = round(v, m["dp"])
    return v


def build():
    rng = random.Random(20260930)
    data = {}

    periods = periods_mod.generate(FIRST_FY, LAST_FY, DAILY_FROM_FY, terms=TERM_DATES,
                                    fortnight_anchor=FORTNIGHT_ANCHOR)
    data["periods"] = periods
    by_key = {p["period_key"]: p for p in periods}

    data["org_units"] = [
        dict(org_unit_key=k, unit_name=n, unit_level=lvl, parent_key=parent, active=True)
        for k, n, lvl, parent in ORG_UNITS
    ]
    data["people"] = [
        dict(email=_email(e), display_name=n, org_unit_key=o,
             line_manager_email=_email(lm) if lm else None, app_role=r, active=a)
        for e, n, o, lm, r, a in PEOPLE
    ]
    names = {_email(e): n for e, n, *_ in PEOPLE}
    data["groups"] = [
        dict(group_key=k, group_name=n, group_type=t, description=None, active=True)
        for k, n, t in GROUPS
    ]
    data["lookups"] = [
        dict(lookup_key=f"{t}|{c}", lookup_type=t, code=c, label=l, sort_order=s, active=True)
        for t, c, l, s in LOOKUPS
    ]
    data["settings"] = [dict(setting_key=k, setting_value=v, description=d) for k, v, d in SETTINGS]

    measures, roles, links = [], [], []
    for m in MEASURES:
        retired = m.get("retired")
        measures.append(dict(
            measure_code=m["code"], measure_name=m["name"], source_ref=m["ref"], source_document=m["doc"],
            parent_measure_code=m["parent"], description=m["desc"], definition=m["defn"],
            measure_class=m["cls"], measure_type=m["type"], unit=m["unit"], decimal_places=m["dp"],
            polarity=m["pol"], frequency=m["freq"], aggregation_method=m["agg"], expected_lag_days=m["lag"],
            category=m["cat"], data_source=m["src"], org_unit_key=m["org"],
            status=m.get("status", "active"),
            retired_date=retired[0] if retired else None, retired_reason=retired[1] if retired else None,
        ))
        owner, updaters, approver = m["roles"]
        for role, people in (("owner", [owner]), ("updater", updaters), ("approver", [approver])):
            for p in people:
                roles.append(dict(role_key=f"{m['code']}|{_email(p)}|{role}", measure_code=m["code"],
                                  email=_email(p), role=role, active=True,
                                  start_date=date(2025, 4, 1), end_date=None))
        for g, rel in m["groups"]:
            links.append(dict(link_key=f"{m['code']}|{g}", measure_code=m["code"], group_key=g,
                              relationship_type=rel, active=True))
    data["measures"] = measures
    data["measure_roles"] = roles
    data["measure_links"] = links

    refs, subs, versions, comments, audit, rpt = [], [], [], [], [], []
    comment_no = [0]
    audit_no = [0]

    def add_comment(skey, ver, reviewer, action, text, when, resolved=False, resolved_by=None, resolved_date=None):
        comment_no[0] += 1
        comments.append(dict(comment_ref=f"RC-{comment_no[0]:05d}", submission_key=skey, version_no=ver,
                             reviewer_email=reviewer, action=action, comment=text, comment_date=when,
                             resolved=resolved, resolved_by=resolved_by, resolved_date=resolved_date))

    def add_audit(list_name, key, action, field, old, new, who, when):
        audit_no[0] += 1
        audit.append(dict(audit_ref=f"AUD-{audit_no[0]:07d}", list_name=list_name, item_key=key, action=action,
                          field_name=field, old_value=None if old is None else str(old),
                          new_value=None if new is None else str(new), changed_by=who, changed_at=when))

    for m in MEASURES:
        code = m["code"]
        mrow = next(x for x in measures if x["measure_code"] == code)
        owner, updaters, approver = m["roles"]
        updater, approver = _email(updaters[0]), _email(approver)
        retired = m.get("retired")
        end_limit = retired[0] if retired else AS_OF
        plist = [p for p in periods if p["period_type"] == m["freq"] and p["end_date"] < end_limit]
        if m["freq"] in HISTORY:
            plist = plist[-HISTORY[m["freq"]]:]
        # Reference values: every period with data plus the next two.
        future = [p for p in periods if p["period_type"] == m["freq"] and p["end_date"] >= end_limit][:2]
        start, trend, noise, target, tolerance = m.get("sim", (None, 0, 0, None, None))
        target_only = m.get("target_only")
        ref_lookup = {}
        for i, p in enumerate(plist + future):
            vals = {}
            if target is not None:
                vals["target"] = target
                if m["cls"] in ("kpi", "okr") and tolerance is not None:
                    vals["tolerance"] = tolerance
            elif target_only is not None:
                vals["target"] = target_only
            if m.get("capacity"):
                vals["capacity"] = m["capacity"]
            if i == 0 and m["unit"] != "text" and m["unit"] != "yes_no":
                vals["baseline"] = start
            for rtype, v in vals.items():
                refs.append(dict(ref_key=f"{code}|{p['period_key']}|{rtype}", measure_code=code,
                                 period_key=p["period_key"], ref_type=rtype, ref_value=v,
                                 notes="Baseline is the first period in the plan." if rtype == "baseline" else None,
                                 active=True))
            ref_lookup[p["period_key"]] = vals

        if not plist:
            continue
        latest_key = plist[-1]["period_key"]
        for i, p in enumerate(plist):
            pkey = p["period_key"]
            skey = f"{code}|{pkey}"
            exp = rules.expected_by(p["end_date"], m["lag"])
            special = SPECIAL.get((code, "latest") if pkey == latest_key else (code, pkey))
            available = exp is None or exp <= AS_OF
            if not available and special is None:
                special = "awaiting"
            if code == "PM-0019" and pkey == latest_key:
                special = "awaiting"

            sub = dict(submission_key=skey, measure_code=code, period_key=pkey, period_end=p["end_date"], status="approved",
                       expected_by=exp, current_version=0, approved_version=None, submitted_date=None,
                       approved_by=None, approved_date=None)
            subs.append(sub)
            if special in ("awaiting", "not_started"):
                sub["status"] = "not_started"
                continue

            # Timeline: entered a few days before expected_by (or after period end).
            base = exp if exp is not None else p["end_date"] + timedelta(days=3)
            entered = min(base - timedelta(days=rng.randint(0, 3)), AS_OF - timedelta(days=2))
            entered = max(entered, p["end_date"] + timedelta(days=1)) if p["end_date"] < AS_OF - timedelta(days=1) else p["end_date"]
            entered_dt = _dt(entered, 9 + rng.randint(0, 6), rng.choice([0, 15, 30, 45]))
            submitted_dt = entered_dt + timedelta(hours=rng.randint(1, 5))
            approved_dt = min(submitted_dt + timedelta(days=rng.randint(1, 4)), _dt(AS_OF, 9))

            missing = special == "missing"
            value = None if (missing or m["unit"] == "text") else _value(m, i, rng)
            text = None
            if m["unit"] == "text" and not missing:
                text = TEXT_ASSESSMENTS[i % len(TEXT_ASSESSMENTS)]
            vals = ref_lookup.get(pkey, {})
            rag = rules.rag_status(mrow, value, missing, vals.get("target"), vals.get("tolerance"))
            if missing:
                narrative = "Provider data for this quarter was withdrawn after a data quality issue and will not be republished. See the definition note."
            elif m["unit"] == "text":
                narrative = None
            elif rag in rules.OFF_TRACK or rng.random() < 0.5:
                narrative = _narrative(m, rag, value, p["period_label"])
            else:
                narrative = None
            recent = i >= len(plist) - 2
            dq = "provisional" if recent else ("estimated" if rng.random() < 0.1 else "verified")

            def version(no, status, v=value, n=narrative, sub_dt=submitted_dt, r=rag):
                return dict(version_key=f"{skey}|v{no}", submission_key=skey, measure_code=code, period_key=pkey,
                            version_no=no, value_number=v, value_text=text, value_missing=missing,
                            narrative=n, data_quality=dq, entered_by=updater, entered_date=entered_dt,
                            submitted_date=sub_dt, version_status=status,
                            rag_status=r if status == "approved" else None)

            if special == "draft":
                versions.append(version(1, "draft", sub_dt=None))
                sub.update(status="draft", current_version=1)
                add_audit("submission_versions", f"{skey}|v1", "create", None, None, None, updater, entered_dt)
            elif special == "submitted":
                versions.append(version(1, "submitted"))
                sub.update(status="submitted", current_version=1, submitted_date=submitted_dt)
                add_audit("submissions", skey, "status_change", "status", "draft", "submitted", updater, submitted_dt)
            elif special == "returned":
                versions.append(version(1, "returned"))
                sub.update(status="returned", current_version=1, submitted_date=submitted_dt)
                ret_dt = submitted_dt + timedelta(days=1)
                add_comment(skey, 1, approver, "returned",
                            "The narrative does not explain why the figure moved against last month. Please add the main reasons and check the East district figure.",
                            ret_dt)
                add_audit("submissions", skey, "status_change", "status", "submitted", "returned", approver, ret_dt)
            elif special == "resubmitted":
                v1_value = value - 2.1 if value is not None else None
                v1_rag = rules.rag_status(mrow, v1_value, missing, vals.get("target"), vals.get("tolerance"))
                versions.append(version(1, "returned", v=v1_value, n="Slightly down this fortnight.", r=v1_rag))
                ret_dt = submitted_dt + timedelta(hours=20)
                resub_dt = ret_dt + timedelta(hours=26)
                add_comment(skey, 1, approver, "returned",
                            "This looks low. Has the North depot data been included? Please confirm and explain the drop.",
                            ret_dt, resolved=True, resolved_by=updater, resolved_date=resub_dt)
                versions.append(version(2, "submitted", n="Revised: the North depot feed was missing from the first extract. Now included. "
                                        + (narrative or ""), sub_dt=resub_dt))
                sub.update(status="submitted", current_version=2, submitted_date=resub_dt)
                add_audit("submissions", skey, "status_change", "status", "submitted", "returned", approver, ret_dt)
                add_audit("submission_versions", f"{skey}|v2", "create", None, None, None, updater, resub_dt)
                add_audit("submission_versions", f"{skey}|v2", "edit", "value_number", v1_value, value, updater, resub_dt)
                add_audit("submissions", skey, "status_change", "status", "returned", "submitted", updater, resub_dt)
            else:
                versions.append(version(1, "approved"))
                sub.update(status="approved", current_version=1, approved_version=1,
                           submitted_date=submitted_dt, approved_by=approver, approved_date=approved_dt)
                if special == "reopened":
                    reopen_dt = _dt(AS_OF - timedelta(days=1), 11)
                    corrected = value + 3 if value is not None else None
                    versions.append(version(2, "draft", v=corrected,
                                            n="Correction: three members who joined on the last day of the month were missed.",
                                            sub_dt=None))
                    sub.update(status="draft", current_version=2)
                    add_audit("submissions", skey, "reopen", "status", "approved", "draft", "sam.patel@" + DOMAIN, reopen_dt)
                    add_comment(skey, 1, "sam.patel@" + DOMAIN, "reopened",
                                "Reopened: the owner reported that three late joiners were missed from the count.", reopen_dt)

    # rpt_values: one row per approved submission, built with the same code the flows mirror.
    owners = {r["measure_code"]: r["email"] for r in roles if r["role"] == "owner"}
    ver_by_key = {v["version_key"]: v for v in versions}
    mby = {x["measure_code"]: x for x in measures}
    latest_end = {}
    for s in subs:
        if s["approved_version"]:
            end = by_key[s["period_key"]]["end_date"]
            latest_end[s["measure_code"]] = max(latest_end.get(s["measure_code"], end), end)
    for s in subs:
        if not s["approved_version"]:
            continue
        v = ver_by_key[f"{s['submission_key']}|v{s['approved_version']}"]
        mm, p = mby[s["measure_code"]], by_key[s["period_key"]]
        refs_here = {r["ref_type"]: r["ref_value"] for r in refs
                     if r["measure_code"] == s["measure_code"] and r["period_key"] == s["period_key"]}
        owner = owners[mm["measure_code"]]
        rpt.append(workflow.rpt_row(s, v, mm, p, owner, names[owner], refs_here,
                                    p["end_date"] == latest_end[mm["measure_code"]], _dt(AS_OF, 6)))

    data.update(reference_values=refs, submissions=subs, submission_versions=versions,
                review_comments=comments, audit_log=audit, rpt_values=rpt)
    data.update(_weekly_work(rng))
    data["export_requests"] = [
        dict(request_ref="REQ-20260929-0600-full", dataset="full_model", job_code="EXP-FULL-NIGHTLY", quarter_label=None,
             filter_label="Everything", folder_path="full_model",
             requested_by=None, requested_at=_dt(AS_OF - timedelta(days=1), 6), status="done",
             output_url="full_model/latest",
             message="14 tables written.", completed_at=_dt(AS_OF - timedelta(days=1), 6, 9)),
    ]
    data["export_jobs"] = [
        dict(job_code="EXP-FULL-NIGHTLY", job_name="Full data model, nightly", dataset="full_model", format="both",
             frequency="daily", run_day=None, folder_path="full_model", keep_history=True, active=True,
             last_run_at=None, last_run_status=None),
        dict(job_code="EXP-WEEKLY-WORK", job_name="Weekly work, every Monday", dataset="weekly_work", format="csv",
             frequency="weekly", run_day=1, folder_path="weekly_work", keep_history=True, active=True,
             last_run_at=None, last_run_status=None),
        dict(job_code="EXP-QUARTER-PACK", job_name="Quarterly report pack", dataset="quarter_pack", format="xlsx",
             frequency="quarterly", run_day=10, folder_path="quarter_pack", keep_history=True, active=True,
             last_run_at=None, last_run_status=None),
    ]
    return data


TASKS = [
    ("Review whether the weekly slot is still needed", "could", "ST-SDS-A", "group", "OB-SERVICE", "jordan.hughes", date(2026, 8, 3), "open"),
    ("Confirm baseline figures for the new indicator set", "must", "ST-SDS-A", "measure", "PM-0002", "priya.shah", date(2026, 8, 10), "complete"),
    ("Explore linking the portal to Fabric", "could", "ST-SDS-A", "group", "OB-DATA", "tom.walsh", date(2026, 8, 10), "open"),
    ("Set up the automated refresh schedule", "should", "ST-SDS-A", "group", "OB-DATA", "tom.walsh", date(2026, 8, 17), "complete"),
    ("Pilot the new dashboard with one team", "should", "ST-SDS-A", "group", "OB-DATA", "chloe.bennett", date(2026, 8, 17), "open"),
    ("Draft the Q2 performance narrative", "must", "ST-SDS-A", "measure", "PM-0001", "priya.shah", date(2026, 8, 17), "open"),
    ("Agree charter targets for next year", "should", "TM-EMP", "measure", "PM-0004", "aisha.khan", date(2026, 8, 24), "open"),
    ("Chase providers for September job starts", "must", "ST-SDS-A", "measure", "PM-0002", "priya.shah", date(2026, 9, 1), "open"),
    ("Update the apprenticeship definition note", "should", "ST-SDS-A", "measure", "PM-0003", "chloe.bennett", date(2026, 9, 1), "complete"),
    ("Book room for the quarterly board", "could", "ST-SDS-B", None, None, "marcus.reid", date(2026, 9, 7), "cancelled"),
    ("Prepare employer survey questions", "should", "ST-SDS-B", "measure", "PM-0004", "marcus.reid", date(2026, 9, 7), "open"),
    ("Reconcile temporary accommodation returns", "must", "TM-HSG", "measure", "PM-0007", "ellie.brooks", date(2026, 9, 14), "open"),
    ("Map bus data feeds by depot", "should", "TM-BUS", "measure", "PM-0010", "rhys.evans", date(2026, 9, 14), "complete"),
    ("Write up the North depot data fix", "could", "TM-BUS", "measure", "PM-0010", "rhys.evans", date(2026, 9, 21), "open"),
    ("Check term dates for 2027-28 with councils", "should", "TM-EDU", "group", "TH-CYP", "owen.price", date(2026, 9, 21), "open"),
    ("Train updaters on the new submission tool", "must", "TM-DATA", "group", "OB-DATA", "nadia.hassan", date(2026, 9, 28), "open"),
]

PROBLEMS = [
    ("Locality returns arriving late", "Three councils send monthly returns after the 20th, which delays job start figures.", "ST-SDS-A", "priya.shah", date(2026, 8, 5), "jordan.hughes", "high", "medium", "measure", "PM-0002", "open"),
    ("Indicator definitions inconsistent across teams", "Two teams count job starts differently, so totals do not reconcile.", "ST-SDS-A", "priya.shah", date(2026, 8, 12), "jordan.hughes", "high", "high", "group", "OB-DATA", "open"),
    ("Manual rework on every refresh", "The dashboard needs about two hours of manual fixes after each refresh.", "ST-SDS-A", "tom.walsh", date(2026, 8, 12), "jordan.hughes", "medium", "medium", "group", "OB-DATA", "closed"),
    ("No agreed baseline for two new measures", "Baselines for the new charter measures have not been signed off.", "TM-EMP", "aisha.khan", date(2026, 8, 19), "jordan.hughes", "medium", "low", "measure", "PM-0004", "open"),
    ("Portal access requests taking too long", "New starters wait over a week for access to the data portal.", "TM-DATA", "nadia.hassan", date(2026, 8, 26), "sam.patel", "low", "medium", "group", "OB-SERVICE", "open"),
    ("Duplicate records in the master list", "About 4% of employer records are duplicated.", "TM-EMP", "aisha.khan", date(2026, 9, 2), "jordan.hughes", "medium", "medium", "measure", "PM-0004", "open"),
    ("Board pack turnaround too tight", "Two working days between data lock and board pack deadline is not enough.", "WS-CORP", "sam.patel", date(2026, 9, 9), "sam.patel", "high", "medium", "group", "OB-SERVICE", "open"),
    ("North depot missing from bus extract", "The on-time extract dropped one depot for a fortnight.", "TM-BUS", "rhys.evans", date(2026, 9, 23), "rhys.evans", "medium", "high", "measure", "PM-0010", "closed"),
]

WEEKLY_PEOPLE = ["jordan.hughes", "priya.shah", "tom.walsh", "chloe.bennett", "marcus.reid", "aisha.khan",
                 "ellie.brooks", "rhys.evans"]

SUCCESSES = [
    "Providers confirmed September job starts early.",
    "Dashboard pilot feedback was positive.",
    "Charter webinar had 60 employers attend.",
    "Closed the depot data issue within two days.",
    "New starter got portal access in one day after the process change.",
    None,
]
COMMUNICATIONS = [
    "The refresh now runs automatically at 6am.",
    "Term dates for next year need checking with councils by November.",
    None,
    "Board deadline moved to the second Thursday.",
]


def _weekly_work(rng):
    people = {e: (o, lm) for e, _, o, lm, *_ in PEOPLE}
    weeks = [date(2026, 8, 17) + timedelta(weeks=i) for i in range(7)]  # to w/c 28 Sep
    updates, wellbeing = [], []
    for w in weeks:
        for p in WEEKLY_PEOPLE:
            if w == weeks[-1] and rng.random() < 0.4:
                continue  # not everyone has done this week's yet
            org, lm = people[p]
            saved = _dt(w + timedelta(days=rng.randint(0, 4)), 15, 30)
            updates.append(dict(update_key=f"{_email(p)}|{w.isoformat()}", email=_email(p), week_start=w,
                                org_unit_key=org, successes=rng.choice(SUCCESSES),
                                communication=rng.choice(COMMUNICATIONS),
                                workload=rng.choice(["light", "manageable", "manageable", "heavy", "overloaded"]),
                                submitted_at=saved))
            wellbeing.append(dict(checkin_key=f"{_email(p)}|{w.isoformat()}", email=_email(p),
                                  line_manager_email=_email(lm), org_unit_key=org, week_start=w,
                                  wellbeing=rng.choice(["thriving", "ok", "ok", "ok", "struggling"]),
                                  comments=None, submitted_at=saved))
    tasks = []
    for i, (name, pri, org, ctype, ckey, who, raised, status) in enumerate(TASKS, 1):
        done = raised + timedelta(days=rng.randint(5, 20)) if status != "open" else None
        if done and done > AS_OF:
            done = AS_OF
        tasks.append(dict(task_code=f"TSK-{i:05d}", task_name=name, priority=pri, org_unit_key=org,
                          contributes_to_type=ctype, contributes_to_key=ckey, contributes_to_note=None,
                          raised_by=_email(who), date_raised=raised, assigned_to=_email(who), status=status,
                          completed_by=_email(who) if status == "complete" else None, completed_date=done,
                          notes=None))
    problems = []
    for i, (title, stmt, org, who, raised, owner, imp, urg, ctype, ckey, status) in enumerate(PROBLEMS, 1):
        closed = raised + timedelta(days=rng.randint(3, 10)) if status == "closed" else None
        problems.append(dict(problem_code=f"PRB-{i:05d}", problem_title=title, problem_statement=stmt,
                             org_unit_key=org, raised_by=_email(who), raised_on=raised, problem_owner=_email(owner),
                             impact=imp, urgency=urg, target_resolution_date=raised + timedelta(days=28),
                             status=status, closed_date=closed,
                             resolution="Fixed at source and a check added to the monthly routine." if closed else None,
                             contributes_to_type=ctype, contributes_to_key=ckey, notes=None))
    return dict(weekly_updates=updates, wellbeing_checkins=wellbeing, tasks=tasks, problems=problems)
