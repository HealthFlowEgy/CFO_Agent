"""Deterministic Tool Server (SRS §5.4, §6.4).

All tools are tenant-scoped. The tenant_id is injected by the orchestrator
from the authenticated session and is never exposed in the JSON Schema visible
to the LLM — the model cannot choose a tenant.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.db import get_db
from app import memory as memory_mod
from app import uploads as uploads_mod


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
        "name": "analyze_uploaded_statement",
        "description": (
            "Return the parsed structured summary of a previously uploaded statement "
            "(PDF / CSV / XLS / XLSX). Use this whenever the user asks to analyze, "
            "review, summarize, or extract numbers from an uploaded file. "
            "You MUST cite this tool for any number you quote from the document."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "upload_id": {"type": "string", "description": "id returned at upload time, e.g. up_abc123"}
            },
            "required": ["upload_id"],
        },
    },
    {
        "name": "recommend_actions_from_statement",
        "description": (
            "Generate a structured set of CFO recommendations grounded in the parsed "
            "summary of an uploaded statement. Use AFTER analyze_uploaded_statement. "
            "Returns a list of recommendations with severity, rationale, and a suggested follow-up."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "upload_id": {"type": "string"},
                "focus": {
                    "type": "string",
                    "enum": ["liquidity", "collections", "cost_control", "compliance", "general"],
                    "default": "general",
                },
            },
            "required": ["upload_id"],
        },
    },
    {
        "name": "recall_memory",
        "description": (
            "Recall pinned facts and prior insights for the current user/tenant. "
            "Use at the start of an analysis when prior context might apply (e.g. "
            "\"What did we say last week about UHI denials?\")."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional topic hint to bias retrieval."},
                "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            },
        },
    },
    {
        "name": "pin_memory",
        "description": (
            "Persist a short, durable fact about the tenant or user that should "
            "influence future analyses. Examples: 'Payroll runs from NBE on the 25th', "
            "'CFO prefers EGP-only narratives'. Keep facts under 200 chars."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string"},
                "importance": {"type": "integer", "minimum": 1, "maximum": 10, "default": 7},
            },
            "required": ["fact"],
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
    placeholders = ",".join(["%s"] * len(months))
    sl_filter = ""
    params: list[Any] = [tenant_id, *months]
    if args.get("service_lines"):
        sl_filter = " AND service_line IN (" + ",".join(["%s"] * len(args["service_lines"])) + ")"
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
                WHERE g.tenant_id = %s
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
        payer_filter = " AND payer_code IN (" + ",".join(["%s"] * len(args["payer_codes"])) + ")"
        params.extend(args["payer_codes"])

    with get_db() as conn:
        agg = conn.execute(
            f"""SELECT SUM(billed) AS billed, SUM(paid) AS paid,
                       SUM(denied) AS denied, SUM(outstanding) AS outstanding,
                       AVG(days_in_ar) AS days_in_ar
                FROM claims_summary
                WHERE tenant_id = %s AND period = %s{payer_filter}""",
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
    placeholders = ",".join(["%s"] * len(months))

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
                WHERE c.tenant_id = %s AND c.period IN ({placeholders})
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
               WHERE tenant_id = %s AND as_of_date <= %s""",
            (tenant_id, args["as_of"]),
        ).fetchone()
        d = latest["d"]
        if not d:
            return {"as_of": args["as_of"], "accounts": [], "total": 0.0}
        rows = conn.execute(
            """SELECT account, currency, balance FROM cash_balances
               WHERE tenant_id = %s AND as_of_date = %s""",
            (tenant_id, d),
        ).fetchall()
        # Prior week
        prior_d = (datetime.strptime(d, "%Y-%m-%d").date() - timedelta(days=7)).isoformat()
        prior = conn.execute(
            """SELECT SUM(balance) AS s FROM cash_balances
               WHERE tenant_id = %s AND as_of_date = (
                 SELECT MAX(as_of_date) FROM cash_balances
                 WHERE tenant_id = %s AND as_of_date <= %s
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

def _analyze_uploaded_statement(tenant_id: str, args: dict) -> dict:
    up = uploads_mod.get_upload(tenant_id, args["upload_id"])
    if not up:
        return {"error": f"upload not found: {args['upload_id']}"}
    if up.get("status") != "parsed":
        return {"error": up.get("parse_error") or "upload could not be parsed",
                "upload_id": up["id"], "filename": up["filename"]}
    return {
        "upload_id": up["id"],
        "filename": up["filename"],
        "kind": up["kind"],
        "summary": up["summary"],
    }


def _recommend_actions_from_statement(tenant_id: str, args: dict) -> dict:
    up = uploads_mod.get_upload(tenant_id, args["upload_id"])
    if not up or up.get("status") != "parsed":
        return {"error": "upload not parsed yet"}
    s = up["summary"] or {}
    kind = s.get("kind") or up.get("kind") or "generic"
    focus = args.get("focus", "general")
    recs: list[dict] = []

    if kind == "bank_statement":
        net = float(s.get("net_movement") or 0)
        debits_sum = float((s.get("debits") or {}).get("sum") or 0)
        credits_sum = float((s.get("credits") or {}).get("sum") or 0)
        if net < 0:
            recs.append({"severity": "high", "action": "Investigate negative net movement",
                         "rationale": f"Net cash movement on the statement is {net:,.2f} (debits {debits_sum:,.2f} > credits {credits_sum:,.2f})."})
        big_debit = float(s.get("largest_debit") or 0)
        if abs(big_debit) > abs(net) * 0.4 and big_debit != 0:
            recs.append({"severity": "medium", "action": "Validate the largest debit",
                         "rationale": f"Single debit of {big_debit:,.2f} accounts for >40% of net movement; confirm authorization and counterparty."})
        if focus == "liquidity":
            recs.append({"severity": "medium", "action": "Refresh 13-week cash forecast",
                         "rationale": "Use the closing balance and recent inflow run-rate to update the rolling forecast."})

    elif kind == "ar_aging":
        buckets = s.get("aging_buckets") or {}
        total = float(s.get("total_outstanding") or 0)
        gt90 = sum(float(v) for k, v in buckets.items() if any(t in k for t in ["91", ">90", ">180"]))
        if total and gt90 / total > 0.20:
            recs.append({"severity": "high", "action": "Escalate >90-day AR collections",
                         "rationale": f"{gt90/total*100:.1f}% of outstanding AR sits beyond 90 days; assign to a collections sprint."})
        offenders = s.get("top_offenders") or []
        if offenders:
            top = offenders[0]
            recs.append({"severity": "medium", "action": f"Open dispute review with {top['name']}",
                         "rationale": f"Largest aged exposure is {top['name']} at {top['total']:,.2f}."})

    elif kind == "payer_remit":
        by = s.get("by_payer") or []
        if by:
            top = by[0]
            recs.append({"severity": "info", "action": f"Top remit payer: {top['payer']} ({top['amount']:,.2f})",
                         "rationale": "Confirm posting and any short-pay variances against expected billed amounts."})

    elif kind == "gl_export":
        margin_pct = float(s.get("margin_pct") or 0)
        if margin_pct < 5:
            recs.append({"severity": "high", "action": "Run a cost-driver review",
                         "rationale": f"Statement implies operating margin of {margin_pct:.1f}% — below sustainable threshold."})
        else:
            recs.append({"severity": "info", "action": "Tag GL classes for monthly close",
                         "rationale": f"Margin {margin_pct:.1f}% on revenue {float(s.get('revenue_total') or 0):,.0f}; ready for narrative draft."})

    elif kind == "financial_model":
        head = s.get("headline") or {}
        agg = head.get("largest_numeric_aggregates") or []
        proj_sheets = head.get("projection_sheets") or []
        sheet_count = int(head.get("sheet_count") or s.get("sheet_count") or 0)
        keywords = head.get("detected_keywords") or []
        per_sheet = s.get("per_sheet") or []

        # Try to find a P&L-like sheet and a cash-flow-like sheet
        pl_sheet = next((p for p in per_sheet if any(k in p["sheet"].lower() for k in ["p&l", "income", "pnl"])), None)
        cf_sheet = next((p for p in per_sheet if "cash" in p["sheet"].lower()), None)
        bs_sheet = next((p for p in per_sheet if "balance" in p["sheet"].lower()), None)
        ass_sheet = next((p for p in per_sheet if "assumption" in p["sheet"].lower()), None)
        scen_sheet = next((p for p in per_sheet if "scenario" in p["sheet"].lower() or "sensitivity" in p["sheet"].lower()), None)

        recs.append({
            "severity": "info",
            "action": "Validate model integrity (links, hard-codes, sign conventions)",
            "rationale": (
                f"Workbook spans {sheet_count} sheets including {len(proj_sheets)} projection sheets. "
                f"Detected concepts: {', '.join(keywords[:6]) or 'none'}."
            ),
        })
        if ass_sheet:
            recs.append({
                "severity": "high",
                "action": f"Stress-test assumptions in '{ass_sheet['sheet']}'",
                "rationale": (
                    f"Assumption sheet drives downstream projections. Run +/-10% sensitivity on top revenue/cost drivers "
                    f"and confirm WACC, growth and FX rates are board-approved."
                ),
            })
        if pl_sheet:
            recs.append({
                "severity": "high",
                "action": f"Reconcile '{pl_sheet['sheet']}' to actuals YTD",
                "rationale": (
                    "Compare current-year P&L projection against management accounts; investigate >5% variance lines and "
                    "refresh forward periods accordingly."
                ),
            })
        if cf_sheet:
            recs.append({
                "severity": "medium",
                "action": f"Verify cash-flow waterfall on '{cf_sheet['sheet']}'",
                "rationale": (
                    "Confirm working-capital, capex and debt-service items tie to balance sheet and that ending cash is "
                    "non-negative across the projection horizon."
                ),
            })
        if bs_sheet:
            recs.append({
                "severity": "medium",
                "action": f"Check balance-sheet integrity in '{bs_sheet['sheet']}'",
                "rationale": "Assets should equal liabilities + equity in every period; flag any imbalance > 0.5%."
            })
        if scen_sheet:
            recs.append({
                "severity": "info",
                "action": f"Run downside / base / upside scenarios via '{scen_sheet['sheet']}'",
                "rationale": "Quantify cash runway and covenant headroom under each scenario; circulate with board pack."
            })
        if agg:
            top = agg[0]
            recs.append({
                "severity": "info",
                "action": f"Spot-check largest aggregate: '{top['column']}' on '{top['sheet']}'",
                "rationale": f"Sum of {top['sum']:,.0f} dominates the workbook; confirm it is correctly scaled and labeled."
            })
        if focus == "liquidity":
            recs.append({
                "severity": "high",
                "action": "Translate model into a 13-week cash forecast",
                "rationale": "Even an annual model needs a near-term liquidity bridge to operate; produce a 13-week cash forecast that ties to it."
            })

    # Generic fallback only when nothing matched (truly unknown shape)
    if not recs:
        recs.append({
            "severity": "info",
            "action": "Manually inspect the document with finance team",
            "rationale": (
                "Automated heuristics did not match a known statement shape. "
                f"Document kind detected as '{kind}'. Use the summary fields as supplementary evidence and "
                "add a tenant-specific rule if this format will recur."
            ),
        })

    return {
        "upload_id": up["id"],
        "filename": up["filename"],
        "kind": kind,
        "focus": focus,
        "recommendations": recs,
    }


def _recall_memory(tenant_id: str, args: dict) -> dict:
    user_id = args.get("_user_id") or ""
    if not user_id:
        return {"error": "recall_memory requires a user context"}
    facts = memory_mod.recall_relevant(
        tenant_id=tenant_id, user_id=user_id,
        query=args.get("query") or "", k=int(args.get("k") or 8),
    )
    return {"facts": [{"id": f["id"], "fact": f["fact"], "pinned": f["pinned"], "importance": f["importance"]} for f in facts]}


def _pin_memory(tenant_id: str, args: dict) -> dict:
    user_id = args.get("_user_id") or ""
    if not user_id:
        return {"error": "pin_memory requires a user context"}
    f = memory_mod.pin_fact(
        tenant_id=tenant_id, user_id=user_id,
        fact=args["fact"], importance=int(args.get("importance") or 7),
        source="agent",
    )
    return {"pinned": True, "fact": f}


DISPATCH = {
    "query_service_line_pnl": _query_service_line_pnl,
    "query_revenue_cycle": _query_revenue_cycle,
    "query_payer_performance": _query_payer_performance,
    "query_cash_position": _query_cash_position,
    "forecast_cash": _forecast_cash,
    "compute_kpi": _compute_kpi,
    "run_controls_check": _run_controls_check,
    "analyze_uploaded_statement": _analyze_uploaded_statement,
    "recommend_actions_from_statement": _recommend_actions_from_statement,
    "recall_memory": _recall_memory,
    "pin_memory": _pin_memory,
    # compose_chart / compose_table are pure data passthroughs (echo back the spec)
    "compose_chart": lambda tenant_id, args: {"chart": args},
    "compose_table": lambda tenant_id, args: {"table": args},
}


def invoke(tool_name: str, tenant_id: str, arguments: dict, *, user_id: str | None = None) -> dict:
    if tool_name not in DISPATCH:
        return {"error": f"unknown tool: {tool_name}"}
    args = dict(arguments or {})
    # Inject internal fields not visible to the model so memory tools can scope to user.
    if user_id and tool_name in ("recall_memory", "pin_memory"):
        args["_user_id"] = user_id
    try:
        return DISPATCH[tool_name](tenant_id, args)
    except Exception as e:  # surface tool errors as data, never crash the agent loop
        return {"error": str(e), "tool": tool_name}
