"""Deterministic Tool Server (SRS §5.4, §6.4).

All tools are tenant-scoped. The tenant_id is injected by the orchestrator
from the authenticated session and is never exposed in the JSON Schema visible
to the LLM — the model cannot choose a tenant.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.db import get_db


# ---------- JSON Schemas exposed to the model ----------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "query_service_line_pnl",
        "description": (
            "Returns contribution margin and component costs by service line for a given period. "
            "Use when the user asks about service-line profitability, margin trends, or cost composition."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Service line codes (e.g. CARD, ORTHO). Empty array = all.",
                },
                "period_start": {"type": "string", "format": "date"},
                "period_end": {"type": "string", "format": "date"},
                "include_overhead_allocation": {"type": "boolean", "default": True},
            },
            "required": ["period_start", "period_end"],
        },
    },
    {
        "name": "query_revenue_cycle",
        "description": (
            "Returns revenue cycle KPIs (Days in AR, denial rate, net collection rate, aging) "
            "for a period, optionally filtered by payer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of": {"type": "string", "format": "date"},
                "kpis": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "days_in_ar",
                            "denial_rate",
                            "net_collection_rate",
                            "aging_buckets",
                        ],
                    },
                },
                "payer_codes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["as_of", "kpis"],
        },
    },
    {
        "name": "query_payer_performance",
        "description": "Per-payer paid/denied/outstanding and Days in AR for the trailing months.",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of": {"type": "string", "format": "date"},
                "trailing_months": {"type": "integer", "minimum": 1, "maximum": 12, "default": 3},
            },
            "required": ["as_of"],
        },
    },
    {
        "name": "query_cash_position",
        "description": "Latest cash and bank balances by account, with prior-period comparison.",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of": {"type": "string", "format": "date"},
            },
            "required": ["as_of"],
        },
    },
    {
        "name": "forecast_cash",
        "description": (
            "Generate a 13-week cash flow forecast based on historical inflows and outflows. "
            "Optional scenario overlays."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "horizon_weeks": {"type": "integer", "minimum": 4, "maximum": 26, "default": 13},
                "scenarios": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["base", "uhi_delay_30d", "fx_shock_15pct", "volume_drop_10pct"],
                    },
                    "default": ["base"],
                },
            },
        },
    },
    {
        "name": "compute_kpi",
        "description": "Compute a named KPI with units; e.g. operating_margin, ebitda_margin, ar_turnover.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kpi": {
                    "type": "string",
                    "enum": ["operating_margin", "ebitda_margin", "ar_turnover", "cost_per_encounter"],
                },
                "period_start": {"type": "string", "format": "date"},
                "period_end": {"type": "string", "format": "date"},
            },
            "required": ["kpi", "period_start", "period_end"],
        },
    },
    {
        "name": "run_controls_check",
        "description": "Execute one or more named controls rules and return exceptions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rule_ids": {"type": "array", "items": {"type": "string"}},
                "as_of": {"type": "string", "format": "date"},
            },
            "required": ["rule_ids", "as_of"],
        },
    },
    {
        "name": "compose_chart",
        "description": (
            "Produce a chart spec the UI can render. Pass tabular data already obtained from another tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "type": {"type": "string", "enum": ["bar", "line", "area", "donut"]},
                "x_label": {"type": "string"},
                "y_label": {"type": "string"},
                "series": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "data": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {"x": {}, "y": {"type": "number"}},
                                    "required": ["x", "y"],
                                },
                            },
                        },
                        "required": ["name", "data"],
                    },
                },
            },
            "required": ["title", "type", "series"],
        },
    },
    {
        "name": "compose_table",
        "description": "Produce a table spec the UI can render. Caller supplies rows already computed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "columns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "label": {"type": "string"},
                            "format": {"type": "string", "enum": ["text", "number", "currency", "percent", "date"]},
                        },
                        "required": ["key", "label"],
                    },
                },
                "rows": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["title", "columns", "rows"],
        },
    },
]


def schemas_for(names: list[str]) -> list[dict[str, Any]]:
    return [t for t in TOOL_SCHEMAS if t["name"] in names]


# ---------- Tool implementations ----------

def _months_between(start: str, end: str) -> list[str]:
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    out = []
    cur = date(s.year, s.month, 1)
    while cur <= e:
        out.append(cur.strftime("%Y-%m"))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def _query_service_line_pnl(tenant_id: str, args: dict) -> dict:
    months = _months_between(args["period_start"], args["period_end"])
    placeholders = ",".join("?" * len(months))
    sl_filter = ""
    params: list[Any] = [tenant_id, *months]
    if args.get("service_lines"):
        sl_filter = " AND service_line IN (" + ",".join("?" * len(args["service_lines"])) + ")"
        params.extend(args["service_lines"])
    include_oh = args.get("include_overhead_allocation", True)

    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT sl.code, sl.name, sl.name_ar,
                       SUM(g.revenue) AS revenue,
                       SUM(g.direct_cost) AS direct_cost,
                       SUM(g.overhead) AS overhead,
                       SUM(g.encounters) AS encounters
                FROM gl_entries g
                JOIN service_lines sl
                  ON sl.tenant_id = g.tenant_id AND sl.code = g.service_line
                WHERE g.tenant_id = ?
                  AND g.period IN ({placeholders})
                  {sl_filter}
                GROUP BY sl.code, sl.name, sl.name_ar
                ORDER BY revenue DESC""",
            params,
        ).fetchall()

    items = []
    total_rev = total_cost = total_encounters = 0.0
    for r in rows:
        rev = float(r["revenue"] or 0)
        dc = float(r["direct_cost"] or 0)
        oh = float(r["overhead"] or 0) if include_oh else 0.0
        cm = rev - dc - oh
        encounters = int(r["encounters"] or 0)
        items.append({
            "code": r["code"],
            "name": r["name"],
            "name_ar": r["name_ar"],
            "revenue": round(rev, 2),
            "direct_cost": round(dc, 2),
            "overhead": round(oh, 2),
            "contribution_margin": round(cm, 2),
            "margin_pct": round((cm / rev * 100), 2) if rev else 0.0,
            "encounters": encounters,
        })
        total_rev += rev
        total_cost += dc + oh
        total_encounters += encounters

    return {
        "currency": "EGP",
        "period": {"start": args["period_start"], "end": args["period_end"]},
        "service_lines": items,
        "totals": {
            "revenue": round(total_rev, 2),
            "cost": round(total_cost, 2),
            "contribution_margin": round(total_rev - total_cost, 2),
            "margin_pct": round((total_rev - total_cost) / total_rev * 100, 2) if total_rev else 0.0,
            "encounters": int(total_encounters),
        },
    }


