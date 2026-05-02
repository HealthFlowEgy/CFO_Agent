import json
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.agents import stream_run
from app.audit import record as audit_record
from app.auth import (
    Session,
    current_session,
    issue_token,
    platform_admin_session,
    verify_password,
)
from app.config import settings
from app.db import get_db, init_db
from app.seed import seed_demo_data


app = FastAPI(title="HealthFlow CFO Copilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    seed_demo_data()


# ----------------- Health & meta -----------------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm_mode": settings.llm_mode,
            "models": {"conductor": settings.model_conductor,
                       "specialist": settings.model_specialist,
                       "haiku": settings.model_haiku}}


# ----------------- Auth -----------------

class LoginIn(BaseModel):
    email: str
    password: str
    tenant_id: Optional[str] = None


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    tenants: list[dict]
    active_tenant_id: str


@app.post("/api/auth/login", response_model=LoginOut)
def login(payload: LoginIn) -> LoginOut:
    with get_db() as conn:
        u = conn.execute(
            "SELECT id, email, name, locale, password_hash, is_platform_admin FROM users WHERE email = %s",
            (payload.email.lower(),),
        ).fetchone()
        if not u or not verify_password(payload.password, u["password_hash"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

        tenant_rows = conn.execute(
            """SELECT t.id, t.name, t.name_ar, t.currency, t.plan, tu.role
               FROM tenant_users tu
               JOIN tenants t ON t.id = tu.tenant_id
               WHERE tu.user_id = %s
               ORDER BY t.name""",
            (u["id"],),
        ).fetchall()
        if not tenant_rows:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "user has no tenants")

        tenants = [dict(r) for r in tenant_rows]
        active = payload.tenant_id or tenants[0]["id"]
        active_role = next((t["role"] for t in tenants if t["id"] == active), tenants[0]["role"])

    token = issue_token(u["id"], active, active_role)
    audit_record("auth.login", {"email": u["email"], "tenant_id": active},
                 tenant_id=active, user_id=u["id"])
    return LoginOut(
        access_token=token,
        user={"id": u["id"], "email": u["email"], "name": u["name"], "locale": u["locale"],
              "is_platform_admin": bool(u["is_platform_admin"])},
        tenants=tenants,
        active_tenant_id=active,
    )


@app.get("/api/auth/me")
def me(session: Session = Depends(current_session)) -> dict:
    with get_db() as conn:
        tenants = [dict(r) for r in conn.execute(
            """SELECT t.id, t.name, t.name_ar, t.currency, t.plan, tu.role
               FROM tenant_users tu JOIN tenants t ON t.id = tu.tenant_id
               WHERE tu.user_id = %s ORDER BY t.name""",
            (session.user_id,),
        ).fetchall()]
    return {
        "user": {"id": session.user_id, "email": session.email, "name": session.name,
                 "locale": session.locale, "role": session.role,
                 "is_platform_admin": session.is_platform_admin},
        "active_tenant_id": session.tenant_id,
        "tenants": tenants,
    }


@app.post("/api/auth/switch-tenant")
def switch_tenant(body: dict, session: Session = Depends(current_session)) -> dict:
    new_tid = body.get("tenant_id")
    if not new_tid:
        raise HTTPException(400, "tenant_id required")
    with get_db() as conn:
        row = conn.execute(
            "SELECT role FROM tenant_users WHERE user_id = %s AND tenant_id = %s",
            (session.user_id, new_tid),
        ).fetchone()
        if not row:
            raise HTTPException(403, "no access to tenant")
    token = issue_token(session.user_id, new_tid, row["role"])
    return {"access_token": token, "active_tenant_id": new_tid, "role": row["role"]}


# ----------------- Platform Super-Admin -----------------
#
# All endpoints in this block require is_platform_admin = TRUE on the user.
# These bypass tenant scoping by design — they exist to operate the platform.

def _aggregate_usage_from_audit(rows: list[dict]) -> dict:
    """Reduce audit_log payload_json rows into agent runs / tools / tokens."""
    runs = tools = total_tokens = 0
    for r in rows:
        try:
            p = json.loads(r["payload_json"])
        except Exception:
            continue
        runs += 1
        for sp in p.get("specialists", []):
            tools += len(sp.get("tools", []))
            usage = sp.get("usage") or {}
            total_tokens += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        syn = p.get("synthesis_usage") or {}
        total_tokens += int(syn.get("input_tokens", 0)) + int(syn.get("output_tokens", 0))
    return {"runs": runs, "tools": tools, "tokens": total_tokens}


@app.get("/api/admin/overview")
def admin_overview(_: Session = Depends(platform_admin_session)) -> dict:
    """System-wide KPIs for the super-admin dashboard."""
    with get_db() as conn:
        total_tenants = conn.execute("SELECT COUNT(*) AS n FROM tenants").fetchone()["n"]
        total_users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        total_conversations = conn.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]
        plan_dist_rows = conn.execute(
            "SELECT plan, COUNT(*) AS n FROM tenants GROUP BY plan"
        ).fetchall()
        # 30-day audit aggregates
        audit_rows = conn.execute(
            """SELECT payload_json FROM audit_log
               WHERE event = 'agent.run' AND created_at >= NOW() - INTERVAL '30 days'"""
        ).fetchall()
        # Today's audit aggregates
        today_rows = conn.execute(
            """SELECT payload_json FROM audit_log
               WHERE event = 'agent.run' AND created_at >= NOW() - INTERVAL '24 hours'"""
        ).fetchall()
        # Recent logins (24h)
        logins_24h = conn.execute(
            """SELECT COUNT(*) AS n FROM audit_log
               WHERE event = 'auth.login' AND created_at >= NOW() - INTERVAL '24 hours'"""
        ).fetchone()["n"]

    plan_dist = {r["plan"] or "unknown": r["n"] for r in plan_dist_rows}
    mrr = sum(PLANS.get(p, {}).get("price_usd_per_month", 0) * n for p, n in plan_dist.items())

    usage_30d = _aggregate_usage_from_audit(audit_rows)
    usage_24h = _aggregate_usage_from_audit(today_rows)

    return {
        "tenants_total": total_tenants,
        "users_total": total_users,
        "conversations_total": total_conversations,
        "logins_24h": logins_24h,
        "plan_distribution": plan_dist,
        "mrr_usd": mrr,
        "usage_30d": usage_30d,
        "usage_24h": usage_24h,
        "llm_mode": settings.llm_mode,
    }


