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

## HTTPS (needed before real use)

Passwords and session cookies must only travel over HTTPS. The simplest way is a reverse proxy that gets certificates automatically. For example, with [Caddy](https://caddyserver.com), the whole `Caddyfile` is:

```
pms.example.org {
    reverse_proxy 127.0.0.1:8000
}
```

Once HTTPS works, set `OPENPMS_SECURE_COOKIES=1` (in `docker-compose.yml` or your environment) and restart. Browsers will then only send the sign-in cookie over HTTPS.

## Settings (environment variables)

| Variable | Default | What it does |
|---|---|---|
| `OPENPMS_INSTANCE` | `/data` in Docker | Folder for the database, secret key and setup code |
| `OPENPMS_DATABASE` | `<instance>/openpms.db` | Database file |
| `OPENPMS_SECRET_KEY` | generated and saved in the instance folder | Signs sessions. Set it yourself if you run several servers. |
| `OPENPMS_SECURE_COOKIES` | `0` | Set to `1` once served over HTTPS |
| `OPENPMS_SETUP_CODE` | random, printed in the log | Choose your own first-run setup code |
| `OPENPMS_SMTP_HOST` | not set | Mail server for notifications. Without it, emails are only logged and everything else works. |
| `OPENPMS_SMTP_PORT`, `OPENPMS_SMTP_USER`, `OPENPMS_SMTP_PASSWORD` | 587, none, none | Mail server sign-in |
| `OPENPMS_SMTP_FROM` | `openpms@localhost` | The From address on emails |
| `OPENPMS_SMTP_STARTTLS` | `1` | Set to `0` only for a mail server that doesn't support encryption |

Everything else, such as your organisation name, financial year start and wellbeing group size, is set in the app under **Admin > Settings**.

## Daily jobs

Each morning, Open PMS creates an empty value for every measure whose period has just ended, and on Mondays it emails reminders. It does this by itself the first time anyone uses it each day, so you don't need cron.

If you'd rather run it on a schedule, use `openpms run-jobs` (it only runs once a day, however often it's called).

## Backups

Everything is in one SQLite database. To take a consistent copy while the app is running:

```bash
sqlite3 /var/lib/openpms/openpms.db ".backup '/backups/openpms-$(date +%F).db'"
```

With Docker, run the same command against the volume, or stop the container and copy the volume.

- **Schedule it daily** and keep copies somewhere else, such as another machine or cloud storage.
- **Test a restore now and then:** copy a backup to a test machine and start Open PMS against it.

## Upgrading

1. **Back up first.**
2. **Get the new version:** `git pull`, then `docker compose up -d --build`, or `pip install -e .` and restart.
3. **Database changes happen by themselves.** Open PMS creates any new tables or columns when it starts.

## Command line

```bash
openpms init-db --org-name "My Organisation"     # create the database without the web setup
openpms create-admin --email you@example.org --name "Your Name"   # prints a link to set a password
openpms generate-periods --fy 2027              # add a financial year of periods
openpms load-demo --password "..."              # fictional demo data, fresh databases only
```

In Docker, prefix these with `docker compose exec openpms`.
