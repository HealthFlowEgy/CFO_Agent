"""Agent orchestrator (SRS §6.3).

Conductor (Opus) plans → fan-out to specialists (Sonnet) → tools → synthesis.
Streams progress events via the `stream_run` async generator (SSE-friendly).

This revision adds:
- Date grounding via `runtime_context_block()` (today + seeded data window).
- Per-conversation memory: prior turns + rolling summary fed back into prompts.
- Cross-conversation memory: pinned facts recalled per user × tenant.
- Upload context: known upload_ids surfaced so specialists can call
  `analyze_uploaded_statement` and `recommend_actions_from_statement`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from app.audit import record as audit_record
from app.config import settings
from app.llm import FallbackProvider, LLMProvider, get_llm
from app.prompts import (
    CONDUCTOR_PLANNING_SYSTEM,
    CONDUCTOR_SYNTHESIS_SYSTEM,
    PROMPT_VERSION,
    SPECIALIST_REGISTRY,
    runtime_context_block,
    tenant_context_block,
)
from app.tools import invoke as tool_invoke, schemas_for
from app import memory as memory_mod
from app import uploads as uploads_mod


def _cached(text: str) -> dict:
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}


@dataclass
class AgentRun:
    agent: str
    answer: str = ""
    tools_used: list[str] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


def _extract_text(content: list[dict]) -> str:
    return "".join(b.get("text", "") for b in content if b.get("type") == "text")


def _build_context(
    *,
    prior_turns: list[dict] | None,
    conversation_summary: Optional[str],
    memory_facts: list[dict] | None,
    upload_context: list[dict] | None,
) -> str:
    blocks: list[str] = []
    if conversation_summary:
        blocks.append(f"CONVERSATION SUMMARY SO FAR\n{conversation_summary}")
    if prior_turns:
        blocks.append(
            "RECENT TURNS\n" + "\n".join(f"{t['role'].upper()}: {t['text']}" for t in prior_turns[-6:])
        )
    if memory_facts:
        blocks.append(
            "PINNED / RECALLED FACTS (cross-conversation memory)\n"
            + "\n".join(f"- {f['fact']}" for f in memory_facts[:8])
        )
    if upload_context:
        blocks.append(
            "UPLOADED FILES AVAILABLE TO YOU "
            "(call analyze_uploaded_statement(upload_id) to read them)\n"
            + "\n".join(
                f"- upload_id={u['id']} filename={u['filename']} kind={u.get('kind') or 'generic'}"
                for u in upload_context
            )
        )
    return "\n\n".join(blocks)


def _run_specialist(
    *, llm: LLMProvider, agent: str, sub_query: str, tenant: dict, user_id: str,
    prior_turns: list[dict] | None = None, conversation_summary: Optional[str] = None,
    memory_facts: list[dict] | None = None, upload_context: list[dict] | None = None,
) -> AgentRun:
    cfg = SPECIALIST_REGISTRY[agent]
    tools = schemas_for(cfg["tools"])

    ctx = _build_context(
        prior_turns=prior_turns,
        conversation_summary=conversation_summary,
        memory_facts=memory_facts,
        upload_context=upload_context,
    )
    user_payload = (ctx + "\n\nCURRENT QUESTION\n" + sub_query) if ctx else sub_query

    messages: list[dict] = [{"role": "user", "content": user_payload}]
    run = AgentRun(agent=agent)

    # Bounded tool-use loop (max 4 turns to prevent runaway)
    for _ in range(4):
        resp = llm.messages_create(
            model=settings.model_specialist,
            max_tokens=2048,
            temperature=0,
            system=[
                _cached(cfg["system"]),
                _cached(tenant_context_block(tenant)),
                _cached(runtime_context_block()),
            ],
            tools=tools,
            messages=messages,
            metadata={"user_id": f"{tenant['id']}:{user_id}"},
        )
        # accumulate usage
        for k, v in resp.usage.items():
            if isinstance(v, (int, float)):
                run.usage[k] = run.usage.get(k, 0) + int(v)

        if resp.stop_reason != "tool_use":
            run.answer = _extract_text(resp.content)
            return run

        # collect tool_use blocks; execute each tool
        tool_uses = [b for b in resp.content if b.get("type") == "tool_use"]
        tool_results_msg: list[dict] = []
        for tu in tool_uses:
            run.tools_used.append(tu["name"])
            result = tool_invoke(tu["name"], tenant["id"], tu.get("input") or {}, user_id=user_id)
            run.tool_results.append({"tool": tu["name"], "result": result})
            tool_results_msg.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": json.dumps(result, default=str),
                "is_error": "error" in result,
            })

        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": tool_results_msg})

    if not run.answer:
        run.answer = "I gathered tool results but couldn't finalize a narrative within the loop budget."
    return run


def _conductor_plan(
    llm: LLMProvider, user_query: str, tenant: dict, user_id: str,
    *, prior_turns: list[dict] | None = None, conversation_summary: Optional[str] = None,
    memory_facts: list[dict] | None = None, upload_context: list[dict] | None = None,
) -> dict:
    ctx = _build_context(
        prior_turns=prior_turns,
        conversation_summary=conversation_summary,
        memory_facts=memory_facts,
        upload_context=upload_context,
    )
    payload = (ctx + "\n\nUSER QUESTION\n" + user_query) if ctx else user_query

    resp = llm.messages_create(
        model=settings.model_conductor,
        max_tokens=1024,
        temperature=0,
        system=[_cached(CONDUCTOR_PLANNING_SYSTEM), _cached(runtime_context_block())],
        messages=[{"role": "user", "content": payload}],
        metadata={"user_id": f"{tenant['id']}:{user_id}"},
    )
    text = _extract_text(resp.content).strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except Exception:
        return {"intent": "Answer the CFO's question.",
                "subtasks": [{"agent": "rcm", "sub_query": user_query}]}


def _conductor_synthesize(
    llm: LLMProvider, user_query: str, runs: list[AgentRun], tenant: dict, user_id: str,
) -> tuple[str, dict[str, int]]:
    findings = {
        r.agent: {"answer": r.answer, "tools_used": list(dict.fromkeys(r.tools_used))}
        for r in runs
    }
    payload = {"user_query": user_query, "specialist_findings": findings}
    resp = llm.messages_create(
        model=settings.model_conductor,
        max_tokens=2048,
        temperature=0.2,
        system=[_cached(CONDUCTOR_SYNTHESIS_SYSTEM), _cached(runtime_context_block())],
        messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
        metadata={"user_id": f"{tenant['id']}:{user_id}"},
    )
    text = _extract_text(resp.content).strip()
    return text, resp.usage


def _summarize_for_memory(
    llm: LLMProvider, *, prior_summary: Optional[str], user_query: str, assistant_answer: str,
    tenant: dict, user_id: str,
) -> str:
    """Refresh the rolling conversation summary using a small/cheap model."""
    sys = (
        "You maintain a rolling, brand-neutral summary of a CFO copilot conversation. "
        "Output 4-8 bullet points capturing decisions, key numbers (with units), entities "
        "(payers, accounts, service lines), and unresolved follow-ups. No preamble, no apology. "
        "If a prior summary is provided, MERGE it with the new turn instead of restarting."
    )
    payload = {
        "prior_summary": prior_summary or "",
        "new_user_question": user_query,
        "new_assistant_answer": assistant_answer,
    }
    resp = llm.messages_create(
        model=settings.model_haiku or settings.model_specialist,
        max_tokens=512,
        temperature=0,
        system=[_cached(sys)],
        messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
        metadata={"user_id": f"{tenant['id']}:{user_id}"},
    )
    return _extract_text(resp.content).strip()


async def stream_run(
    *, user_query: str, tenant: dict, user_id: str,
    conversation_id: Optional[str] = None, upload_ids: Optional[list[str]] = None,
) -> AsyncIterator[dict]:
    """Yield SSE-friendly event dicts as the conductor + specialists run."""
    llm = get_llm()

    # Pull memory + recent turns + uploads up front
    prior_turns = memory_mod.recent_turns(conversation_id, limit_turns=6) if conversation_id else []
    conv_summary = memory_mod.get_summary(conversation_id) if conversation_id else None
    facts = memory_mod.recall_relevant(
        tenant_id=tenant["id"], user_id=user_id, query=user_query, k=8
    )
    upload_ctx: list[dict] = []
    for uid in (upload_ids or []):
        u = uploads_mod.get_upload(tenant["id"], uid)
        if u:
            upload_ctx.append({"id": u["id"], "filename": u["filename"], "kind": u.get("kind")})

    yield {
        "event": "status",
        "data": {
            "phase": "planning",
            "model": settings.model_conductor,
            "llm_mode": settings.llm_mode,
            "memory": {
                "facts_recalled": len(facts),
                "prior_turns": len(prior_turns),
                "uploads_referenced": len(upload_ctx),
                "has_summary": bool(conv_summary),
            },
        },
    }

    plan = _conductor_plan(
        llm, user_query, tenant, user_id,
        prior_turns=prior_turns, conversation_summary=conv_summary,
        memory_facts=facts, upload_context=upload_ctx,
    )
    if isinstance(llm, FallbackProvider) and llm.last_error:
        yield {"event": "warning",
               "data": {"message": f"AI provider unavailable, using mock fallback: {llm.last_error}"}}
    yield {"event": "plan", "data": plan}

    subtasks: list[dict] = plan.get("subtasks") or []
    runs: list[AgentRun] = []

    if not subtasks:
        text = ("Hi! I'm your HealthFlow CFO Copilot. Try: "
                "'What's our Days in AR?', 'Show service-line margins last quarter', "
                "'Forecast cash for 13 weeks', or upload a bank statement and ask me to analyze it.")
        yield {"event": "final", "data": {
            "answer": text, "plan": plan, "specialists": [], "prompt_version": PROMPT_VERSION,
            "memory": {"facts_used": [], "summary_pre": conv_summary,
                        "prior_turn_count": len(prior_turns),
                        "uploads_referenced": [u["id"] for u in upload_ctx]},
        }}
        return

    for st in subtasks:
        agent = st.get("agent")
        if agent not in SPECIALIST_REGISTRY:
            continue
        yield {"event": "status", "data": {"phase": "specialist_start", "agent": agent}}
        run = _run_specialist(
            llm=llm, agent=agent, sub_query=st["sub_query"], tenant=tenant, user_id=user_id,
            prior_turns=prior_turns, conversation_summary=conv_summary,
            memory_facts=facts, upload_context=upload_ctx,
        )
        runs.append(run)
        yield {
            "event": "specialist_result",
            "data": {
                "agent": agent,
                "answer": run.answer,
                "tools_used": list(dict.fromkeys(run.tools_used)),
                "tool_results": run.tool_results,
                "usage": run.usage,
            },
        }

    yield {"event": "status", "data": {"phase": "synthesis"}}
    final, syn_usage = _conductor_synthesize(llm, user_query, runs, tenant, user_id)

    audit_record(
        "agent.run",
        {
            "user_query": user_query,
            "plan": plan,
            "specialists": [
                {"agent": r.agent, "tools": list(dict.fromkeys(r.tools_used)), "usage": r.usage}
                for r in runs
            ],
            "synthesis_usage": syn_usage,
            "prompt_version": PROMPT_VERSION,
            "uploads_referenced": [u["id"] for u in upload_ctx],
        },
        tenant_id=tenant["id"],
        user_id=user_id,
    )

    # Refresh the rolling conversation summary so future turns are primed.
    if conversation_id:
        try:
            new_summary = _summarize_for_memory(
                llm, prior_summary=conv_summary,
                user_query=user_query, assistant_answer=final,
                tenant=tenant, user_id=user_id,
            )
            if new_summary:
                memory_mod.upsert_summary(
                    conversation_id=conversation_id,
                    tenant_id=tenant["id"], user_id=user_id, summary=new_summary,
                )
        except Exception:
            pass

    yield {
        "event": "final",
        "data": {
            "answer": final,
            "plan": plan,
            "specialists": [
                {
                    "agent": r.agent,
                    "answer": r.answer,
                    "tools_used": list(dict.fromkeys(r.tools_used)),
                    "tool_results": r.tool_results,
                }
                for r in runs
            ],
            "memory": {
                "facts_used": [
                    {"id": f["id"], "fact": f["fact"], "pinned": f["pinned"]} for f in facts
                ],
                "summary_pre": conv_summary,
                "prior_turn_count": len(prior_turns),
                "uploads_referenced": [u["id"] for u in upload_ctx],
            },
            "prompt_version": PROMPT_VERSION,
        },
    }
