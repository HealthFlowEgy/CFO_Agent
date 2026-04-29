import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import settings


def _connect() -> sqlite3.Connection:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_ar TEXT,
    currency TEXT DEFAULT 'EGP',
    plan TEXT DEFAULT 'pro',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    locale TEXT DEFAULT 'en'
);

CREATE TABLE IF NOT EXISTS tenant_users (
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    user_id   TEXT NOT NULL REFERENCES users(id),
    role TEXT NOT NULL DEFAULT 'cfo',
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS service_lines (
    tenant_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    name_ar TEXT,
    PRIMARY KEY (tenant_id, code)
);

CREATE TABLE IF NOT EXISTS gl_entries (
    tenant_id TEXT NOT NULL,
    period TEXT NOT NULL,            -- YYYY-MM
    service_line TEXT NOT NULL,
    revenue REAL NOT NULL DEFAULT 0,
    direct_cost REAL NOT NULL DEFAULT 0,
    overhead REAL NOT NULL DEFAULT 0,
    encounters INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, period, service_line)
);

CREATE TABLE IF NOT EXISTS payers (
    tenant_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    name_ar TEXT,
    PRIMARY KEY (tenant_id, code)
);

CREATE TABLE IF NOT EXISTS claims_summary (
    tenant_id TEXT NOT NULL,
    period TEXT NOT NULL,
    payer_code TEXT NOT NULL,
    billed REAL NOT NULL,
    paid REAL NOT NULL,
    denied REAL NOT NULL,
    outstanding REAL NOT NULL,
    days_in_ar REAL NOT NULL,
    PRIMARY KEY (tenant_id, period, payer_code)
);

CREATE TABLE IF NOT EXISTS cash_balances (
    tenant_id TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    account TEXT NOT NULL,
    currency TEXT DEFAULT 'EGP',
    balance REAL NOT NULL,
    PRIMARY KEY (tenant_id, as_of_date, account)
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT,
    user_id TEXT,
    event TEXT NOT NULL,
    payload_json TEXT,
    prev_hash TEXT,
    hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA)
