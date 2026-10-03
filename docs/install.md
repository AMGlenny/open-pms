# Installing Open PMS

Open PMS is one small web app with one database file. It runs on almost anything:
- a spare office PC or server
- a Raspberry Pi
- a small cloud server. Several providers offer one free, for example Oracle Cloud's Always Free tier.

## Option 1: Docker (recommended)

1. **Install** Docker and Docker Compose.
2. **Start it.** Download Open PMS and run:
   ```bash
   docker compose up -d
   ```
3. **Get the setup code.** Fresh installations ask for a one-time code, so nobody else can claim yours first:
   ```bash
   docker compose logs openpms | grep "setup code"
   ```
4. **Set up.** Open `http://<your server>:8000/setup`, enter the code, and set up your organisation and admin account.

All data lives in the `openpms-data` volume: the database, the secret key used to sign sessions, and the setup code. Back it up (see below).

## Option 2: plain Python

You need Python 3.10 or later.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[server]"
export OPENPMS_INSTANCE=/var/lib/openpms          # where data is kept
gunicorn --bind 127.0.0.1:8000 --workers 2 "openpms:create_app()"
```

The setup code is printed in gunicorn's log. To keep it running, use systemd or any process manager.

## Option 3: PostgreSQL

SQLite is the default and is plenty for most organisations: the scale tests (see [performance.md](performance.md)) run 360 measures and 120 people with every page under a tenth of a second. Use PostgreSQL if you already run it, want your database host to handle backups, or host many organisations on one installation.

With Docker:

```bash
export POSTGRES_PASSWORD="a-long-random-password"     # letters, numbers and hyphens only
docker compose -f docker-compose.postgres.yml up -d
docker compose -f docker-compose.postgres.yml logs openpms | grep "setup code"
```

Then open `http://<your server>:8001/setup`.

Without Docker, install the PostgreSQL extra and point Open PMS at your database:

```bash
pip install -e ".[server,postgres]"
export OPENPMS_DATABASE="postgresql://openpms:password@db.example.org:5432/openpms"
```

The database user needs to be able to create tables in that database. Open PMS creates them when it starts.

## HTTPS (needed before real use)

