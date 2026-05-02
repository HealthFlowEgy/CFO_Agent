# HealthFlow CFO Copilot — V0

AI-powered, multi-tenant financial intelligence platform for hospital CFOs.
Multi-agent reasoning powered by **Anthropic Claude** (Opus + Sonnet) with
deterministic tool use, tenant-scoped data isolation, and citation-backed
answers.

This repository implements a **vertical V0 slice** of the SRS
(`docs/SRS.md`):

- **Backend**: FastAPI service combining BFF + agent orchestrator + tool server.
  - Conductor agent (Opus) + two specialist agents (Profitability, RCM).
  - Deterministic Tool Server with 9 V0 tools (P&L, RCM, cash, forecast, controls, KPIs, charts/tables).
  - JWT auth, multi-tenant, append-only hash-chained audit log.
  - SSE streaming of conversation events (planning → specialist → synthesis).
  - Anthropic Messages API with tool use, prompt caching, and mock fallback.
- **Frontend**: Next.js 15 + Tailwind, distinctive dark glass UI.
  - Workspace (split layout: conversation + live evidence pane).
  - CFO dashboard with KPIs, service-line P&L bars, payer donut, AR aging.
  - Library, Settings, EN/AR with RTL parity.
- **Data**: SQLite seed for two demo hospital tenants (Cairo Specialty,
  Alexandria Medical Center) with 12 months of synthetic GL, 6 months of
  payer claims, 13 weeks of cash balances.

V0 explicitly defers Keycloak SSO, Kafka, Temporal, ClickHouse, Qdrant RAG,
dbt ingestion, BYOK encryption — see `docs/SRS.md` Appendix A for the deferred
list.

---

## Quick start (Docker Compose)

```bash
# 1. Configure your Anthropic key
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 2. Bring everything up
docker compose up --build
```

The web app will be available at **http://localhost:3000** and the API at
**http://localhost:8000**. Both auto-reload on source changes.

If `ANTHROPIC_API_KEY` is empty, the system runs in **mock mode** —
deterministic stub LLM responses, the full UI works end-to-end without an API
key.

### Demo accounts

| Email                                  | Password   | Tenants                  | Locale |
|----------------------------------------|------------|--------------------------|--------|
| amr.cfo@healthflow.demo                | demo1234   | Cairo + Alex (CFO)       | EN     |
| layla.controller@healthflow.demo       | demo1234   | Cairo (Controller)       | AR     |
| omar.analyst@healthflow.demo           | demo1234   | Alex (Analyst)           | EN     |

### Try it

In the workspace, ask:
- _"What's our Days in AR?"_
- _"Show service-line margins for the last 90 days."_
- _"Which payer is hurting us most?"_
- _"Forecast cash for 13 weeks under the UHI 30-day delay scenario."_
- _"Run controls check and list any open exceptions."_

You'll see the **plan** (which specialist agents the Conductor delegated to),
each specialist's **tool calls**, and the synthesized final answer with
citations.

---

## Deploy to DigitalOcean App Platform

A ready-to-import App Platform spec lives at `.do/app.yaml`. It provisions
both components (web + api), wires their URLs and CORS via DO variable
substitution, and configures health checks.

**One-click deploy:**

[![Deploy to DigitalOcean](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/healthflowegy/cfo_agent/tree/claude/healthflow-cfo-srs-4WILe)

After import, set the `ANTHROPIC_API_KEY` secret in the console
(Apps → cfo-copilot → **api** component → Settings → Environment).
Without it the system runs in mock mode (still demoable end-to-end).

**Or via doctl:**

```bash
doctl apps create --spec .do/app.yaml
# then set the secret:
doctl apps update <APP_ID> --spec - <<< "$(cat .do/app.yaml)"
```

V0 uses ephemeral SQLite (`/tmp/cfo.db`) — re-seeds on every container
restart. For production, swap to DigitalOcean Managed Postgres and update
`apps/api/app/db.py` accordingly.

---

## Local dev (no Docker)

### Backend

```bash
cd apps/api
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export DB_PATH=./local.db
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd apps/web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000.

---

## Architecture (V0)

```
Browser (Next.js 15)
   │  fetch / SSE
   ▼
FastAPI BFF (apps/api)
   ├── auth (JWT, multi-tenant)
   ├── orchestrator
   │     ├── Conductor      (Opus, planning + synthesis)
   │     ├── Profitability  (Sonnet, P&L tools)
   │     └── RCM            (Sonnet, RCM + cash + forecast tools)
   ├── tool server          (deterministic, tenant-scoped)
   └── audit log            (hash-chained, append-only)
        │
        ▼
   SQLite (per-tenant data; schema-per-tenant in V1+)
```

### Anthropic API usage (per SRS §6)

- **Messages API + tool use**: every numeric claim originates from a tool
  result; the model never computes numbers.
- **Prompt caching**: agent system prompts and tenant context blocks are
  cached via `cache_control: ephemeral`.
- **Tool use loop**: `tool_use` → server invokes tool → `tool_result` →
  model emits final text. Loop bounded at 4 turns.
- **Multi-agent topology**: Conductor (Opus) plans → fan-out to specialists
  (Sonnet) → synthesis (Opus).
- **Mock fallback**: `app/llm.py::MockProvider` simulates the loop so the
  whole UI works end-to-end without a key.

---

## Repo layout

```
.
├── docs/
│   └── SRS.md
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── app/
│   │   │   ├── agents.py    # orchestrator
│   │   │   ├── auth.py      # JWT + tenant scoping
│   │   │   ├── audit.py     # hash-chained audit log
│   │   │   ├── config.py
│   │   │   ├── db.py        # sqlite + schema
│   │   │   ├── llm.py       # AnthropicProvider + MockProvider
│   │   │   ├── main.py      # routes
│   │   │   ├── prompts.py   # system prompts (SRS §6.6)
│   │   │   ├── seed.py
│   │   │   └── tools.py     # deterministic tool server
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── web/                 # Next.js 15 frontend
│       ├── src/
│       │   ├── app/
│       │   │   ├── login/
│       │   │   ├── workspace/
│       │   │   ├── library/
│       │   │   ├── settings/
│       │   │   ├── globals.css
│       │   │   ├── layout.tsx
│       │   │   └── page.tsx (dashboard)
│       │   ├── components/
│       │   └── lib/
│       └── ...
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Roadmap to V1

- Replace SQLite with PostgreSQL (schema-per-tenant) + ClickHouse for
  analytical workloads.
- Keycloak SSO with MFA; replace mock JWT.
- Add 4 more specialist agents (Cost & Operations, Liquidity-deep, Compliance,
  Forecasting).
- Connect ingestion connectors: HIS / FHIR, ERP, payroll, banking ISO 20022.
- Qdrant RAG over uploaded contracts/policies + Anthropic Citations.
- Stripe billing for subscription tiers (Starter / Pro / Enterprise).
- Move audit + telemetry to OpenTelemetry → Tempo / Loki / Mimir.
- AI eval harness with reference Q/A sets + adversarial suite.

See `docs/SRS.md` for the full specification.
