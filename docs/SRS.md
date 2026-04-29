# Software Requirements Specification (SRS)

## HealthFlow CFO Copilot
### AI-Powered Financial Intelligence Platform — Anthropic-Backed Multi-Agent Architecture

---

**Document Reference:** HF-CFO-SRS-v1.0
**Status:** Draft for Engineering & Architecture Review
**Date:** April 2026
**Companion Document:** HF-CFO-BRD-v1.0
**Prepared by:** HealthFlow Group — Engineering & Architecture
**Owner:** CTO / Head of AI
**Classification:** Confidential — Internal Engineering

---

## Document Control

| Version | Date | Author | Description |
|---|---|---|---|
| 0.1 | Apr 2026 | Architecture | Initial outline |
| 1.0 | Apr 2026 | Architecture | First complete draft for review |

**Distribution:** CTO, Head of AI, Lead Architect, Engineering Leads (Backend, Frontend, Data, DevOps, Security), Product, QA Lead, Compliance.

---

## Table of Contents

1. Introduction
2. Overall Description
3. System Architecture
4. External Interface Requirements
5. Detailed Functional Requirements
6. **Anthropic API Backend Specifications**
7. Data Architecture & Storage
8. Security Architecture
9. Non-Functional Requirements
10. Deployment & Infrastructure
11. Observability & Operations
12. Testing & Quality Requirements
13. Acceptance Criteria
14. Appendices (code samples, prompts, schemas)

---

## 1. Introduction

### 1.1 Purpose
This document specifies the software requirements for the HealthFlow CFO Copilot platform — a multi-tenant SaaS system that uses Anthropic's Claude API as the reasoning backbone for a team of specialized AI agents serving hospital chief financial officers. It is the engineering counterpart to the BRD (HF-CFO-BRD-v1.0) and is the source of truth for architectural and implementation decisions.

### 1.2 Scope
The system covered by this SRS includes:
- Multi-tenant web application (CFO Copilot Workspace).
- Backend services for ingestion, transformation, analytics, and AI orchestration.
- A six-agent reasoning layer powered by the Anthropic Messages API with tool use.
- Connectors to HIS, ERP, payroll, pharmacy, banking, and HealthFlow rails.
- Observability, security, compliance, and DevOps infrastructure.

### 1.3 Definitions, Acronyms, Abbreviations

| Term | Definition |
|---|---|
| Conductor | Orchestrating LLM agent that routes and assembles answers |
| Specialist Agent | Domain-bounded LLM agent (e.g., Profitability) |
| Tool | Structured deterministic function callable by an agent |
| Tool Use | Anthropic API capability allowing the model to call defined tools |
| Prompt Cache | Anthropic feature reducing cost by caching reused prompt prefixes |
| Batch API | Anthropic asynchronous API with 50% discount and 24-hour SLA |
| Extended Thinking | Anthropic feature where models reason for longer before responding |
| RAG | Retrieval-Augmented Generation |
| Tenant | A hospital customer with isolated data and configuration |
| HFCX | HealthFlow Claims Exchange |
| NDP | National Digital Prescription platform |
| HCP Registry | Healthcare Professional Registry |
| PDPL | Egyptian Personal Data Protection Law (151/2020) |
| RTO / RPO | Recovery Time / Point Objective |
| MTok | Million tokens (Anthropic billing unit) |
| MCP | Model Context Protocol |

### 1.4 References
- HF-CFO-BRD-v1.0 — Business Requirements Document
- Anthropic API Documentation (`https://docs.claude.com`)
- Anthropic Pricing Reference (April 2026)
- IEEE/ISO/IEC 29148:2018 — Systems and software engineering — Life cycle processes — Requirements engineering
- COSO Internal Control – Integrated Framework (2013)
- ISO/IEC 27001:2022, ISO/IEC 27701:2019
- Egyptian PDPL (Law 151/2020)
- HL7 FHIR R4

### 1.5 Document Overview
Sections 2–4 establish architectural context and external interfaces. Section 5 catalogs functional requirements at module level. **Section 6 is the technical heart of this SRS**, specifying exactly how the Anthropic API is used. Sections 7–11 cover data, security, NFRs, deployment, and operations. Section 12 defines testing requirements including AI evaluation. Appendices include code samples, prompt patterns, and tool schemas.

---

## 2. Overall Description