Passwords and session cookies must only travel over HTTPS. The simplest way is a reverse proxy that gets certificates automatically. For example, with [Caddy](https://caddyserver.com), the whole `Caddyfile` is:

```
pms.example.org {
    reverse_proxy 127.0.0.1:8000
}
```

Once HTTPS works, set `OPENPMS_SECURE_COOKIES=1` and `OPENPMS_BEHIND_PROXY=1` (in `docker-compose.yml` or your environment) and restart. Browsers will then only send the sign-in cookie over HTTPS, and links Open PMS makes (such as data links) will use your public `https://` address.

## Settings (environment variables)

| Variable | Default | What it does |
|---|---|---|
| `OPENPMS_INSTANCE` | `/data` in Docker | Folder for the database, secret key and setup code |
| `OPENPMS_DATABASE` | `<instance>/openpms.db` | SQLite database file, or a `postgresql://` address |
| `OPENPMS_SECRET_KEY` | generated and saved in the instance folder | Signs sessions. Set it yourself if you run several servers. |
| `OPENPMS_SECURE_COOKIES` | `0` | Set to `1` once served over HTTPS |
| `OPENPMS_SETUP_CODE` | random, printed in the log | Choose your own first-run setup code |
| `OPENPMS_BEHIND_PROXY` | `0` | Set to `1` when a reverse proxy (Caddy, nginx) sits in front. Only do this if Open PMS can't be reached except through the proxy. |
| `OPENPMS_SNAPSHOT_DIR` | `<instance>/snapshots` | Where scheduled exports are written |
| `OPENPMS_PASSWORD_SIGN_IN` | `1` | Set to `0` to allow single sign-on only |
| `OPENPMS_GOOGLE_CLIENT_ID`, `OPENPMS_GOOGLE_CLIENT_SECRET` | not set | Turn on Sign in with Google (see below) |
| `OPENPMS_GOOGLE_DOMAIN` | not set | Only accept Google accounts from this Workspace domain |
| `OPENPMS_MICROSOFT_CLIENT_ID`, `OPENPMS_MICROSOFT_CLIENT_SECRET`, `OPENPMS_MICROSOFT_TENANT_ID` | not set | Turn on Sign in with Microsoft (see below) |
| `OPENPMS_SMTP_HOST` | not set | Mail server for notifications. Without it, emails are only logged and everything else works. |
| `OPENPMS_SMTP_PORT`, `OPENPMS_SMTP_USER`, `OPENPMS_SMTP_PASSWORD` | 587, none, none | Mail server sign-in |
| `OPENPMS_SMTP_FROM` | `openpms@localhost` | The From address on emails |
| `OPENPMS_SMTP_STARTTLS` | `1` | Set to `0` only for a mail server that doesn't support encryption |

Everything else, such as your organisation name, financial year start and wellbeing group size, is set in the app under **Admin > Settings**.

## Single sign-on (Google and Microsoft)

People can sign in with their Google or Microsoft work account instead of a password. Single sign-on only signs in people who are already in Open PMS and active: the email address the provider confirms must match their email in **Admin > People**. It never creates people. Invite links and passwords keep working unless you set `OPENPMS_PASSWORD_SIGN_IN=0`.

You need HTTPS and `OPENPMS_BEHIND_PROXY=1` first, so the return address is your public `https://` one.

### Google

1. In the [Google Cloud console](https://console.cloud.google.com/apis/credentials), create an **OAuth client ID** of type **Web application**.
2. Add the authorised redirect URI `https://pms.example.org/login/sso/google/callback` (with your own address).
3. Set `OPENPMS_GOOGLE_CLIENT_ID` and `OPENPMS_GOOGLE_CLIENT_SECRET`. To accept only your Google Workspace accounts, also set `OPENPMS_GOOGLE_DOMAIN`, for example `example.org`.

Open PMS only accepts email addresses Google has verified.

### Microsoft (Entra ID, formerly Azure AD)

1. In the [Entra admin centre](https://entra.microsoft.com), go to **App registrations > New registration**. Choose **Accounts in this organizational directory only**.
2. Add a **Web** redirect URI: `https://pms.example.org/login/sso/microsoft/callback`.
3. Under **Certificates & secrets**, make a client secret. Note when it expires, and renew it before then.
4. Set `OPENPMS_MICROSOFT_CLIENT_ID` (the application ID), `OPENPMS_MICROSOFT_CLIENT_SECRET` and `OPENPMS_MICROSOFT_TENANT_ID` (the directory ID).

The tenant ID must be your own directory's ID. Open PMS refuses to start with `common` or `organizations`, so accounts from other organisations can never sign in. People are matched on their email, or their sign-in name if no email is set, so make sure these match the emails in Open PMS.

## Several organisations on one installation

One installation can host several organisations, for example a shared service hosting its partners. Each organisation's data, settings, people, exports and data links are kept completely apart.

```bash
openpms create-org --name "Riverside Trust" --code riverside \
  --admin-email ada@riverside.example --admin-name "Ada Admin" \
  --fy-start-month 4 --base-url https://pms.example.org
openpms list-orgs
```

`create-org` prints a link for the new admin to set their password, and the organisation's sign-in link, `https://pms.example.org/login?org=riverside`. Once there's more than one organisation, the sign-in page asks for the organisation code, and command-line tools need `--org <code>`. Daily jobs run for every organisation, and scheduled exports go into a folder per organisation.

## Daily jobs

Each day, Open PMS:
- creates an empty value for every measure whose period has just ended;
- on Mondays, emails reminders;
- runs any scheduled exports that are due (see the [exports guide](exports_guide.md)), in the background.

It does this by itself the first time anyone uses it each day, so you don't need cron.

If you'd rather run it on a schedule, use `openpms run-jobs` (it only runs once a day, however often it's called).

## Backups

Back up every day, keep copies somewhere else (another machine or cloud storage), and test a restore now and then.

### SQLite (the default)

```bash
openpms backup --keep 14
```

This takes a consistent copy while Open PMS is running, checks it, and keeps the latest 14 (in `backups` inside the data folder, or wherever `--to` says). With Docker:

```bash
docker compose exec openpms openpms backup --keep 14
```

A daily cron entry does it for you, for example `15 2 * * * cd /srv/open-pms && docker compose exec -T openpms openpms backup --keep 14`. Then copy the `backups` folder off the server, for example with rclone.

To check a backup: `openpms check-backup <file>`. It confirms the file is a complete, readable database and shows how many measures, values and people it holds.

To restore, **stop Open PMS first**, then:

```bash
openpms restore <file> --yes
```

The database as it was is kept alongside (`openpms.db.before-restore-...`), in case you need it.

### PostgreSQL

If your database host takes backups, use those. Otherwise `openpms backup` runs `pg_dump` (it needs the PostgreSQL client tools installed) and checks the result. With the PostgreSQL Docker setup, back up from the database container:

```bash
docker compose -f docker-compose.postgres.yml exec -T db pg_dump -U openpms --format=custom openpms > openpms-$(date +%F).dump
```

To restore, stop Open PMS and use `pg_restore --clean --if-exists -d <database> <file>`.

### Not needed

The `snapshots` folder doesn't need backing up: scheduled exports rebuild it.

## Upgrading

1. **Back up first.**
2. **Get the new version:** `git pull`, then `docker compose up -d --build`, or `pip install -e .` and restart.
3. **Database changes happen by themselves.** Open PMS adds any new tables and columns when it starts.

## Command line

```bash
openpms init-db --org-name "My Organisation"     # create the database without the web setup
openpms create-admin --email you@example.org --name "Your Name"   # prints a link to set a password
openpms generate-periods --fy 2027              # add a financial year of periods
openpms load-demo --password "..."              # fictional demo data, fresh databases only
openpms run-jobs                                # daily jobs, for every organisation
openpms backup --keep 14                        # checked backup; also check-backup and restore
openpms create-org ... / openpms list-orgs      # several organisations on one installation
```

In Docker, prefix these with `docker compose exec openpms`.
