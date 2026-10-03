"""Database layer: SQLite tables generated from schema.py, and the only way
the app reads or writes data.

Rules enforced here, for every table:
- every row belongs to an organisation (org_id), and every query is scoped
  to one organisation;
- choice columns only accept their listed values and required columns can't
  be empty (CHECK and NOT NULL constraints in the database itself);
- every insert and every changed field is written to audit_log with who,
  when, the old value and the new value;
- there is no delete. Rows are retired or made inactive instead.
"""
import sqlite3
import uuid
from datetime import date, datetime, timezone

from .schema import LISTS, LISTS_BY_NAME

SCHEMA_VERSION = 1

SQL_TYPES = {"text": "TEXT", "note": "TEXT", "choice": "TEXT", "number": "REAL", "integer": "INTEGER",
             "bool": "INTEGER", "date": "TEXT", "datetime": "TEXT"}

SYSTEM_TABLES = """
CREATE TABLE IF NOT EXISTS organisations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organisations(id),
    email TEXT NOT NULL,
    password_hash TEXT,
    token_hash TEXT,
    token_purpose TEXT CHECK (token_purpose IN ('invite', 'reset') OR token_purpose IS NULL),
    token_expires_at TEXT,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (org_id, email)
);
CREATE TABLE IF NOT EXISTS data_links (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organisations(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    dataset TEXT NOT NULL CHECK (dataset IN ('measures', 'full_model', 'weekly_work')),
    token_hash TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_by TEXT,
    revoked_at TEXT,
    last_used_at TEXT,
    use_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quote(s):
    return "'" + s.replace("'", "''") + "'"


def table_ddl(lst):
    cols = ["id INTEGER PRIMARY KEY", "org_id INTEGER NOT NULL REFERENCES organisations(id)"]
    for c in lst.all_columns:
        parts = [c.name, SQL_TYPES[c.type]]
        if c.required:
            parts.append("NOT NULL")
        checks = []
        if c.choices:
            checks.append(f"{c.name} IN ({', '.join(_quote(v) for v in c.choices)})")
        if c.type == "bool":
            checks.append(f"{c.name} IN (0, 1)")
        if c.type == "date":
            checks.append(f"{c.name} GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'")
        if c.type == "datetime":
            checks.append(f"{c.name} GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z'")
        if c.required and c.type in ("text", "note"):
            checks.append(f"length(trim({c.name})) > 0")
        if checks:
            cond = " AND ".join(f"({x})" for x in checks)
            parts.append(f"CHECK ({c.name} IS NULL OR ({cond}))")
        cols.append(" ".join(parts))
    cols += ["created_at TEXT NOT NULL", "created_by TEXT NOT NULL", "modified_at TEXT NOT NULL",
             "modified_by TEXT NOT NULL", f"UNIQUE (org_id, {lst.key})"]
    stmts = [f"CREATE TABLE IF NOT EXISTS {lst.name} (\n    " + ",\n    ".join(cols) + "\n);"]
    for c in lst.columns:
        if c.indexed:
            stmts.append(f"CREATE INDEX IF NOT EXISTS ix_{lst.name}_{c.name} ON {lst.name} (org_id, {c.name});")
    return "\n".join(stmts)


def ddl():
    return SYSTEM_TABLES + "\n".join(table_ddl(lst) for lst in LISTS)


def connect(path):
    conn = sqlite3.connect(path, detect_types=0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init(conn):
    conn.executescript(ddl())
    conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))


# ---------------------------------------------------------------------------
# Python <-> database values
# ---------------------------------------------------------------------------
def to_db(col, value):
    if value is None or value == "":
        return None
    t = col.type
    if t == "bool":
        return 1 if value else 0
    if t == "date":
        return value.isoformat() if isinstance(value, date) else str(value)
    if t == "datetime":
        return iso(value) if isinstance(value, datetime) else str(value)
    if t == "number":
        return float(value)
    if t == "integer":
        return int(value)
    return value


def from_db(col, value):
    if value is None:
        return None
    t = col.type
    if t == "bool":
        return bool(value)
    if t == "date":
        return date.fromisoformat(value)
    if t == "datetime":
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if t == "number":
        return int(value) if float(value).is_integer() else float(value)
    return value


def display(col, value):
    """Text for audit_log and messages."""
    if value is None:
        return None
    if col.type == "bool":
        return "true" if value else "false"
    if col.type == "date":
        return value.isoformat()
    if col.type == "datetime":
        return iso(value)
    return str(value)


class NotFound(Exception):
    pass


class Repo:
    """All data access for one organisation."""

    def __init__(self, conn, org_id):
        self.conn = conn
        self.org_id = org_id

    # -- reading ---------------------------------------------------------
    def _row(self, lst, r):
        cols = {c.name: c for c in lst.all_columns}
        out = {name: from_db(c, r[name]) for name, c in cols.items()}
        out["_id"] = r["id"]
        out["_modified_at"] = r["modified_at"]
        out["_modified_by"] = r["modified_by"]
        return out

    def get(self, table, key):
        lst = LISTS_BY_NAME[table]
        r = self.conn.execute(f"SELECT * FROM {table} WHERE org_id = ? AND {lst.key} = ?",
                              (self.org_id, key)).fetchone()
        return self._row(lst, r) if r else None

    def find(self, table, where="", params=(), order="", limit=None, offset=0):
        """Rows matching a SQL condition. Column names come from schema.py
        only; values always go through params."""
        lst = LISTS_BY_NAME[table]
        sql = f"SELECT * FROM {table} WHERE org_id = ?"
        if where:
            sql += f" AND ({where})"
        sql += f" ORDER BY {order or lst.key}"
        if limit is not None:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        return [self._row(lst, r) for r in self.conn.execute(sql, (self.org_id, *params))]

    def count(self, table, where="", params=()):
        sql = f"SELECT COUNT(*) FROM {table} WHERE org_id = ?" + (f" AND ({where})" if where else "")
        return self.conn.execute(sql, (self.org_id, *params)).fetchone()[0]

    def by(self, table, **equals):
        lst = LISTS_BY_NAME[table]
        valid = {c.name for c in lst.all_columns}
        clauses, params = [], []
        for k, v in equals.items():
            if k not in valid:
                raise KeyError(f"{table}.{k}")
            col = next(c for c in lst.all_columns if c.name == k)
            clauses.append(f"{k} = ?")
            params.append(to_db(col, v))
        return self.find(table, " AND ".join(clauses), params)

    # -- writing ---------------------------------------------------------
    def _audit(self, table, key, action, field, old, new, who, when):
        restricted = table in LISTS_BY_NAME and LISTS_BY_NAME[table].restricted
        if restricted and field is not None:
            old, new = ("(hidden)" if old is not None else None), ("(hidden)" if new is not None else None)
        self.conn.execute(
            "INSERT INTO audit_log (org_id, audit_ref, list_name, item_key, action, field_name, old_value, new_value,"
            " changed_by, changed_at, created_at, created_by, modified_at, modified_by)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.org_id, "AUD-" + uuid.uuid4().hex[:16], table, key, action, field, old, new, who, iso(when),
             iso(when), who, iso(when), who))

    def insert(self, table, row, who, when=None, audit=True):
        lst = LISTS_BY_NAME[table]
        when = when or utcnow()
        cols = lst.all_columns
        names = [c.name for c in cols] + ["org_id", "created_at", "created_by", "modified_at", "modified_by"]
        values = [to_db(c, row.get(c.name)) for c in cols] + [self.org_id, iso(when), who, iso(when), who]
        self.conn.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})", values)
        if audit and table != "audit_log":
            self._audit(table, row[lst.key], "create", None, None, None, who, when)
        return self.get(table, row[lst.key])

    def update(self, table, key, changes, who, when=None, action="edit", audit=True):
        """Change some fields. Only fields whose value actually changes are
        written and audited. Returns the updated row."""
        lst = LISTS_BY_NAME[table]
        cols = {c.name: c for c in lst.all_columns}
        current = self.get(table, key)
        if current is None:
            raise NotFound(f"{table} {key}")
        when = when or utcnow()
        changed = {}
        for field, new in changes.items():
            if field not in cols or field == lst.key:
                raise KeyError(f"{table}.{field} can't be changed")
            if to_db(cols[field], current[field]) != to_db(cols[field], new):
                changed[field] = new
        if not changed:
            return current
        sets = ", ".join(f"{f} = ?" for f in changed) + ", modified_at = ?, modified_by = ?"
        params = [to_db(cols[f], v) for f, v in changed.items()] + [iso(when), who, self.org_id, key]
        self.conn.execute(f"UPDATE {table} SET {sets} WHERE org_id = ? AND {lst.key} = ?", params)
        for field, new in changed.items():
            if not audit:
                break
            act = action
            if action == "edit" and field in ("status", "version_status"):
                act = "status_change"
            self._audit(table, key, act, field, display(cols[field], current[field]), display(cols[field], new),
                        who, when)
        return self.get(table, key)

    def transaction(self):
        return _Transaction(self.conn)


class _Transaction:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        return False


def claim_today(conn, marker, today):
    """True for the first caller on a given day, across every process."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (marker,)).fetchone()
    if row and row["value"] >= today.isoformat():
        return False  # the usual case: no write lock needed
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (marker,)).fetchone()
        if row and row["value"] >= today.isoformat():
            return False
        conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (marker, today.isoformat()))
        return True
    finally:
        conn.execute("COMMIT")


def org_slug(conn, org_id):
    return conn.execute("SELECT slug FROM organisations WHERE id = ?", (org_id,)).fetchone()[0]


def create_org(conn, name, slug):
    conn.execute("INSERT INTO organisations (name, slug, created_at) VALUES (?, ?, ?)", (name, slug, iso(utcnow())))
    return conn.execute("SELECT id FROM organisations WHERE slug = ?", (slug,)).fetchone()[0]
