"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Send, Sparkles, Loader2, CornerDownLeft, MessageSquarePlus, History,
  ChevronRight, Wrench, BrainCircuit, Layers,
} from "lucide-react";
import clsx from "clsx";

import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { ToolResultCard } from "@/components/ToolResultCard";

type Phase = "idle" | "planning" | "specialist" | "synthesis" | "done";

type SpecialistEvent = {
  agent: string;
  answer?: string;
  tools_used: string[];
  tool_results: { tool: string; result: any }[];
  usage?: any;
};

type Turn = {
  role: "user" | "assistant";
  text?: string;
  plan?: any;
  specialists?: SpecialistEvent[];
  phase?: Phase;
  ts: number;
};

export default function WorkspacePage() {
  return (
    <Shell>
      <WorkspaceInner />
    </Shell>
  );
}

function WorkspaceInner() {
  const { t, locale } = useI18n();
  const [conversations, setConversations] = useState<{ id: string; title: string; created_at: string }[]>([]);
  const [activeConv, setActiveConv] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [activeSpecialist, setActiveSpecialist] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load conversation list
  useEffect(() => {
    (async () => {
      try {
        const list = await api.listConversations();
        setConversations(list);
      } catch { /* noop */ }
    })();
  }, []);

  // Auto-scroll on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, phase]);

  const loadConversation = async (id: string) => {
    setActiveConv(id);
    setTurns([]); setPhase("idle"); setActiveSpecialist(null);
    const c = await api.getConversation(id);
    const out: Turn[] = c.messages.map((m: any) => ({
      role: m.role,
      text: m.role === "user" ? m.content.text : m.content.answer,
      plan: m.content.plan,
      specialists: m.content.specialists,
      phase: "done",
      ts: Date.parse(m.created_at),
    }));
    setTurns(out);
  };

  const newConversation = () => {
    setActiveConv(null);
    setTurns([]); setPhase("idle"); setActiveSpecialist(null);
  };

  const send = async () => {
    const message = input.trim();
    if (!message || streaming) return;
    setInput("");
    setStreaming(true);
    setPhase("planning");
    setActiveSpecialist(null);
    setWarning(null);

    const userTurn: Turn = { role: "user", text: message, ts: Date.now() };
    const assistantTurn: Turn = {
      role: "assistant", text: "", phase: "planning", specialists: [], ts: Date.now(),
    };
    setTurns((p) => [...p, userTurn, assistantTurn]);

    try {
      for await (const evt of api.converseStream(message, activeConv || undefined)) {
        if (evt.event === "open") {
          if (evt.data?.conversation_id && !activeConv) {
            setActiveConv(evt.data.conversation_id);
            // refresh conversation list shortly after
            api.listConversations().then(setConversations).catch(() => {});
          }
        } else if (evt.event === "status") {
          if (evt.data?.phase === "planning") setPhase("planning");
          if (evt.data?.phase === "specialist_start") {
            setPhase("specialist");
            setActiveSpecialist(evt.data.agent);
          }
          if (evt.data?.phase === "synthesis") setPhase("synthesis");
        } else if (evt.event === "warning") {
          setWarning(evt.data?.message || "Warning");
        } else if (evt.event === "plan") {
          setTurns((p) => {
            const c = [...p];
            const last = c[c.length - 1];
            last.plan = evt.data;
            return c;
          });
        } else if (evt.event === "specialist_result") {
          setTurns((p) => {
            const c = [...p];
            const last = c[c.length - 1];
            last.specialists = [...(last.specialists || []), evt.data];
            return c;
          });
        } else if (evt.event === "final") {
          setTurns((p) => {
            const c = [...p];
            const last = c[c.length - 1];
            last.text = evt.data.answer;
            last.specialists = evt.data.specialists;
            last.plan = evt.data.plan;
            last.phase = "done";
            return c;
          });
          setPhase("done");
        }
      }
    } catch (e: any) {
      setTurns((p) => {
        const c = [...p];
        const last = c[c.length - 1];
        last.text = "Connection error: " + (e?.message || "unknown");
        last.phase = "done";
        return c;
      });
    } finally {
      setStreaming(false);
      setActiveSpecialist(null);
    }
  };

  const examples = useMemo(() => t.placeholder_examples, [t]);

  return (
    <div className="grid h-full" style={{ gridTemplateColumns: "260px 1fr 460px" }}>
      {/* Conversations list */}
      <aside className="border-e border-white/5 bg-ink-900/40 backdrop-blur-xl flex flex-col min-h-0">
        <div className="p-4 border-b border-white/5">
          <button onClick={newConversation} className="btn-ghost w-full">
            <MessageSquarePlus className="w-4 h-4" /> {t.new_chat}
          </button>
        </div>
        <div className="px-4 pt-3 pb-1 text-[11px] uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
          <History className="w-3 h-3" /> {t.recent}
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.length === 0 && (
            <div className="text-xs text-slate-600 p-4">{locale === "ar" ? "لا توجد محادثات بعد." : "No conversations yet."}</div>
          )}
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => loadConversation(c.id)}
              className={clsx(
                "w-full text-start px-3 py-2 rounded-lg text-sm transition truncate",
                activeConv === c.id ? "bg-signal-500/10 text-signal-100" : "hover:bg-white/5 text-slate-300",
              )}
              title={c.title}
            >
              {c.title}
            </button>
          ))}
        </div>
      </aside>

      {/* Conversation main */}
      <section className="flex flex-col min-w-0 min-h-0">
        {/* Phase strip */}
        <div className="border-b border-white/5 bg-ink-900/40 px-6 py-3 flex items-center gap-2">
          <PhasePill phase="planning" current={phase} label={t.phases.planning} icon={BrainCircuit} />
          <ChevronRight className="w-3 h-3 text-slate-600" />
          <PhasePill phase="specialist" current={phase} label={t.phases.specialist + (activeSpecialist ? ` · ${activeSpecialist}` : "")} icon={Layers} />
          <ChevronRight className="w-3 h-3 text-slate-600" />
          <PhasePill phase="synthesis" current={phase} label={t.phases.synthesis} icon={Sparkles} />
        </div>

        {warning && (
          <div className="px-6 py-2 bg-gold/10 border-b border-gold/30 text-xs text-gold-400 flex items-start gap-2">
            <span className="font-mono shrink-0">!</span>
            <span className="break-all">{warning}</span>
            <button onClick={() => setWarning(null)} className="ms-auto text-slate-500 hover:text-slate-300">×</button>
          </div>
        )}

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
          {turns.length === 0 && <Welcome examples={examples} onPick={(s) => setInput(s)} />}

          {turns.map((turn, i) => (
            <TurnView key={i} turn={turn} />
          ))}

          {streaming && phase !== "done" && <StreamingHint phase={phase} agent={activeSpecialist} />}
        </div>

        {/* Composer */}
        <div className="border-t border-white/5 bg-ink-900/40 px-6 py-4">
          <div className="glass-strong p-2 flex items-end gap-2">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
              }}
              placeholder={t.ask_anything}
              className="flex-1 bg-transparent resize-none px-3 py-2 text-sm focus:outline-none min-h-[40px] max-h-40"
            />
            <button
              onClick={send}
              disabled={!input.trim() || streaming}
              className="btn-primary !px-3 !py-2.5 disabled:opacity-50"
            >
              {streaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
          <div className="mt-2 px-1 text-[11px] text-slate-500 flex items-center gap-2">
            <CornerDownLeft className="w-3 h-3" /> {locale === "ar" ? "اضغط Enter للإرسال" : "Press Enter to send · Shift+Enter for new line"}
          </div>
        </div>
      </section>

      {/* Evidence pane */}
      <aside className="border-s border-white/5 bg-ink-900/40 backdrop-blur-xl overflow-y-auto min-h-0">
        <EvidencePane turns={turns} />
      </aside>
    </div>
  );
}

