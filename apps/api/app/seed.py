"""Synthetic seed data for two demo tenants.

Realistic-looking hospital finance shapes (orders of magnitude, not real data).
Idempotent: safe to call on every boot.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from app.auth import hash_password
from app.db import get_db


TENANTS = [
    {
        "id": "tnt_cairo",
        "name": "Cairo Specialty Hospital",
        "name_ar": "مستشفى القاهرة التخصصي",
        "currency": "EGP",
        "plan": "enterprise",
    },
    {
        "id": "tnt_alex",
        "name": "Alexandria Medical Center",
        "name_ar": "مركز الإسكندرية الطبي",
        "currency": "EGP",
        "plan": "pro",
    },
]


USERS = [
    # email, name, password, locale, tenants_with_role
    {
        "id": "usr_amr",
        "email": "amr.cfo@healthflow.demo",
        "name": "Amr Hassan",
        "password": "demo1234",
        "locale": "en",
        "memberships": [("tnt_cairo", "cfo"), ("tnt_alex", "cfo")],
    },
    {
        "id": "usr_layla",
        "email": "layla.controller@healthflow.demo",
        "name": "Layla Ibrahim",
        "password": "demo1234",
        "locale": "ar",
        "memberships": [("tnt_cairo", "controller")],
    },
    {
        "id": "usr_omar",
        "email": "omar.analyst@healthflow.demo",
        "name": "Omar Nabil",
        "password": "demo1234",
        "locale": "en",
        "memberships": [("tnt_alex", "analyst")],
    },
]


SERVICE_LINES = [
    ("CARD",    "Cardiology",                "أمراض القلب"),
    ("ORTHO",   "Orthopedics",               "العظام"),
    ("ONC",     "Oncology",                  "الأورام"),
    ("OBGYN",   "Obstetrics & Gynecology",   "النساء والتوليد"),
    ("PEDS",    "Pediatrics",                "طب الأطفال"),
    ("ER",      "Emergency",                 "الطوارئ"),
    ("ICU",     "Intensive Care",            "العناية المركزة"),
    ("RAD",     "Radiology & Imaging",       "الأشعة"),
]


PAYERS = [
    ("UHI",     "Universal Health Insurance",  "التأمين الصحي الشامل"),
    ("AXA",     "AXA Egypt",                    "أكسا مصر"),
    ("BUPA",    "Bupa Global",                  "بوبا"),
    ("MISR",    "Misr Insurance",               "مصر للتأمين"),
    ("SELF",    "Self-Pay / Out-of-Pocket",     "دفع ذاتي"),
    ("CORP",    "Corporate Contracts",          "عقود الشركات"),
]


def _periods(months_back: int) -> list[str]:
    today = date.today().replace(day=1)
    out: list[str] = []
    cur = today
    for _ in range(months_back):
        out.append(cur.strftime("%Y-%m"))
        if cur.month == 1:
            cur = date(cur.year - 1, 12, 1)
        else:
            cur = date(cur.year, cur.month - 1, 1)
    return list(reversed(out))


def _seed_tenant(conn, tenant: dict, *, scale: float, rng: random.Random) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO tenants (id, name, name_ar, currency, plan)
           VALUES (?, ?, ?, ?, ?)""",
        (tenant["id"], tenant["name"], tenant["name_ar"], tenant["currency"], tenant["plan"]),
    )

    for code, name, name_ar in SERVICE_LINES:
        conn.execute(
            "INSERT OR IGNORE INTO service_lines (tenant_id, code, name, name_ar) VALUES (?, ?, ?, ?)",
            (tenant["id"], code, name, name_ar),
        )

    for code, name, name_ar in PAYERS:
        conn.execute(
            "INSERT OR IGNORE INTO payers (tenant_id, code, name, name_ar) VALUES (?, ?, ?, ?)",
            (tenant["id"], code, name, name_ar),
        )

    # GL: 12 months back
    periods = _periods(12)

    # base monthly revenue per service line (EGP M)
    base = {
        "CARD": 12.0, "ORTHO": 9.0, "ONC": 14.0, "OBGYN": 7.0,
        "PEDS": 5.0,  "ER": 8.0,    "ICU": 11.0, "RAD": 6.0,
    }
    for p_idx, period in enumerate(periods):
        # gradual growth + seasonal noise
        season = 1.0 + 0.06 * ((p_idx % 12) / 12)
        for sl in SERVICE_LINES:
            code = sl[0]
            rev = base[code] * scale * season * 1_000_000 * rng.uniform(0.9, 1.1)
            direct_cost = rev * rng.uniform(0.45, 0.65)
            overhead = rev * rng.uniform(0.18, 0.28)
            encounters = int(rev / rng.uniform(2500, 5500))
            conn.execute(
                """INSERT OR REPLACE INTO gl_entries
                   (tenant_id, period, service_line, revenue, direct_cost, overhead, encounters)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (tenant["id"], period, code, rev, direct_cost, overhead, encounters),
            )

    # Claims summary by payer × period (last 6 months for performance)
    payer_mix = {"UHI": 0.42, "AXA": 0.14, "BUPA": 0.10, "MISR": 0.16, "SELF": 0.08, "CORP": 0.10}
    payer_denial = {"UHI": 0.14, "AXA": 0.06, "BUPA": 0.05, "MISR": 0.09, "SELF": 0.02, "CORP": 0.07}
    payer_dso = {"UHI": 78, "AXA": 42, "BUPA": 38, "MISR": 65, "SELF": 12, "CORP": 55}

    for period in periods[-6:]:
        # monthly tenant total ~ 70% of GL revenue (claims billed)
        gl_total = sum(
            (r["revenue"] or 0)
            for r in conn.execute(
                "SELECT revenue FROM gl_entries WHERE tenant_id = ? AND period = ?",
                (tenant["id"], period),
            ).fetchall()
        )
        billed_total = gl_total * 0.85
        for code, share in payer_mix.items():
            billed = billed_total * share * rng.uniform(0.92, 1.08)
            denied = billed * payer_denial[code] * rng.uniform(0.85, 1.15)
            paid = (billed - denied) * rng.uniform(0.78, 0.92)
            outstanding = billed - denied - paid
            dso = payer_dso[code] * rng.uniform(0.9, 1.1)
            conn.execute(
                """INSERT OR REPLACE INTO claims_summary
                   (tenant_id, period, payer_code, billed, paid, denied, outstanding, days_in_ar)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (tenant["id"], period, code, billed, paid, denied, outstanding, dso),
            )

    # Cash balances: weekly snapshots for last 13 weeks
    today = date.today()
    accounts = [("CIB-EGP-Operating", "EGP"), ("HSBC-USD-Reserve", "EGP"),
                ("NBE-EGP-Payroll", "EGP"), ("Petty-Cash", "EGP")]
    base_balances = {"CIB-EGP-Operating": 28_000_000.0, "HSBC-USD-Reserve": 9_500_000.0,
                     "NBE-EGP-Payroll": 4_500_000.0, "Petty-Cash": 220_000.0}
    for w in range(13, -1, -1):
        d = today - timedelta(days=w * 7)
        for acct, ccy in accounts:
            b = base_balances[acct] * scale * (1.0 + rng.uniform(-0.05, 0.05) - w * 0.005)
            conn.execute(
                """INSERT OR REPLACE INTO cash_balances
                   (tenant_id, as_of_date, account, currency, balance)
                   VALUES (?, ?, ?, ?, ?)""",
                (tenant["id"], d.isoformat(), acct, ccy, b),
            )


def seed_demo_data() -> None:
    rng = random.Random(42)
    with get_db() as conn:
        # tenants + per-tenant data
        for t in TENANTS:
            scale = 1.0 if t["id"] == "tnt_cairo" else 0.65
            _seed_tenant(conn, t, scale=scale, rng=rng)

        # users + memberships
        for u in USERS:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (u["id"],)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, name, locale) VALUES (?, ?, ?, ?, ?)",
                    (u["id"], u["email"].lower(), hash_password(u["password"]), u["name"], u["locale"]),
                )
            for tid, role in u["memberships"]:
                conn.execute(
                    "INSERT OR IGNORE INTO tenant_users (tenant_id, user_id, role) VALUES (?, ?, ?)",
                    (tid, u["id"], role),
                )