### 2.1 Product Perspective
The Copilot is a new product within the HealthFlow Group ecosystem. It is delivered as a multi-tenant SaaS on cloud infrastructure with Egypt-resident deployment options, sharing identity (Keycloak), notification (WasslChat), and rails (HFCX, HealthPay, NDP, HCP Registry) with other HealthFlow products.

### 2.2 Product Functions (Summary)
- Ingest tenant operational and financial data via connectors.
- Transform raw data into a canonical healthcare-finance data model.
- Serve a conversational workspace where users query a six-agent system.
- Power six specialist agents and one Conductor agent through Anthropic's Claude API.
- Execute deterministic analytical tools called by the agents.
- Continuously monitor controls and detect anomalies.
- Generate dashboards, board packs, audit-ready evidence, and notifications.

### 2.3 User Classes
Defined fully in BRD §6. Engineering treats these as RBAC roles: `tenant.owner`, `tenant.admin`, `cfo`, `controller`, `analyst`, `auditor.internal`, `auditor.external`, `viewer`, `service.implementation`, `platform.support`.

### 2.4 Operating Environment
- **Client:** evergreen browsers (Chrome, Edge, Safari, Firefox) on desktop and tablet; PWA-enabled mobile experience.
- **Server:** Linux containers (Ubuntu 24.04 base) on Kubernetes.
- **Cloud:** primary on DigitalOcean (HealthFlow standard) with optional AWS/Azure via Terraform abstractions; Egypt-resident region for regulated tenants.
- **Database:** PostgreSQL 16 (managed) for OLTP; ClickHouse for analytical workloads; Redis 7 for cache/sessions; OpenSearch for log search; Qdrant for vector storage.
- **AI Backend:** Anthropic API (primary), with provider abstraction layer to allow future providers as backups for non-AI-critical paths.

### 2.5 Design and Implementation Constraints
- **Bilingual mandatory.** Arabic (RTL) and English (LTR) parity in UI, agent responses, and exported documents.
- **Egypt data residency** for tenant patient and salary data unless explicitly waived in writing.
- **Anthropic API is the sole LLM provider** for V1; architecture must abstract the provider so a swap is possible without rewriting agents.
- **No PHI in LLM prompts.** Patient identifiers tokenized before any data leaves the Tool layer to the Anthropic API.
- **Numeric outputs must be deterministic.** LLMs may not perform arithmetic; all math via tools.
- **Audit log is append-only and cryptographically chained.**
- **Open-source preference** consistent with HealthFlow standard stacks (NestJS, Next.js, Python FastAPI, Postgres, Kafka).

### 2.6 Assumptions and Dependencies
- Anthropic API availability and continued support of tool use, prompt caching, batch API, citations, and 1M-token context window on Opus 4.7, Opus 4.6, and Sonnet 4.6.
- HealthFlow Identity, HFCX, HealthPay, NDP, and HCP Registry remain available with current contracts.
- Tenant willingness to permit secure read access to source systems.
- Cloud provider provides Egypt-resident regions or compliant equivalents.

---

## 3. System Architecture

(See full SRS in conversation source for diagrams and exhaustive detail; this file preserves the canonical text for the engineering team.)

### 3.3 Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 19, TypeScript, Tailwind, shadcn/ui |
| BFF | NestJS / FastAPI (V0 uses FastAPI) |
| Agent Services | Python 3.12 + FastAPI + Anthropic Python SDK |
| Analytical Tools | Python 3.12 + DuckDB / SQLite (V0) / ClickHouse (V1+) |
| OLTP | PostgreSQL 16 |
| Vector DB | Qdrant |
| Identity | Keycloak (V1+); JWT mock for V0 |

### 3.4 Multi-Tenant Isolation

- Tenant ID propagated as signed claim; rejected at gateway if missing.
- Schema-per-tenant in OLTP, collection-per-tenant in vectors, prefix-per-tenant in object storage.
- Agent isolation: every Anthropic API call carries tenant-scoped system prompt fragment; tools query only the caller's tenant.

---

## 6. Anthropic API Backend Specifications

