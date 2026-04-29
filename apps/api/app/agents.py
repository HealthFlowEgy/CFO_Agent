"""Agent orchestrator (SRS §6.3).

Conductor (Opus) plans → fan-out to specialists (Sonnet) → tools → synthesis.
Streams progress events via the `stream` generator (SSE-friendly).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterable

from app.audit import record as audit_record
from app.config import settings
from app.llm import FallbackProvider, LLMProvider, get_llm
from app.prompts import (
    CONDUCTOR_PLANNING_SYSTEM,
    CONDUCTOR_SYNTHESIS_SYSTEM,
    PROMPT_VERSION,
    SPECIALIST_REGISTRY,
    tenant_context_block,
)
from app.tools import invoke as tool_invoke, schemas_for


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


def _run_specialist(
    *, llm: LLMProvider, agent: str, sub_query: str, tenant: dict, user_id: str
) -> AgentRun:
    cfg = SPECIALIST_REGISTRY[agent]
    tools = schemas_for(cfg["tools"])

    messages: list[dict] = [{"role": "user", "content": sub_query}]
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
            result = tool_invoke(tu["name"], tenant["id"], tu.get("input") or {})
            run.tool_results.append({"tool": tu["name"], "result": result})
            tool_results_msg.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": json.dumps(result, default=str),
                "is_error": "error" in result,
            })

        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": tool_results_msg})

    # If we hit the loop cap without a final answer, surface what we have.
    if not run.answer:
        run.answer = "I gathered tool results but couldn't finalize a narrative within the loop budget."
    return run


def _conductor_plan(llm: LLMProvider, user_query: str, tenant: dict, user_id: str) -> dict:
    resp = llm.messages_create(
        model=settings.model_conductor,
        max_tokens=1024,
        temperature=0,
        system=[_cached(CONDUCTOR_PLANNING_SYSTEM)],
        messages=[{"role": "user", "content": user_query}],
        metadata={"user_id": f"{tenant['id']}:{user_id}"},
    )
    text = _extract_text(resp.content).strip()
    # Best-effort JSON parse — Anthropic may add prose; extract the first {...}
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except Exception:
        return {"intent": "Answer the CFO's question.",
                "subtasks": [{"agent": "rcm", "sub_query": user_query}]}


def _conductor_synthesize(
    llm: LLMProvider, user_query: str, runs: list[AgentRun], tenant: dict, user_id: str
) -> tuple[str, dict[str, int]]:
    findings = {
        r.agent: {
            "answer": r.answer,
            "tools_used": list(dict.fromkeys(r.tools_used)),
        }
        for r in runs
    }
    payload = {"user_query": user_query, "specialist_findings": findings}
    resp = llm.messages_create(
        model=settings.model_conductor,
        max_tokens=2048,
        temperature=0.2,
        system=[_cached(CONDUCTOR_SYNTHESIS_SYSTEM)],
        messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
        metadata={"user_id": f"{tenant['id']}:{user_id}"},
    )
    text = _extract_text(resp.content).strip()
    return text, resp.usage


async def stream_run(
    *, user_query: str, tenant: dict, user_id: str
) -> AsyncIterator[dict]:
    """Yield SSE-friendly event dicts as the conductor + specialists run."""
    llm = get_llm()
    yield {"event": "status", "data": {"phase": "planning", "model": settings.model_conductor,
                                        "llm_mode": settings.llm_mode}}

    plan = _conductor_plan(llm, user_query, tenant, user_id)
    if isinstance(llm, FallbackProvider) and llm.last_error:
        yield {"event": "warning", "data": {"message": f"Anthropic unavailable, using mock fallback: {llm.last_error}"}}
    yield {"event": "plan", "data": plan}

    subtasks: list[dict] = plan.get("subtasks") or []
    runs: list[AgentRun] = []

    if not subtasks:
        # Conversational path
        text = ("Hi! I'm your HealthFlow CFO Copilot. Try: "
                "'What's our Days in AR?', 'Show service-line margins last quarter', "
                "or 'Forecast cash for 13 weeks.'")
        yield {"event": "final", "data": {
            "answer": text, "plan": plan, "specialists": [], "prompt_version": PROMPT_VERSION,
        }}
        return

    for st in subtasks:
        agent = st.get("agent")
        if agent not in SPECIALIST_REGISTRY:
            continue
        yield {"event": "status", "data": {"phase": "specialist_start", "agent": agent}}
        run = _run_specialist(
            llm=llm, agent=agent, sub_query=st["sub_query"], tenant=tenant, user_id=user_id
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
        },
        tenant_id=tenant["id"],
        user_id=user_id,
    )

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
            "prompt_version": PROMPT_VERSION,
        },
    }
