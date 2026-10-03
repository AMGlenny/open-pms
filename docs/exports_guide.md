# Exports: getting your data out

Open PMS is built so your data is easy to use somewhere else: in a spreadsheet, a BI tool or an AI tool. There are three ways to get it out:

1. **Download:** anyone who can sign in can download an export from the **Exports** page.
2. **Scheduled exports (admins):** files written to a folder on the server every day, week, month or quarter.
3. **Data links (admins):** a private web address that BI tools and spreadsheets read directly, and refresh by themselves.

## What you can export

| Export | What's in it |
|---|---|
| **Measure values** | One row per approved measure per period, with the measure, owner, period, targets and RAG filled in. You can choose one financial year. Works on its own, with no joins. |
| **Full data model** | Every table: measures, periods, roles, people, teams, themes, targets, submissions, approved values, weekly updates, tasks and problems. Use it to build a BI model. |
| **Weekly work** | Weekly updates (successes, communication and workload), tasks and problems, with names filled in. |
| **Quarterly report pack** | Everything needed to write the quarterly report for one quarter, plus a prompt for drafting it with AI and a checklist for writing it without. |

**Never exported:** individual wellbeing answers, reviewer comments, the audit log, drafts and values that haven't been approved, and who manages whom.

## Formats

- **Excel workbook:** one sheet per table, then a `data_dictionary` sheet and a `readme` sheet. Dates are real dates, numbers are real numbers, the header row is frozen and every sheet has filters.
- **CSV files (zip):** one CSV per table, `data_dictionary.csv`, `README_for_AI.md` and `export_info.txt`, in one folder.
- **CSV and Excel (zip):** both.

Every file follows the same rules, so it works in Excel, LibreOffice, Google Sheets, Power BI, Metabase, R, Python or any AI tool without tidying:
- one row per record, one header row, no merged cells, no totals;
- the same snake_case column names as on screen and in the database;
- dates as `2026-09-30` and times in UTC as `2026-09-30T06:00:00Z`;
- percentages as 0 to 100, so 58 means 58%;
- blank means no value, never zero.

CSV files are UTF-8 with a byte order mark, so Excel shows £ signs and accents correctly. Text that starts with `=`, `+`, `-` or `@` gets an apostrophe at the front in CSV files, so a spreadsheet can never run it as a formula. In Excel files it's simply stored as text.

## Using exports with AI

Every export includes `README_for_AI.md`. It explains the columns, the units, how RAG works, how the tables join and how your financial year runs. Tell the AI tool to read it first.

The **quarterly report pack** also includes `prompt_quarterly_report.md`:
1. Download the pack for the quarter (it defaults to the last completed one).
2. Open your organisation's AI tool. Any will do: Microsoft Copilot, ChatGPT, Gemini, Claude or a model you run yourselves.
3. Attach the files (or the Excel file) and paste the prompt.
4. Check the draft. The prompt tells the AI to quote measure codes, so every statement can be checked, and to never invent numbers.

Nothing depends on one AI product, so if a tool changes or goes away, use another. The prompt file also has a **Without AI** checklist that walks through the Excel file section by section, so the report can always be written by hand.

Only share exports with AI tools your organisation has approved for this kind of data.

## Scheduled exports (admins)

Go to **Exports > Scheduled exports** to see each job, when it last ran and whether it worked. **Run now** runs a job straight away.

To add or change a job, go to **Admin > Scheduled exports**:
- **Dataset** and **format:** as above.
- **Frequency** and **run day:** daily; weekly (run day 1 is Monday, 7 is Sunday); monthly (day of the month); or quarterly (day of the month in the first month of each financial quarter). A day past the end of a short month runs on the last day.
- **Folder:** a name such as `full_model`. Letters, numbers, `-` and `_` only.
- **Keep history:** keep a dated copy of each run as well as `latest`.

Jobs run by themselves once a day, in the background, the first time anyone uses Open PMS that day. If nobody uses it on a job's run day, the job runs the next time someone does. You can also run them on a schedule with `openpms run-jobs`.

Quarterly report packs from a schedule are always for the last completed quarter.

### Where the files go

Files are written to the snapshot folder on the server (`snapshots` inside the data folder, or wherever `OPENPMS_SNAPSHOT_DIR` points):

```
snapshots/
  full_model/
    latest/            replaced in one step on every run
    2026-10-03/        a dated copy, if the job keeps history
  quarter_pack/
    latest/
```

`latest` is swapped in one step, so anything reading or syncing it never sees half an export.

To use the files in other tools, sync the folder to wherever your team works, for example with [rclone](https://rclone.org) to OneDrive, SharePoint, Google Drive, Dropbox or S3, or point a shared drive at it. Power BI, Excel and AI tools can then read the `latest` folder.

## Data links for BI tools (admins)

A data link is a private web address that serves live CSV files, with no sign-in. Go to **Exports > Data links**, give the link a name (what it's for) and choose what it shares: measure values, the full data model or weekly work.

The link is shown **once**. Copy it straight away. Open PMS only keeps a scrambled (hashed) copy, so it can't show it again. If you lose it, turn it off and make a new one.

Add a file name to the end of the link:
- `values_flat.csv` (and the other tables in the dataset);
- `data_dictionary.csv`;
- `README_for_AI.md`.

How to connect:
- **Power BI:** Get data > Web, paste the address of a CSV file, then set a scheduled refresh in the Power BI service.
- **Excel:** Data > From Web, paste the address of a CSV file. Refresh All updates it.
- **Google Sheets:** `=IMPORTDATA("address of a CSV file")`.
- **Looker Studio, Metabase, Tableau and others:** use their CSV or web connector.

Every request reads the live data, so values appear as soon as they're approved.

**Treat a data link like a password.** Anyone who has it can read that data. Use it only where the tool needs it, turn it off when it's no longer needed, and check **Last used** now and then. Making and turning off links is recorded in the audit log. Data links need HTTPS (see [install.md](install.md)), so the data isn't sent in the clear.

## The log

Every download and every scheduled run is logged: who, when, what and how many rows. The **Exports** page shows your recent downloads. Admins see everyone's, including scheduled runs.