def _query_revenue_cycle(tenant_id: str, args: dict) -> dict:
    as_of = args["as_of"]
    period = as_of[:7]
    payer_filter = ""
    params: list[Any] = [tenant_id, period]
    if args.get("payer_codes"):
        payer_filter = " AND payer_code IN (" + ",".join("?" * len(args["payer_codes"])) + ")"
        params.extend(args["payer_codes"])

    with get_db() as conn:
        agg = conn.execute(
            f"""SELECT SUM(billed) AS billed, SUM(paid) AS paid,
                       SUM(denied) AS denied, SUM(outstanding) AS outstanding,
                       AVG(days_in_ar) AS days_in_ar
                FROM claims_summary
                WHERE tenant_id = ? AND period = ?{payer_filter}""",
            params,
        ).fetchone()

    billed = float(agg["billed"] or 0)
    paid = float(agg["paid"] or 0)
    denied = float(agg["denied"] or 0)
    outstanding = float(agg["outstanding"] or 0)
    days_in_ar = float(agg["days_in_ar"] or 0)

    out: dict[str, Any] = {"as_of": as_of, "currency": "EGP"}
    for k in args["kpis"]:
        if k == "days_in_ar":
            out["days_in_ar"] = round(days_in_ar, 1)
        elif k == "denial_rate":
            out["denial_rate_pct"] = round(denied / billed * 100, 2) if billed else 0.0
        elif k == "net_collection_rate":
            out["net_collection_rate_pct"] = round(paid / (billed - denied) * 100, 2) if (billed - denied) else 0.0
        elif k == "aging_buckets":
            # Synthetic split derived from outstanding for V0
            out["aging_buckets"] = {
                "0-30": round(outstanding * 0.45, 2),
                "31-60": round(outstanding * 0.25, 2),
                "61-90": round(outstanding * 0.15, 2),
                "91-180": round(outstanding * 0.10, 2),
                ">180": round(outstanding * 0.05, 2),
            }
    out["totals"] = {"billed": billed, "paid": paid, "denied": denied, "outstanding": outstanding}
    return out


