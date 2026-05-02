"""Postgres connection pool + schema bootstrap (replaces V0 SQLite).

The rest of the app uses `with get_db() as conn:` and `conn.execute(sql, params).fetchall()`
— a shape that works identically against psycopg's connection.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings


_pool: Optional[ConnectionPool] = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        # Defer-open to avoid raising at import; we wait for the DB to be ready below.
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=False,
        )
        _pool.open(wait=True, timeout=30)
    return _pool


@contextmanager
def get_db():
    pool = _get_pool()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_ar TEXT,
    currency TEXT DEFAULT 'EGP',
    plan TEXT DEFAULT 'pro',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    locale TEXT DEFAULT 'en',
    is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE
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
    period TEXT NOT NULL,
    service_line TEXT NOT NULL,
    revenue DOUBLE PRECISION NOT NULL DEFAULT 0,
    direct_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    overhead DOUBLE PRECISION NOT NULL DEFAULT 0,
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
    billed DOUBLE PRECISION NOT NULL,
    paid DOUBLE PRECISION NOT NULL,
    denied DOUBLE PRECISION NOT NULL,
    outstanding DOUBLE PRECISION NOT NULL,
    days_in_ar DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant_id, period, payer_code)
);

CREATE TABLE IF NOT EXISTS cash_balances (
    tenant_id TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    account TEXT NOT NULL,
    currency TEXT DEFAULT 'EGP',
    balance DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant_id, as_of_date, account)
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT,
    user_id TEXT,
    event TEXT NOT NULL,
    payload_json TEXT,
    prev_hash TEXT,
    hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


# Idempotent ALTERs for tables that already exist on older deploys.
MIGRATIONS = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE;
"""


def init_db() -> None:
    """Run schema + migrations. Waits up to 30s for Postgres to come up."""
    deadline = time.time() + 30
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            with get_db() as conn:
                # psycopg 3 supports multi-statement execute when no params are passed.
                conn.execute(SCHEMA)
                conn.execute(MIGRATIONS)
            return
        except psycopg.OperationalError as e:
            last_err = e
            time.sleep(1.5)
    raise RuntimeError(f"could not connect to Postgres: {last_err}")
