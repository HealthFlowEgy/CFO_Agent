"""LLM provider abstraction (SRS §6.9).

Exposes a `LLMProvider` interface with two implementations:
  * AnthropicProvider — real Messages API with tool use, prompt caching.
  * MockProvider      — deterministic stub used when no ANTHROPIC_API_KEY is set,
                        so the system runs end-to-end during development.

The mock simulates tool-use loops: it reads the user message, picks a likely
tool from the registry, returns a tool_use block, then on the second pass
returns a brief text answer that cites whatever tool was called.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from app.config import settings


@dataclass
class LLMResponse:
    stop_reason: str
    content: list[dict[str, Any]]
    usage: dict[str, int]
    model: str


class LLMProvider:
    def messages_create(
        self,
        *,
        model: str,
        system: list[dict[str, Any]] | str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        max_tokens: int = 2048,
        temperature: float = 0,
        thinking: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> LLMResponse:
        raise NotImplementedError


# ---------------- Real Anthropic ----------------

class AnthropicError(Exception):
    """Wrapper that preserves the original Anthropic error class name + message."""
    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)

    def messages_create(self, **kwargs) -> LLMResponse:
        # Drop None thinking; SDK is strict
        if kwargs.get("thinking") is None:
            kwargs.pop("thinking", None)
        if kwargs.get("metadata") is None:
            kwargs.pop("metadata", None)
        if kwargs.get("tools") is None:
            kwargs.pop("tools", None)
        try:
            resp = self.client.messages.create(**kwargs)
        except Exception as e:
            kind = type(e).__name__
            msg = getattr(e, "message", None) or str(e)
            raise AnthropicError(kind, msg) from e
        content = [c.model_dump() for c in resp.content]
        usage = resp.usage.model_dump() if resp.usage else {}
        return LLMResponse(
            stop_reason=resp.stop_reason or "end_turn",
            content=content,
            usage=usage,
            model=resp.model,
        )


# ---------------- Mock provider ----------------

_TOOL_HEURISTICS = [
    (r"\b(margin|profit|pnl|p&l|service line|service-line)\b", "query_service_line_pnl"),
    (r"\b(operating margin|ebitda|kpi|cost per encounter)\b", "compute_kpi"),
    (r"\b(forecast|13[- ]?week|cash flow)\b", "forecast_cash"),
    (r"\b(cash|bank|liquidity|cash position)\b", "query_cash_position"),
    (r"\b(payer|denial|denied)\b", "query_payer_performance"),
    (r"\b(dso|days in ar|aging|net collection|revenue cycle|rcm)\b", "query_revenue_cycle"),
    (r"\b(control|exception|anomaly|audit)\b", "run_controls_check"),
]


def _pick_tool(text: str, allowed: list[str]) -> Optional[str]:
    t = text.lower()
    for pat, tool in _TOOL_HEURISTICS:
        if re.search(pat, t) and tool in allowed:
            return tool
    return None


def _default_args_for(tool: str) -> dict:
    from datetime import date, timedelta
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=90)).replace(day=1)
    end = today
    if tool == "query_service_line_pnl":
        return {"period_start": start.isoformat(), "period_end": end.isoformat()}
    if tool == "query_revenue_cycle":
        return {"as_of": end.isoformat(), "kpis": ["days_in_ar", "denial_rate", "net_collection_rate"]}
    if tool == "query_payer_performance":
        return {"as_of": end.isoformat(), "trailing_months": 3}
    if tool == "query_cash_position":
        return {"as_of": end.isoformat()}
    if tool == "forecast_cash":
        return {"horizon_weeks": 13, "scenarios": ["base"]}
    if tool == "compute_kpi":
        return {"kpi": "operating_margin", "period_start": start.isoformat(), "period_end": end.isoformat()}
    if tool == "run_controls_check":
        return {"rule_ids": ["CTRL-AR-001"], "as_of": end.isoformat()}
    return {}


class MockProvider(LLMProvider):
    """Deterministic mock; works without an Anthropic key."""

    def messages_create(self, **kwargs) -> LLMResponse:
        messages = kwargs["messages"]
        tools = kwargs.get("tools") or []
        allowed = [t["name"] for t in tools]
        last = messages[-1]

        # Conductor planning prompt? Detect by JSON-only system.
        sys_text = ""
        sysv = kwargs.get("system")
        if isinstance(sysv, str):
            sys_text = sysv
        elif isinstance(sysv, list):
            sys_text = " ".join(b.get("text", "") for b in sysv if isinstance(b, dict))

        is_planning = "OUTPUT CONTRACT" in sys_text and '"subtasks"' in sys_text
        is_synthesis = "Compose a single, coherent CFO-grade answer" in sys_text

        # Extract user text from last message (may be string or content blocks list)
        user_text = ""
        if last["role"] == "user":
            c = last["content"]
            if isinstance(c, str):
                user_text = c
            elif isinstance(c, list):
                # If last message contains tool_results, this is the second pass — emit answer.
                tool_results = [b for b in c if isinstance(b, dict) and b.get("type") == "tool_result"]
                if tool_results:
                    return self._final_answer(tool_results, kwargs.get("model", "mock"))
                user_text = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")

        if is_planning:
            return self._plan(user_text, kwargs.get("model", "mock"))
        if is_synthesis:
            return self._synthesize(user_text, kwargs.get("model", "mock"))

        # Specialist first pass — pick a tool and request it
        tool_name = _pick_tool(user_text, allowed) or (allowed[0] if allowed else None)
        if tool_name and tool_name not in ("compose_chart", "compose_table"):
            tu_id = "toolu_" + uuid.uuid4().hex[:12]
            return LLMResponse(
                stop_reason="tool_use",
                content=[{
                    "type": "tool_use",
                    "id": tu_id,
                    "name": tool_name,
                    "input": _default_args_for(tool_name),
                }],
                usage={"input_tokens": 800, "output_tokens": 40},
                model=kwargs.get("model", "mock"),
            )

        # No tool needed — short text reply
        return LLMResponse(
            stop_reason="end_turn",
            content=[{"type": "text", "text": "I can help with profitability and revenue-cycle questions. Try: 'What's our Days in AR?'"}],
            usage={"input_tokens": 300, "output_tokens": 30},
            model=kwargs.get("model", "mock"),
        )

    def _plan(self, user_text: str, model: str) -> LLMResponse:
        t = user_text.lower()
        subtasks: list[dict] = []
        if any(k in t for k in ["margin", "profit", "service line", "kpi", "ebitda", "operating", "cost per"]):
            subtasks.append({"agent": "profitability", "sub_query": user_text})
        if any(k in t for k in ["dso", "days in ar", "denial", "payer", "cash", "forecast", "13 week", "rcm", "revenue cycle"]):
            subtasks.append({"agent": "rcm", "sub_query": user_text})
        if not subtasks and user_text.strip():
            # Default to RCM for ambiguous questions in V0
            subtasks = [{"agent": "rcm", "sub_query": user_text}]

        plan = {"intent": "Answer the CFO's question.", "subtasks": subtasks}
        return LLMResponse(
            stop_reason="end_turn",
            content=[{"type": "text", "text": json.dumps(plan)}],
            usage={"input_tokens": 600, "output_tokens": 80},
            model=model,
        )

    def _synthesize(self, user_text: str, model: str) -> LLMResponse:
        # In synthesis, the user message is the JSON of findings
        try:
            data = json.loads(user_text)
            findings = data.get("specialist_findings", {})
        except Exception:
            findings = {}

        tools_used: set[str] = set()
        bullets = []
        for agent, finding in findings.items():
            ans = finding.get("answer") if isinstance(finding, dict) else str(finding)
            for tn in finding.get("tools_used", []) if isinstance(finding, dict) else []:
                tools_used.add(tn)
            if ans:
                bullets.append(f"- **{agent}**: {ans}")

        cite = ", ".join(f"[{t}]" for t in sorted(tools_used)) or ""
        body = "Here's what I found.\n\n" + "\n".join(bullets) if bullets else "I couldn't find the right data to answer."
        followup = "\n\n_Suggested follow-up: would you like a 13-week cash forecast under stress scenarios?_"
        text = f"{body}\n\n{cite}{followup}"
        return LLMResponse(
            stop_reason="end_turn",
            content=[{"type": "text", "text": text}],
            usage={"input_tokens": 1200, "output_tokens": 200},
            model=model,
        )

    def _final_answer(self, tool_results: list[dict], model: str) -> LLMResponse:
        first = tool_results[0]
        try:
            data = json.loads(first.get("content", "{}"))
        except Exception:
            data = {}
        # Build a short narrative referencing one or two key fields
        summary = self._narrate(data)
        text = f"{summary}\n\n<sources>tool_result</sources>"
        return LLMResponse(
            stop_reason="end_turn",
            content=[{"type": "text", "text": text}],
            usage={"input_tokens": 1500, "output_tokens": 150},
            model=model,
        )

    def _narrate(self, data: dict) -> str:
        if "service_lines" in data and data.get("totals"):
            t = data["totals"]
            return (
                f"Total revenue across service lines was EGP {t['revenue']:,.0f} with a "
                f"contribution margin of EGP {t['contribution_margin']:,.0f} "
                f"({t['margin_pct']}%). Top line is **{data['service_lines'][0]['name']}** "
                f"with EGP {data['service_lines'][0]['revenue']:,.0f}."
            )
        if "days_in_ar" in data:
            return f"Days in AR is **{data['days_in_ar']}** with denial rate {data.get('denial_rate_pct', 0)}%."
        if "payers" in data and data["payers"]:
            top = data["payers"][0]
            return f"Top payer by billings: **{top['name']}** at EGP {top['billed']:,.0f}, denial rate {top['denial_rate_pct']}%."
        if "accounts" in data and "total" in data:
            return f"Cash position EGP {data['total']:,.0f} as of {data['as_of']} ({data.get('wow_delta_pct', 0)}% WoW)."
        if "scenarios" in data:
            base = next((s for s in data["scenarios"] if s["scenario"] == "base"), data["scenarios"][0])
            return f"13-week forecast (base): ending balance EGP {base['ending_balance']:,.0f}."
        if "exceptions" in data:
            return f"Controls check found **{data['exception_count']}** exception(s)."
        if "value" in data and "kpi" in data:
            return f"{data['kpi']} = **{data['value']} {data['unit']}**."
        return "Result captured."


# ---------------- Factory ----------------

class FallbackProvider(LLMProvider):
    """Try Anthropic first; on transient/permanent errors, fall back to mock so
    the demo keeps working. Records last_error for observability."""

    def __init__(self, primary: LLMProvider, secondary: LLMProvider):
        self.primary = primary
        self.secondary = secondary
        self.last_error: Optional[str] = None

    def messages_create(self, **kwargs) -> LLMResponse:
        try:
            r = self.primary.messages_create(**kwargs)
            self.last_error = None
            return r
        except AnthropicError as e:
            self.last_error = str(e)
            return self.secondary.messages_create(**kwargs)


def get_llm() -> LLMProvider:
    if settings.anthropic_api_key:
        return FallbackProvider(
            AnthropicProvider(settings.anthropic_api_key),
            MockProvider(),
        )
    return MockProvider()