function PhasePill({
  phase, current, label, icon: Icon,
}: {
  phase: Exclude<Phase, "idle" | "done">; current: Phase; label: string; icon: any;
}) {
  const order: Phase[] = ["idle", "planning", "specialist", "synthesis", "done"];
  const idx = order.indexOf(current);
  const myIdx = order.indexOf(phase);
  const state = idx === myIdx ? "active" : idx > myIdx ? "done" : "idle";
  return (
    <span className={`phase-pill ${state}`}>
      <Icon className="w-3 h-3" /> {label}
    </span>
  );
}

function StreamingHint({ phase, agent }: { phase: Phase; agent: string | null }) {
  const text =
    phase === "planning" ? "Conductor is planning…" :
    phase === "specialist" ? `${agent ?? "Specialist"} is reasoning…` :
    "Conductor is synthesizing…";
  return (
    <div className="glass p-4 flex items-center gap-3">
      <Loader2 className="w-4 h-4 animate-spin text-signal-300" />
      <span className="text-sm text-slate-300">{text}</span>
    </div>
  );
}

function Welcome({ examples, onPick }: { examples: readonly string[]; onPick: (s: string) => void }) {
  const { t, locale } = useI18n();
  return (
    <div className="max-w-2xl mx-auto py-12">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-signal-400 to-gold-400 grid place-items-center shadow-glow">
          <Sparkles className="w-6 h-6 text-ink-950" />
        </div>
        <div>
          <h2 className="text-2xl font-semibold">{t.welcome_h}</h2>
          <p className="text-slate-400 text-sm">{t.welcome_p}</p>
        </div>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {examples.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="glass p-4 text-start hover:bg-ink-800/70 transition"
          >
            <div className="text-sm">{s}</div>
            <div className="text-[11px] text-signal-300/80 mt-2 flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> {locale === "ar" ? "جرّبه" : "Try it"}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  const { t, locale } = useI18n();
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[78%] glass-strong px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-signal-300/80 mb-1">{t.you}</div>
          <div className="whitespace-pre-wrap text-sm">{turn.text}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 max-w-[92%]">
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-signal-400 to-gold-400 grid place-items-center shrink-0 shadow-glow">
        <Sparkles className="w-4 h-4 text-ink-950" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-signal-300/80 mb-1">{t.copilot}</div>

        {turn.plan?.subtasks?.length ? (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {turn.plan.subtasks.map((st: any, i: number) => (
              <span key={i} className="text-[11px] px-2 py-1 rounded-md bg-white/5 border border-white/10 text-slate-300">
                <span className="text-signal-300">→</span> {st.agent}
              </span>
            ))}
          </div>
        ) : null}

        {turn.specialists?.map((s, i) => (
          <details key={i} className="mb-2 glass">
            <summary className="cursor-pointer px-4 py-2.5 flex items-center justify-between text-sm">
              <span className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-signal-300" />
                <span className="font-medium">{s.agent}</span>
                <span className="text-[11px] text-slate-500">
                  {s.tools_used.length} {locale === "ar" ? "أداة" : "tool"}{s.tools_used.length === 1 ? "" : "s"}
                </span>
              </span>
              <ChevronRight className="w-4 h-4 text-slate-500" />
            </summary>
            <div className="px-4 pb-3 text-sm text-slate-300 whitespace-pre-wrap prose-cfo">
              {s.answer}
            </div>
            {s.tools_used.length > 0 && (
              <div className="px-4 pb-3 flex flex-wrap gap-1.5">
                {s.tools_used.map((tn) => (
                  <span key={tn} className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-signal-300">
                    {tn}
                  </span>
                ))}
              </div>
            )}
          </details>
        ))}

        {turn.text && (
          <div className="glass-strong p-4 text-sm leading-relaxed prose-cfo">
            <Markdownish text={turn.text} />
          </div>
        )}
      </div>
    </div>
  );
}

/** Tiny markdown-ish renderer: bold **x**, em _x_, code `x`, citation [tool_name]. */
function Markdownish({ text }: { text: string }) {
  // Escape HTML
  let s = text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
  // Citations [tool_name] (lowercase + underscore + alnum)
  s = s.replace(/\[([a-z_][a-z0-9_]*)\]/g, '<span class="citation">[$1]</span>');
  // Bold
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic _x_
  s = s.replace(/(^|\W)_([^_]+)_(\W|$)/g, "$1<em>$2</em>$3");
  // Inline code
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Newlines → <br>
  s = s.replace(/\n/g, "<br/>");
  return <div dangerouslySetInnerHTML={{ __html: s }} />;
}

function EvidencePane({ turns }: { turns: Turn[] }) {
  const { t, locale } = useI18n();
  const last = [...turns].reverse().find((t) => t.role === "assistant");
  const tools = last?.specialists?.flatMap((s) => s.tool_results) || [];

  if (!last || tools.length === 0) {
    return (
      <div className="p-6 h-full">
        <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-1.5">
          <Wrench className="w-3 h-3" /> {locale === "ar" ? "الأدلة الحية" : "Live evidence"}
        </div>
        <div className="glass p-5 text-sm text-slate-400">
          {locale === "ar"
            ? "هنا ستظهر نتائج الأدوات والمخططات أثناء عمل المساعد."
            : "Tool results, charts and tables will appear here as the agents work."}
        </div>
        <div className="mt-6 glass p-5">
          <div className="text-xs text-slate-500 mb-2">{locale === "ar" ? "كيف يعمل" : "How it works"}</div>
          <ol className="text-sm text-slate-300 space-y-2 list-decimal ms-4">
            <li>{locale === "ar" ? "Conductor (Opus) يخطط ويحدد المتخصصين." : "The Conductor (Opus) plans and routes to specialists."}</li>
            <li>{locale === "ar" ? "كل متخصص يستدعي أدوات حتمية." : "Each specialist calls deterministic tools."}</li>
            <li>{locale === "ar" ? "كل رقم في الإجابة مرتبط بنتيجة أداة." : "Every number in the answer cites a tool result."}</li>
          </ol>
        </div>
      </div>
    );
  }

  return (
    <div className="p-5 space-y-3">
      <div className="text-[11px] uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
        <Wrench className="w-3 h-3" /> {locale === "ar" ? "الأدلة" : "Evidence"} · {tools.length}
      </div>
      {tools.map((tr, i) => (
        <ToolResultCard key={i} tool={tr.tool} result={tr.result} />
      ))}
    </div>
  );
}
