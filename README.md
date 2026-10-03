# Open PMS

Free, open-source performance management for public bodies, charities and teams of any size.

- **Measures** with targets, RAG and a proper approval trail: updaters enter values, approvers approve or return them with a comment, and every change is recorded.
- **Weekly updates:** a quick daily or weekly log of tasks, problems, successes and workload. Quarterly reports can then be drafted from what was logged, instead of a scramble every quarter.
- **Tidy exports** that work straight away in Excel, LibreOffice, Power BI, Metabase or any AI tool, with a data dictionary, a README for AI, scheduled snapshots and live data links.

It runs anywhere: one small Docker container, or plain Python, with SQLite or PostgreSQL. People sign in with a password, or with their Google or Microsoft account. There's no licence fee and no cloud account to sign up for. Your data stays on your own server.

> **Status: ready to try.** All five phases are done: the foundation, weekly updates, the measures workflow, exports and hardening. It hasn't had an independent security or accessibility review yet, so try it with test data first.

## Principles

- **Submit once, use many times.** Every value is entered in one place and reused everywhere.
- **Keep it simple.** Only essential features are built.
- **Data first.** The data model is clean, consistent and exportable. Every table and column name is the same in the database, on screen and in every export.
- **Nothing is deleted.** Things are retired or made inactive, and every change records who, when, the old value and the new value.

## Try it in two minutes (demo data)

You need Python 3.10 or later.

```bash
git clone https://github.com/AMGlenny/open-pms.git
cd open-pms
python -m venv .venv && . .venv/bin/activate
pip install -e .
openpms load-demo --password "try open pms today"
openpms run
```

Open http://127.0.0.1:5000 and sign in as `sam.patel@example.org` (an admin) with that password. Everyone in the demo is fictional.

## Install it for real

The quickest route is Docker:

```bash
docker compose up -d
docker compose logs openpms | grep "setup code"
```

Then open http://localhost:8000/setup. Enter the setup code from the log, name your organisation, choose when your financial year starts, and create your admin account. After that, add teams, people and measures under **Admin**.

[docs/install.md](docs/install.md) covers HTTPS, single sign-on, PostgreSQL, backups, upgrades, hosting several organisations and running without Docker. [docs/admin_guide.md](docs/admin_guide.md) covers first steps as an admin.

## How it's built

| Part | What it is |
|---|---|
| `openpms/schema.py` | The data model: every table, column and allowed value, defined once. Tables, admin forms, checks and exports are all built from it. |
| `openpms/db.py` | The only way data is read or written, on SQLite or PostgreSQL. It scopes everything to one organisation, audits every change, and has no delete. |
| `openpms/rules.py`, `openpms/workflow.py` | The business rules: RAG, validation, the approval workflow, weekly carry-over and wellbeing privacy |
| `openpms/periods.py` | Days, weeks, fortnights, months, quarters, financial years (any start month), calendar years, academic years and terms |
| `openpms/admin.py`, `openpms/templates/` | Plain, accessible web pages. There's no JavaScript framework. |
| `openpms/weekly.py` | My week, tasks, problems and My team |
| `openpms/measures.py`, `openpms/measures_service.py` | Measures pages, and the bridge that runs the tested workflow rules against the database in one transaction |
| `openpms/mail.py` | Optional email notifications |
| `openpms/sso.py` | Optional Google and Microsoft sign-in |
| `openpms/exports.py`, `openpms/exports_web.py` | Export datasets, CSV and Excel writers, the README for AI and quarterly prompt, scheduled snapshots and data links |
| `tests/` | 147 tests: data rules, security, admin, periods, workflow, weekly pages, wellbeing privacy, the measures journey end to end, exports, single sign-on, keeping organisations apart, backups and accessibility. All run on SQLite and PostgreSQL. Scale tests (360 measures, 120 people) run in CI: see [performance.md](docs/performance.md). |

The stack is Python, Flask, and SQLite or PostgreSQL. It's deliberately small, so it's easy to look after.

## Roadmap

| Phase | What | Status |
|---|---|---|
| 1. Foundation | Data model, sign-in with invites, roles, audit trail, admin screens, first-run setup, Docker | **Done** |
| 2. Weekly updates | Successes, communication, workload, tasks and problems that carry over each week, the team view, and private wellbeing (only line managers see individual answers) | **Done**: [guide](docs/weekly_guide.md) |
| 3. Measures | Entering values, review, return with comments, versions, reopening, RAG, reminders, setting targets across a range, email notifications | **Done**: [guide](docs/measures_guide.md) |
| 4. Exports | CSV and Excel with a data dictionary, a README for AI tools, scheduled snapshots, the quarterly report pack and prompt, and a read-only data link for BI tools | **Done**: [guide](docs/exports_guide.md) |
| 5. Hardening | Google and Microsoft sign-in, PostgreSQL, tests at volume, a backup tool, an accessibility checklist, and hosting several organisations on one installation | **Done**: [install](docs/install.md), [performance](docs/performance.md), [accessibility](docs/accessibility.md) |

## Accessibility

Open PMS aims to meet WCAG 2.2 AA. The tests check every page for:
- language, page titles and headings
- labels on every field, with hints and errors linked to it
- unique IDs and table headers
- colour contrast and visible focus

Keyboard, screen reader, zoom and phone checks still need doing by hand before each release: [docs/accessibility.md](docs/accessibility.md) has the checklist.

## Licence

MIT: free to use, change and share, including commercially. See [LICENSE](LICENSE).

Security problems: see [SECURITY.md](SECURITY.md).
