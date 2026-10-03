# Admin guide: first steps

Everything here is under **Admin** in the top menu. Every change you make is recorded: open any item and choose **History** to see who changed what, and when. Nothing can be deleted. Instead, make things inactive or retire them, so their history stays linked.

## 1. Check your settings

Go to **Admin > Settings**.

- **organisation_name:** shown in the header and on exports.
- **fy_start_month:** the month your financial year starts (4 is April). This sets quarters and financial years everywhere.
- **ay_start_month:** the month your academic year starts, if you use academic-year or term measures.
- **wellbeing_min_group_size:** team wellbeing totals are hidden until at least this many people answer. It can't be lower than 3, so individuals can't be identified.

## 2. Periods

Setup creates periods for this financial year and next. **Admin > Periods** shows them all.

- **Each year:** in the spring, use **Add a financial year's periods** to add the year after next.
- **Term dates:** if you use term-time measures, add one period per term. Use type `term` and a key like `T-2026-27-AUT`, with the real start and end dates. Edit them when your local calendar changes.

## 3. Teams

Go to **Admin > Teams**. Add your structure from the top down:
- workstreams first, with no parent
- then teams, with a workstream as the parent
- then sub-teams, if you need them

People pick their team from this list, and every task, problem and update is filed under a team.

## 4. People

1. **Add them.** Go to **Admin > People**, then **Add**. Enter their work email (it's also their sign-in), their name, their team and their line manager.
   - The line manager matters: only they will ever see this person's individual wellbeing answers.
2. **Choose a role:**
   - **admin** can use these screens
   - **standard** can do everything else
   - **viewer** can look but not change anything
3. **Invite them.** Open the person and choose **Create an invite link**. Send them the link. It works once, for 7 days, and lets them set their own password.
4. **Forgotten passwords:** open the person and create a reset link the same way.
5. **Leavers:** untick **active**. They can no longer sign in, and their history stays.

## 5. Themes, programmes and objectives

Go to **Admin > Themes, programmes and objectives**. Add whatever your measures and work contribute to. These feed the "contributes to" choices and help group the quarterly report.

## 6. Measures

1. **Add the measure.** Go to **Admin > Measures**, then **Add**. The code (for example PM-0023) is made for you.
   - **source_ref** is the reference in your source document, for example 1.01. It can repeat, which is fine.
   - **parent_measure_code** links a child measure to its summary measure.
   - **measure_class**: choose kpi or okr for formal KPIs and OKRs. Only those can have a tolerance.
   - **unit**: percent is entered as 58 for 58%.
   - **expected_lag_days**: how long after the period ends the data is usually available. Leave it blank if there's no firm expectation; the measure then won't be chased.
2. **Give it people.** In **Admin > Measure roles**, add one **owner**, at least one **updater** and at least one **approver**. The approver should be someone other than the owner.
3. **Optional extras.** Add links in **Measure links**, and targets in **Targets and reference values**.

To stop using a measure, set its status to **retired**. It disappears from day-to-day lists, and its history stays in reports.

## 7. Audit log

**Admin > Audit log** shows every change across the system. Individual wellbeing answers are never shown in it: wellbeing changes appear as "(hidden)".

## 8. Exports

Everyone can download exports from **Exports**. As an admin you can also:
- set up **scheduled exports**, which write fresh files to a folder on the server every day, week, month or quarter. Three example jobs come with the demo data;
- make **data links**, so Power BI, Excel or Google Sheets can read live data and refresh by themselves.

See the [exports guide](exports_guide.md).