@app.get("/api/admin/tenants")
def admin_tenants(_: Session = Depends(platform_admin_session)) -> dict:
    """Per-tenant metrics: plan, user count, conversations, last activity, MTD tokens."""
    with get_db() as conn:
        tenants = conn.execute(
            """SELECT t.id, t.name, t.name_ar, t.currency, t.plan, t.created_at,
                      COUNT(DISTINCT tu.user_id) AS user_count
               FROM tenants t
               LEFT JOIN tenant_users tu ON tu.tenant_id = t.id
               GROUP BY t.id, t.name, t.name_ar, t.currency, t.plan, t.created_at
               ORDER BY t.name""",
        ).fetchall()
        out = []
        for t in tenants:
            convs = conn.execute(
                "SELECT COUNT(*) AS n, MAX(created_at) AS last FROM conversations WHERE tenant_id = %s",
                (t["id"],),
            ).fetchone()
            audit_mtd = conn.execute(
                """SELECT payload_json FROM audit_log
                   WHERE tenant_id = %s AND event = 'agent.run'
                     AND to_char(created_at, 'YYYY-MM') = to_char(NOW(), 'YYYY-MM')""",
                (t["id"],),
            ).fetchall()
            usage = _aggregate_usage_from_audit(audit_mtd)
            plan = PLANS.get((t["plan"] or "").lower(), {})
            out.append({
                "id": t["id"],
                "name": t["name"],
                "name_ar": t["name_ar"],
                "currency": t["currency"],
                "plan": t["plan"],
                "plan_price_usd": plan.get("price_usd_per_month", 0),
                "user_count": int(t["user_count"] or 0),
                "conversation_count": int(convs["n"] or 0),
                "last_activity": convs["last"].isoformat() if convs["last"] else None,
                "created_at": t["created_at"].isoformat() if t["created_at"] else None,
                "tokens_mtd": usage["tokens"],
                "agent_runs_mtd": usage["runs"],
            })
    return {"tenants": out}


