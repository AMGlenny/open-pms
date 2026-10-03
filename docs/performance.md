# Performance at scale

Open PMS is tested with more data than most organisations will ever have. `tests/test_scale.py` builds:
- 360 measures (monthly, quarterly and annual), each with an owner, an updater and an approver;
- 120 people in 15 teams;
- two and a half years of approved values: 8,320 values, each with a target;
- 32,320 audit rows;
- six months of weekly updates from 110 people, 3,000 tasks and 400 problems.

It then times every key page and export. CI runs it on every change, on SQLite and on PostgreSQL, and fails if any page takes more than 2 seconds or any export more than 30 seconds.

## Results

Measured on a small 4-core cloud machine. Times are in seconds, for one request after the page has been used once.

| What | SQLite | PostgreSQL 16 |
|---|---|---|
| Home | 0.00 | 0.02 |
| Measures: to update | 0.03 | 0.05 |
| Measures: to review | 0.03 | 0.05 |
| Measures: all 360 with latest values | 0.04 | 0.07 |
| One value with its history | 0.01 | 0.03 |
| Save a value | 0.01 | 0.01 |
| Admin: measures list and search | 0.00 | 0.03 |
| Admin: audit log | 0.01 | 0.02 |
| My week | 0.01 | 0.03 |
| My team | 0.01 | 0.03 |
| Daily jobs (expected values for a day) | 0.01 | 0.02 |
| Export: measure values | 0.32 | 0.43 |
| Export: quarterly report pack | 0.39 | 0.43 |
| Export: full data model, CSV | 1.33 | 1.40 |
| Export: full data model, Excel | 8.19 | 8.90 |

(The full data model rows add together building the data and writing the files.)

**30 people saving at the same moment**, each on their own connection, all succeed with nothing lost, on both databases.

## What this means

- **SQLite is enough** for an organisation with hundreds of measures and a hundred or more people. Everyday pages respond in a few hundredths of a second.
- **The full data model as Excel** is the slowest thing, at about 8 seconds for all of the data above. It's meant for scheduled exports, which run in the background. For live dashboards, use a data link, which serves CSV in under a second.
- **PostgreSQL** is slightly slower per request here (the database is a separate process) but handles many simultaneous writers and very large installations better.

To run the scale tests yourself:

```bash
OPENPMS_SCALE_TESTS=1 python -m unittest tests.test_scale -v
```