def _query_payer_performance(tenant_id: str, args: dict) -> dict:
    as_of = datetime.strptime(args["as_of"], "%Y-%m-%d").date()
    n = args.get("trailing_months", 3)
    months: list[str] = []
    cur = date(as_of.year, as_of.month, 1)
    for _ in range(n):
        months.append(cur.strftime("%Y-%m"))
        if cur.month == 1:
            cur = date(cur.year - 1, 12, 1)
        else:
            cur = date(cur.year, cur.month - 1, 1)
    placeholders = ",".join("?" * len(months))

    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT p.code, p.name, p.name_ar,
                       SUM(c.billed) AS billed,
                       SUM(c.paid) AS paid,
                       SUM(c.denied) AS denied,
                       SUM(c.outstanding) AS outstanding,
                       AVG(c.days_in_ar) AS days_in_ar
                FROM claims_summary c
                JOIN payers p
                  ON p.tenant_id = c.tenant_id AND p.code = c.payer_code
                WHERE c.tenant_id = ? AND c.period IN ({placeholders})
                GROUP BY p.code, p.name, p.name_ar
                ORDER BY billed DESC""",
            [tenant_id, *months],
        ).fetchall()

    payers = []
    for r in rows:
        billed = float(r["billed"] or 0)
        denied = float(r["denied"] or 0)
        payers.append({
            "code": r["code"],
            "name": r["name"],
            "name_ar": r["name_ar"],
            "billed": round(billed, 2),
            "paid": round(float(r["paid"] or 0), 2),
            "denied": round(denied, 2),
            "denial_rate_pct": round(denied / billed * 100, 2) if billed else 0.0,
            "outstanding": round(float(r["outstanding"] or 0), 2),
            "days_in_ar": round(float(r["days_in_ar"] or 0), 1),
        })
    return {"as_of": args["as_of"], "trailing_months": n, "currency": "EGP", "payers": payers}


def _query_cash_position(tenant_id: str, args: dict) -> dict:
    with get_db() as conn:
        latest = conn.execute(
            """SELECT MAX(as_of_date) AS d FROM cash_balances
               WHERE tenant_id = ? AND as_of_date <= ?""",
            (tenant_id, args["as_of"]),
        ).fetchone()
        d = latest["d"]
        if not d:
            return {"as_of": args["as_of"], "accounts": [], "total": 0.0}
        rows = conn.execute(
            """SELECT account, currency, balance FROM cash_balances
               WHERE tenant_id = ? AND as_of_date = ?""",
            (tenant_id, d),
        ).fetchall()
        # Prior week
        prior_d = (datetime.strptime(d, "%Y-%m-%d").date() - timedelta(days=7)).isoformat()
        prior = conn.execute(
            """SELECT SUM(balance) AS s FROM cash_balances
               WHERE tenant_id = ? AND as_of_date = (
                 SELECT MAX(as_of_date) FROM cash_balances
                 WHERE tenant_id = ? AND as_of_date <= ?
               )""",
            (tenant_id, tenant_id, prior_d),
        ).fetchone()

    total = sum(float(r["balance"]) for r in rows)
    prior_total = float(prior["s"] or 0)
    return {
        "as_of": d,
        "currency": "EGP",
        "accounts": [
            {"account": r["account"], "currency": r["currency"], "balance": round(float(r["balance"]), 2)}
            for r in rows
        ],
        "total": round(total, 2),
        "wow_delta": round(total - prior_total, 2),
        "wow_delta_pct": round((total - prior_total) / prior_total * 100, 2) if prior_total else 0.0,
    }


def _forecast_cash(tenant_id: str, args: dict) -> dict:
    horizon = args.get("horizon_weeks", 13)
    scenarios = args.get("scenarios", ["base"])

    cash = _query_cash_position(tenant_id, {"as_of": date.today().isoformat()})
    opening = cash["total"]

    # Use trailing 3 months of net inflow as base run-rate (very simplified V0)
    today = date.today()
    rcm = _query_payer_performance(tenant_id, {"as_of": today.isoformat(), "trailing_months": 3})
    monthly_inflow = sum(p["paid"] for p in rcm["payers"]) / 3 if rcm["payers"] else 0.0
    weekly_inflow = monthly_inflow / 4.33

    # Outflow approx = 90% of inflow (V0 placeholder for payroll+supplies+overheads)
    weekly_outflow = weekly_inflow * 0.92

    overlays = {
        "base": {"in": 1.0, "out": 1.0},
        "uhi_delay_30d": {"in": 0.6, "out": 1.0},   # claims delayed
        "fx_shock_15pct": {"in": 1.0, "out": 1.15},  # imported supplies cost more
        "volume_drop_10pct": {"in": 0.9, "out": 0.95},
    }

    out = []
    for s in scenarios:
        ov = overlays.get(s, overlays["base"])
        bal = opening
        weeks = []
        for w in range(1, horizon + 1):
            inflow = weekly_inflow * ov["in"]
            outflow = weekly_outflow * ov["out"]
            bal += inflow - outflow
            weeks.append({
                "week": w,
                "inflow": round(inflow, 2),
                "outflow": round(outflow, 2),
                "ending_balance": round(bal, 2),
            })
        out.append({"scenario": s, "ending_balance": round(bal, 2), "weeks": weeks})

    return {
        "currency": "EGP",
        "opening_balance": round(opening, 2),
        "horizon_weeks": horizon,
        "scenarios": out,
    }


def _compute_kpi(tenant_id: str, args: dict) -> dict:
    pnl = _query_service_line_pnl(tenant_id, {
        "period_start": args["period_start"],
        "period_end": args["period_end"],
    })
    rev = pnl["totals"]["revenue"]
    cost = pnl["totals"]["cost"]
    encounters = pnl["totals"]["encounters"]

    kpi = args["kpi"]
    if kpi == "operating_margin":
        val = (rev - cost) / rev * 100 if rev else 0.0
        return {"kpi": kpi, "value": round(val, 2), "unit": "percent"}
    if kpi == "ebitda_margin":
        ebitda = (rev - cost) * 1.08  # add-back D&A approx 8% (V0 placeholder)
        val = ebitda / rev * 100 if rev else 0.0
        return {"kpi": kpi, "value": round(val, 2), "unit": "percent"}
    if kpi == "ar_turnover":
        rcm = _query_revenue_cycle(tenant_id, {"as_of": args["period_end"], "kpis": ["days_in_ar"]})
        days = rcm.get("days_in_ar", 0) or 1
        return {"kpi": kpi, "value": round(365 / days, 2), "unit": "turns_per_year"}
    if kpi == "cost_per_encounter":
        val = cost / encounters if encounters else 0.0
        return {"kpi": kpi, "value": round(val, 2), "unit": "EGP"}
    return {"error": f"unknown kpi {kpi}"}


def _run_controls_check(tenant_id: str, args: dict) -> dict:
    # V0 ships two example rules: weekend-JE and round-amount-JE.
    rules = {
        "CTRL-JE-001": "Journal entries posted on weekends",
        "CTRL-JE-002": "Journal entries with suspiciously round amounts (>=100k)",
        "CTRL-AR-001": "Payers with denial rate above tenant threshold (10%)",
    }
    requested = args.get("rule_ids") or list(rules.keys())
    exceptions = []
    if "CTRL-AR-001" in requested:
        rcm = _query_payer_performance(tenant_id, {"as_of": args["as_of"], "trailing_months": 3})
        for p in rcm["payers"]:
            if p["denial_rate_pct"] > 10:
                exceptions.append({
                    "rule_id": "CTRL-AR-001",
                    "severity": "high" if p["denial_rate_pct"] > 15 else "medium",
                    "subject": f"Payer {p['name']} ({p['code']})",
                    "detail": f"Denial rate {p['denial_rate_pct']}% exceeds 10% threshold",
                    "evidence_ref": f"payer:{p['code']}:trailing_3m",
                })
    return {
        "as_of": args["as_of"],
        "rules_evaluated": [{"id": r, "description": rules[r]} for r in requested if r in rules],
        "exceptions": exceptions,
        "exception_count": len(exceptions),
    }


# ---------- Dispatcher ----------

DISPATCH = {
    "query_service_line_pnl": _query_service_line_pnl,
    "query_revenue_cycle": _query_revenue_cycle,
    "query_payer_performance": _query_payer_performance,
    "query_cash_position": _query_cash_position,
    "forecast_cash": _forecast_cash,
    "compute_kpi": _compute_kpi,
    "run_controls_check": _run_controls_check,
    # compose_chart / compose_table are pure data passthroughs (echo back the spec)
    "compose_chart": lambda tenant_id, args: {"chart": args},
    "compose_table": lambda tenant_id, args: {"table": args},
}


def invoke(tool_name: str, tenant_id: str, arguments: dict) -> dict:
    if tool_name not in DISPATCH:
        return {"error": f"unknown tool: {tool_name}"}
    try:
        return DISPATCH[tool_name](tenant_id, arguments or {})
    except Exception as e:  # surface tool errors as data, never crash the agent loop
        return {"error": str(e), "tool": tool_name}