@app.get("/api/admin/users")
def admin_users(_: Session = Depends(platform_admin_session)) -> dict:
    """Cross-tenant user list with memberships."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT u.id, u.email, u.name, u.locale, u.is_platform_admin,
                      COALESCE(json_agg(json_build_object(
                          'tenant_id', tu.tenant_id, 'role', tu.role
                      )) FILTER (WHERE tu.tenant_id IS NOT NULL), '[]') AS memberships
               FROM users u
               LEFT JOIN tenant_users tu ON tu.user_id = u.id
               GROUP BY u.id, u.email, u.name, u.locale, u.is_platform_admin
               ORDER BY u.is_platform_admin DESC, u.name""",
        ).fetchall()
    return {"users": [dict(r) for r in rows]}


@app.get("/api/admin/audit")
def admin_audit(
    limit: int = 100,
    _: Session = Depends(platform_admin_session),
) -> dict:
    """Recent platform events across all tenants."""
    limit = max(1, min(limit, 500))
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, tenant_id, user_id, event, created_at, hash
               FROM audit_log
               ORDER BY id DESC
               LIMIT %s""",
            (limit,),
        ).fetchall()
    return {
        "events": [
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "user_id": r["user_id"],
                "event": r["event"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "hash_prefix": (r["hash"] or "")[:12],
            }
            for r in rows
        ]
    }


@app.get("/api/admin/anomalies")
def admin_anomalies(_: Session = Depends(platform_admin_session)) -> dict:
    """Lightweight signal panel: tenants near token-budget cap, failed logins, unused tenants."""
    with get_db() as conn:
        # Failed logins in last 24h (we don't currently log failures separately;
        # this surface is reserved — return 0 today, list is here for the dashboard schema).
        # Tenants with stale activity (no conversation in 14 days)
        stale = conn.execute(
            """SELECT t.id, t.name, MAX(c.created_at) AS last
               FROM tenants t
               LEFT JOIN conversations c ON c.tenant_id = t.id
               GROUP BY t.id, t.name
               HAVING MAX(c.created_at) IS NULL OR MAX(c.created_at) < NOW() - INTERVAL '14 days'""",
        ).fetchall()
        over_budget: list[dict] = []
        for t in conn.execute("SELECT id, name, plan FROM tenants").fetchall():
            audit_mtd = conn.execute(
                """SELECT payload_json FROM audit_log
                   WHERE tenant_id = %s AND event = 'agent.run'
                     AND to_char(created_at, 'YYYY-MM') = to_char(NOW(), 'YYYY-MM')""",
                (t["id"],),
            ).fetchall()
            usage = _aggregate_usage_from_audit(audit_mtd)
            plan = PLANS.get((t["plan"] or "").lower(), {})
            budget = plan.get("monthly_token_budget", 0) or 1
            pct = usage["tokens"] / budget * 100
            if pct >= 70:
                over_budget.append({
                    "tenant_id": t["id"],
                    "tenant_name": t["name"],
                    "tokens_pct": round(pct, 1),
                    "plan": t["plan"],
                })
    return {
        "stale_tenants": [
            {"tenant_id": s["id"], "tenant_name": s["name"],
             "last_activity": s["last"].isoformat() if s["last"] else None}
            for s in stale
        ],
        "tenants_near_budget": over_budget,
    }


# ----------------- KPIs / Dashboard -----------------

PLANS = {
    "starter": {
        "name": "Starter",
        "price_usd_per_month": 499,
        "monthly_token_budget": 2_000_000,
        "agents": ["profitability", "rcm"],
        "features": [
            "Conversational workspace (EN/AR)",
            "Service-line P&L, RCM, cash position tools",
            "Up to 5 finance users",
            "Email support",
        ],
    },
    "pro": {
        "name": "Pro",
        "price_usd_per_month": 1_499,
        "monthly_token_budget": 10_000_000,
        "agents": ["profitability", "rcm", "cost_ops", "liquidity"],
        "features": [
            "Everything in Starter",
            "Cost & Operations + Liquidity agents",
            "13-week cash forecasts with stress scenarios",
            "Up to 20 finance users",
            "Priority support · 99.9% SLA",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_usd_per_month": 4_999,
        "monthly_token_budget": 50_000_000,
        "agents": ["profitability", "rcm", "cost_ops", "liquidity", "compliance", "forecasting"],
        "features": [
            "Everything in Pro",
            "Compliance & Forecasting agents",
            "Egypt-resident deployment, BYOK encryption",
            "Unlimited users · dedicated CSM",
            "Custom controls + audit-ready evidence pipelines",
            "ISO 27001, SOC 2, PDPL alignment",
        ],
    },
}


@app.get("/api/billing/plans")
def billing_plans() -> dict:
    return {"plans": PLANS}


@app.get("/api/billing/usage")
def billing_usage(session: Session = Depends(current_session)) -> dict:
    """Pseudo-usage derived from audit log entries this calendar month."""
    from datetime import date
    month = date.today().strftime("%Y-%m")
    with get_db() as conn:
        rows = conn.execute(
            """SELECT payload_json FROM audit_log
               WHERE tenant_id = %s AND event = 'agent.run'
                 AND to_char(created_at, 'YYYY-MM') = %s""",
            (session.tenant_id, month),
        ).fetchall()
        plan_row = conn.execute(
            "SELECT plan FROM tenants WHERE id = %s", (session.tenant_id,),
        ).fetchone()
    plan_id = (plan_row["plan"] if plan_row else "pro").lower()
    plan = PLANS.get(plan_id, PLANS["pro"])

    total_tokens = 0
    runs = 0
    tools = 0
    for r in rows:
        try:
            p = json.loads(r["payload_json"])
        except Exception:
            continue
        runs += 1
        for sp in p.get("specialists", []):
            tools += len(sp.get("tools", []))
            usage = sp.get("usage") or {}
            total_tokens += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        syn = p.get("synthesis_usage") or {}
        total_tokens += int(syn.get("input_tokens", 0)) + int(syn.get("output_tokens", 0))

    pct = round(total_tokens / plan["monthly_token_budget"] * 100, 1) if plan["monthly_token_budget"] else 0.0
    return {
        "month": month,
        "plan_id": plan_id,
        "plan": plan,
        "tokens_used": total_tokens,
        "tokens_budget": plan["monthly_token_budget"],
        "tokens_pct": pct,
        "agent_runs": runs,
        "tool_calls": tools,
    }


@app.post("/api/billing/change-plan")
def billing_change_plan(body: dict, session: Session = Depends(current_session)) -> dict:
    target = (body.get("plan_id") or "").lower()
    if target not in PLANS:
        raise HTTPException(400, "unknown plan")
    if session.role not in ("cfo", "tenant.owner", "tenant.admin", "controller"):
        raise HTTPException(403, "only CFO / admin / controller may change plan")
    with get_db() as conn:
        conn.execute("UPDATE tenants SET plan = %s WHERE id = %s", (target, session.tenant_id))
    audit_record("billing.plan_changed", {"to": target}, tenant_id=session.tenant_id, user_id=session.user_id)
    return {"ok": True, "plan_id": target}


@app.get("/api/dashboard/summary")
def dashboard_summary(session: Session = Depends(current_session)) -> dict:
    from app.tools import invoke
    from datetime import date, timedelta
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=90)).replace(day=1)
    pnl = invoke("query_service_line_pnl", session.tenant_id,
                 {"period_start": start.isoformat(), "period_end": today.isoformat()})
    rcm = invoke("query_revenue_cycle", session.tenant_id,
                 {"as_of": today.isoformat(),
                  "kpis": ["days_in_ar", "denial_rate", "net_collection_rate", "aging_buckets"]})
    cash = invoke("query_cash_position", session.tenant_id, {"as_of": today.isoformat()})
    payers = invoke("query_payer_performance", session.tenant_id,
                    {"as_of": today.isoformat(), "trailing_months": 3})
    controls = invoke("run_controls_check", session.tenant_id,
                      {"rule_ids": ["CTRL-AR-001"], "as_of": today.isoformat()})
    return {
        "pnl": pnl,
        "revenue_cycle": rcm,
        "cash": cash,
        "payers": payers,
        "controls": controls,
    }


# ----------------- Conversations -----------------

class ConverseIn(BaseModel):
    conversation_id: Optional[str] = None
    message: str


@app.get("/api/conversations")
def list_conversations(session: Session = Depends(current_session)) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, title, created_at FROM conversations
               WHERE tenant_id = %s AND user_id = %s
               ORDER BY created_at DESC LIMIT 50""",
            (session.tenant_id, session.user_id),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str, session: Session = Depends(current_session)) -> dict:
    with get_db() as conn:
        c = conn.execute(
            "SELECT id, title, created_at FROM conversations WHERE id = %s AND tenant_id = %s AND user_id = %s",
            (conv_id, session.tenant_id, session.user_id),
        ).fetchone()
        if not c:
            raise HTTPException(404, "not found")
        msgs = conn.execute(
            "SELECT id, role, content_json, created_at FROM messages WHERE conversation_id = %s ORDER BY created_at",
            (conv_id,),
        ).fetchall()
    return {
        "conversation": dict(c),
        "messages": [
            {"id": m["id"], "role": m["role"], "content": json.loads(m["content_json"]),
             "created_at": m["created_at"]}
            for m in msgs
        ],
    }


