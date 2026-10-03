# Measures: entering and approving values

Open **Measures** in the top menu. It has three tabs:
- **To update:** your values, most urgent first. Returned values come first, then values that are expected but haven't arrived, then drafts, then values still waiting for data.
- **To review:** for approvers. Values awaiting your review, values you've returned, and values that are overdue.
- **All measures:** every active measure with its latest approved value and RAG, plus a search box.

Nothing needs setting up for each period. The day after a period ends, Open PMS creates an empty ("not started") value for every active measure with that frequency.

## Entering a value (updaters)

1. Open the value from **To update**.
2. Enter the value:
   - **Percentages** go in as 0 to 100, so 58 means 58%.
   - **Yes/no measures** have two buttons instead of a box.
   - **No value this period?** Tick **No value available for this period** and explain why in the narrative.
3. Write the **narrative**: what's behind the figure, and what's being done about it. It's required if there's no value, or if the value is off track (amber or red).
4. Choose the **data quality**: verified, provisional, estimated or unverified.
5. Choose **Save draft** to come back later, or **Submit for review** when it's ready. Once submitted, the value is locked and the approvers get an email.

If the approver returns it, you'll get an email with their comment. Open the value, make your changes and submit again. This creates a new version, so the approver can see exactly what changed.

## Reviewing a value (approvers)

Open the value from **To review**. Then:
- **Read it:** check the value, narrative and data quality against the target and recent values.
- **Approve it,** or
- **Return it for changes,** with a comment explaining what to change. The comment is required, and the updaters are emailed.

Comments are kept separate from the narrative. They're never included in reports or exports.

You can't approve a value you entered yourself. Another approver has to review it.

## When an approved value is wrong (admins)

Open the value and use **Reopen for correction**, giving a reason. The updaters are emailed, and the corrected value goes through review again. Until it's approved, reports keep showing the approved value.

## RAG

RAG is worked out when a value is approved, using the measure's direction ("higher is better" or "lower is better") and the period's target and tolerance. It's always shown in words, not just colour:
- **Green:** on or better than target
- **Amber:** short of target but within tolerance (KPIs and OKRs only)
- **Red:** off track
- **No target set,** **No data,** or **RAG not used for this measure** (for text measures, and for measures with no better direction)

## Targets (admins)

Go to **Measures**, then **Targets**. Choose a measure, a type (target, tolerance, baseline or capacity) and a date range. You'll see every period in the range; enter one value to apply to all of them. To stop using a value without losing its history, choose **Stop using in these periods**.

## Reminders

Every Monday, each updater gets one email listing their values that are late or due within the next few days. The number of days is set by `reminder_days_before_expected` in **Admin > Settings**. Measures with no expected lag are never chased.