### 6.1 Architectural Principles for AI Calls
- **AI-1. Tool-use over numeric reasoning.** Models do not compute financial numbers — tools do.
- **AI-2. Structured I/O.** Tool-call → tool-result → final-answer.
- **AI-3. Tenant isolation at the prompt boundary.**
- **AI-4. Determinism where it matters.** `temperature=0` for reasoning.
- **AI-5. Provenance is mandatory.** Every numeric claim cites a tool result.
- **AI-6. Fail closed.** Tool failure surfaces; never approximated.
- **AI-7. Cost is a first-class metric.** Token + USD logged per call.

### 6.2 Model Selection Matrix

| Use Case | Model |
|---|---|
| Conductor planning, synthesis | `claude-opus-4-7` |
| Specialist agents | `claude-sonnet-4-6` |
| Auxiliary (mapping, classification, translation) | `claude-haiku-4-5` |
| Nightly bulk work | Same models via Batch API |

### 6.3 Multi-Agent Topology

User → Conductor (Opus 4.7) → fan-out to specialists (Sonnet 4.6) → tools → canonical data.

V0 specialists: **Profitability**, **Revenue Cycle (RCM)**.
V1 adds: Cost & Operations, Liquidity, Compliance, Forecasting.

### 6.4 Tool Catalog (V0 subset)

- `query_service_line_pnl`
- `query_revenue_cycle`
- `query_cash_position`
- `query_payer_performance`
- `forecast_cash`
- `run_controls_check`
- `compose_chart`
- `compose_table`

### 6.5 Anthropic API Usage Patterns

#### 6.5.1 Messages API + Tool Use
Standard tool-use loop: model emits `tool_use` blocks → server invokes tools with tenant-scoped context → results returned as `tool_result` → model emits final text.

#### 6.5.2 Streaming
SSE from agent service → BFF → browser. Tool-use deltas surfaced in UI as "Querying GL…" affordances.

#### 6.5.3 Prompt Caching
- System instructions per agent: ~4–8K tokens, cached with `cache_control: ephemeral`.
- Tool registry: cached.
- Tenant context (CoA, fiscal calendar, payer master excerpt): cached.
- Cache hit-rate target ≥ 70%.

#### 6.5.4 Batch API
Nightly jobs for bulk anomaly explanation, monthly close narrative drafting, evidence summarization. 50% discount, 24h SLA.

#### 6.5.5 Files API
For QA over entire contracts/audits without re-chunking.

#### 6.5.6 Citations
Inline citation pills on every numeric claim, sourced from tool results.

#### 6.5.7 Extended Thinking
Conductor enables thinking for multi-agent plans, ≥5-variable scenarios, capital decisions. 16K thinking-token cap per request.

### 6.10 Privacy Controls at the API Boundary
- PHI tokenization before any data leaves the Tool layer.
- Salary aggregates only (≥5 employees per group).
- Tenant opt-out flag disables training-data eligibility.
- `metadata.user_id` set to tenant-scoped pseudonym.

---

## 9. Non-Functional Requirements

- P95 dashboard load ≤ 3 s
- P95 single-agent conversation ≤ 8 s
- P95 multi-agent ≤ 20 s (excl. extended thinking)
- 99.9% uptime; RTO ≤ 4h; RPO ≤ 15min
- AR/EN parity in UI, agent responses, exports
- ISO 27001, SOC 2 Type II, ISO 27701, PDPL alignment

---

## 12. Testing & Quality Requirements

- Unit ≥ 80% coverage
- AI Eval Harness: ≥200 reference Q/A per agent, gating on correctness/citation/tool-call/refusal/latency/cost
- Adversarial suite: prompt injection, cross-tenant probes, jailbreaks
- Promotion gate: no metric regresses by >2%, 0 adversarial violations

---

## Appendix A — V0 Implementation Notes

This repository implements a V0 vertical slice of the SRS:

- FastAPI backend: auth (JWT), tenancy, agent orchestrator (Conductor + Profitability + RCM), tool server, SSE streaming.
- Next.js 15 frontend: workspace (conversational), dashboards (KPIs), library (saved insights), settings; EN/AR with RTL.
- Synthetic seed data (SQLite) for two demo tenants: Cairo Specialty Hospital, Alexandria Medical Center.
- Anthropic Python SDK with mock fallback when `ANTHROPIC_API_KEY` is not set.
- Docker Compose for end-to-end run.

V0 deliberately defers: Keycloak SSO, Kafka/Redpanda, Temporal, ClickHouse, Qdrant RAG, dbt ingestion, BYOK encryption, SOC2 evidence pipelines.

---

**End of Document**
