"""Generates rows for the periods table.

Every organisation sets its own year boundaries in settings:
- financial year start month (default April, UK). January makes the
  financial year the same as the calendar year.
- academic year start month (default September).
- term dates, entered by admins (they live only in the periods table).

Weeks run Monday to Sunday and are keyed by their Monday. Fortnights run
continuously from an anchor Monday, so they never overlap across years.
"""
from datetime import date, timedelta

DEFAULT_FY_START_MONTH = 4
DEFAULT_AY_START_MONTH = 9


def _add_months(year, month, n):
    m = month - 1 + n
    return year + m // 12, m % 12 + 1


def year_label(start_year, start_month):
    """'2026-27' for years that cross January, '2026' for calendar years."""
    if start_month == 1:
        return str(start_year)
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def fy_start_year(d, fy_start_month=DEFAULT_FY_START_MONTH):
    return d.year if d.month >= fy_start_month else d.year - 1


def fy_label(start_year, fy_start_month=DEFAULT_FY_START_MONTH):
    return year_label(start_year, fy_start_month)


def financial_year(d, fy_start_month=DEFAULT_FY_START_MONTH):
    return fy_label(fy_start_year(d, fy_start_month), fy_start_month)


def financial_quarter_no(d, fy_start_month=DEFAULT_FY_START_MONTH):
    return ((d.month - fy_start_month) % 12) // 3 + 1


def academic_year(d, ay_start_month=DEFAULT_AY_START_MONTH):
    start = d.year if d.month >= ay_start_month else d.year - 1
    return year_label(start, ay_start_month)


def _month_end(year, month):
    ny, nm = _add_months(year, month, 1)
    return date(ny, nm, 1) - timedelta(days=1)


def first_monday_on_or_after(d):
    return d + timedelta(days=(7 - d.weekday()) % 7)


def generate(first_fy, last_fy, daily_from_fy=None, *, fy_start_month=DEFAULT_FY_START_MONTH,
             ay_start_month=DEFAULT_AY_START_MONTH, terms=(), fortnight_anchor=None):
    """Periods for financial years first_fy..last_fy (start years, inclusive).

    terms: [(academic_year_label, code, label, start, end), ...]
    Daily periods are only made from daily_from_fy onwards (defaults to
    first_fy) because they are the bulk of the rows.
    """
    def row(key, ptype, label, start, end):
        short = ptype in ("daily", "weekly", "fortnightly", "monthly", "quarterly")
        fy = financial_year(start, fy_start_month)
        return {
            "period_key": key, "period_type": ptype, "period_label": label,
            "start_date": start, "end_date": end, "financial_year": fy,
            "financial_quarter": f"{fy} Q{financial_quarter_no(start, fy_start_month)}" if short else None,
            "academic_year": academic_year(start, ay_start_month), "calendar_year": start.year,
        }

    rows = []
    range_start = date(first_fy, fy_start_month, 1)
    ey, em = _add_months(last_fy, fy_start_month, 12)
    range_end = date(ey, em, 1) - timedelta(days=1)

    d = date(daily_from_fy or first_fy, fy_start_month, 1)
    while d <= range_end:
        rows.append(row(f"D-{d.isoformat()}", "daily", d.strftime("%d %b %Y"), d, d))
        d += timedelta(days=1)

    d = first_monday_on_or_after(range_start)
    while d <= range_end:
        rows.append(row(f"W-{d.isoformat()}", "weekly", f"w/c {d.strftime('%d %b %Y')}", d, d + timedelta(days=6)))
        d += timedelta(days=7)

    # Fortnights stay on the anchor's two-week rhythm, starting with the first
    # one that begins inside the range.
    d = fortnight_anchor or first_monday_on_or_after(range_start)
    while d < range_start:
        d += timedelta(days=14)
    while d - timedelta(days=14) >= range_start:
        d -= timedelta(days=14)
    while d <= range_end:
        rows.append(row(f"F-{d.isoformat()}", "fortnightly", f"Fortnight w/c {d.strftime('%d %b %Y')}", d,
                        d + timedelta(days=13)))
        d += timedelta(days=14)

    for fy in range(first_fy, last_fy + 1):
        label = fy_label(fy, fy_start_month)
        for i in range(12):
            y, m = _add_months(fy, fy_start_month, i)
            start = date(y, m, 1)
            rows.append(row(f"M-{y}-{m:02d}", "monthly", start.strftime("%b %Y"), start, _month_end(y, m)))
        for q in range(4):
            y, m = _add_months(fy, fy_start_month, q * 3)
            qy, qm = _add_months(y, m, 2)
            rows.append(row(f"Q-{label}-Q{q + 1}", "quarterly", f"Q{q + 1} {label}", date(y, m, 1), _month_end(qy, qm)))
        ny, nm = _add_months(fy, fy_start_month, 12)
        rows.append(row(f"FY-{label}", "annual", f"FY {label}", date(fy, fy_start_month, 1),
                        date(ny, nm, 1) - timedelta(days=1)))

    # Calendar and academic years from the year before the range, so the most
    # recent full year is available for lagged annual data.
    for year in range(first_fy - 1, last_fy + 1):
        rows.append(row(f"CY-{year}", "calendar_year", str(year), date(year, 1, 1), date(year, 12, 31)))
        ay = year_label(year, ay_start_month)
        ny, nm = _add_months(year, ay_start_month, 12)
        rows.append(row(f"AY-{ay}", "academic_year", f"AY {ay}", date(year, ay_start_month, 1),
                        date(ny, nm, 1) - timedelta(days=1)))

    first_ay = year_label(first_fy, ay_start_month)
    last_ay = year_label(last_fy, ay_start_month)
    for ay, code, label, start, end in terms:
        if first_ay <= ay <= last_ay:
            rows.append(row(f"T-{ay}-{code}", "term", label, start, end))

    return sorted(rows, key=lambda r: (r["start_date"], r["period_type"]))