def _ensure_conversation(conn, session: Session, conv_id: Optional[str], first_message: str) -> str:
    if conv_id:
        c = conn.execute(
            "SELECT id FROM conversations WHERE id = %s AND tenant_id = %s AND user_id = %s",
            (conv_id, session.tenant_id, session.user_id),
        ).fetchone()
        if not c:
            raise HTTPException(404, "conversation not found")
        return conv_id
    new_id = "conv_" + uuid.uuid4().hex[:12]
    title = (first_message or "New conversation").strip()[:60]
    conn.execute(
        "INSERT INTO conversations (id, tenant_id, user_id, title) VALUES (%s, %s, %s, %s)",
        (new_id, session.tenant_id, session.user_id, title),
    )
    return new_id


def _persist_message(conn, conv_id: str, role: str, content: dict) -> None:
    mid = "msg_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO messages (id, conversation_id, role, content_json) VALUES (%s, %s, %s, %s)",
        (mid, conv_id, role, json.dumps(content, default=str)),
    )


@app.post("/api/converse/stream")
async def converse_stream(payload: ConverseIn, session: Session = Depends(current_session)):
    # Ensure conversation + user message persisted before streaming starts
    with get_db() as conn:
        conv_id = _ensure_conversation(conn, session, payload.conversation_id, payload.message)
        _persist_message(conn, conv_id, "user", {"text": payload.message})
        tenant_row = conn.execute(
            "SELECT id, name, name_ar, currency, plan FROM tenants WHERE id = %s",
            (session.tenant_id,),
        ).fetchone()
        tenant = dict(tenant_row)

    async def event_generator():
        # Open with conversation id so the UI can pin the URL
        yield {"event": "open", "data": json.dumps({"conversation_id": conv_id})}
        final_payload: Optional[dict] = None
        async for evt in stream_run(
            user_query=payload.message, tenant=tenant, user_id=session.user_id
        ):
            yield {"event": evt["event"], "data": json.dumps(evt["data"], default=str)}
            if evt["event"] == "final":
                final_payload = evt["data"]
        # persist assistant message
        if final_payload is not None:
            with get_db() as conn:
                _persist_message(conn, conv_id, "assistant", final_payload)

    return EventSourceResponse(event_generator())
