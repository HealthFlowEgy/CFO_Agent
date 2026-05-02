"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Send, Sparkles, Loader2, CornerDownLeft, MessageSquarePlus, History,
  ChevronRight, Wrench, BrainCircuit, Layers, Paperclip, FileText, X,
  AlertCircle, RefreshCw, BookmarkPlus, Brain,
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
  attachments?: { id: string; filename: string; kind?: string }[];
  memory_used?: { id: string; fact: string; pinned: boolean }[];
  error?: string;
};

type Attachment = {
  id: string; filename: string; kind: string; status: string;
  size_bytes: number; parse_error?: string | null;
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
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [lastSent, setLastSent] = useState<{ message: string; uploadIds: string[] } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  // Expose retry to the per-turn error block (kept simple to avoid prop drilling).
  useEffect(() => {
    (window as any).__hf_retry = () => retryLast();
    return () => { try { delete (window as any).__hf_retry; } catch { /* noop */ } };
  });

  const loadConversation = async (id: string) => {
    setActiveConv(id);
    setTurns([]); setPhase("idle"); setActiveSpecialist(null); setAttachments([]);
    const c = await api.getConversation(id);
    const out: Turn[] = c.messages.map((m: any) => ({
      role: m.role,
      text: m.role === "user" ? m.content.text : m.content.answer,
      plan: m.content.plan,
      specialists: m.content.specialists,
      memory_used: m.content?.memory?.facts_used,
      phase: "done",
      ts: Date.parse(m.created_at),
    }));
    setTurns(out);
  };

  const newConversation = () => {
    setActiveConv(null);
    setTurns([]); setPhase("idle"); setActiveSpecialist(null); setAttachments([]);
  };

  const onPickFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploadError(null);
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        const uploaded = await api.uploadFile(f, activeConv || undefined);
        setAttachments((prev) => [...prev, uploaded as Attachment]);
      }
    } catch (e: any) {
      setUploadError(e?.message || "upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const send = async (opts?: { retryOf?: { message: string; uploadIds: string[] } }) => {
    const retry = opts?.retryOf;
    const message = (retry?.message ?? input).trim();
    if (!message || streaming) return;
    const uploadIds = retry ? retry.uploadIds : attachments.map((a) => a.id);
    if (!retry) {
      setInput("");
      setAttachments([]);
    }
    setLastSent({ message, uploadIds });
    setStreaming(true);
    setPhase("planning");
    setActiveSpecialist(null);
    setWarning(null);

    const userAttach = retry
      ? attachments.filter((a) => retry.uploadIds.includes(a.id)).map((a) => ({ id: a.id, filename: a.filename, kind: a.kind }))
      : attachments.map((a) => ({ id: a.id, filename: a.filename, kind: a.kind }));

    const userTurn: Turn = {
      role: "user", text: message, ts: Date.now(),
      attachments: userAttach.length ? userAttach : undefined,
    };
    const assistantTurn: Turn = {
      role: "assistant", text: "", phase: "planning", specialists: [], ts: Date.now(),
    };
    setTurns((p) => [...p, userTurn, assistantTurn]);

    try {
      for await (const evt of api.converseStream(message, activeConv || undefined, uploadIds)) {
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
            last.memory_used = evt.data?.memory?.facts_used;
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
        last.text = "";
        last.error = e?.message || "unknown";
        last.phase = "done";
        return c;
      });
    } finally {
      setStreaming(false);
      setActiveSpecialist(null);
    }
  };

  const retryLast = () => { if (lastSent) send({ retryOf: lastSent }); };

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
          {(attachments.length > 0 || uploading) && (
            <div className="mb-2 flex flex-wrap gap-2">
              {attachments.map((a) => (
                <div key={a.id} className="glass px-2.5 py-1.5 flex items-center gap-2 text-xs">
                  <FileText className="w-3.5 h-3.5 text-signal-300" />
                  <span className="max-w-[180px] truncate" title={a.filename}>{a.filename}</span>
                  <span className="text-[10px] text-slate-500">{a.kind}</span>
                  <button onClick={() => removeAttachment(a.id)} className="text-slate-500 hover:text-slate-200">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
              {uploading && (
                <div className="glass px-2.5 py-1.5 flex items-center gap-2 text-xs text-slate-400">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> {locale === "ar" ? "جارٍ الرفع..." : "Uploading…"}
                </div>
              )}
              {uploadError && (
                <div className="px-2.5 py-1.5 text-xs text-rose-300 flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5" /> {uploadError}
                </div>
              )}
            </div>
          )}
          <div className="glass-strong p-2 flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.csv,.xls,.xlsx,application/pdf,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              multiple
              hidden
              onChange={(e) => onPickFiles(e.target.files)}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={streaming || uploading}
              title={locale === "ar" ? "إرفاق ملف (PDF / CSV / XLSX)" : "Attach file (PDF / CSV / XLSX)"}
              className="btn-ghost !px-2.5 !py-2.5"
            >
              <Paperclip className="w-4 h-4" />
            </button>
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
              onClick={() => send()}
              disabled={(!input.trim() && attachments.length === 0) || streaming}
              className="btn-primary !px-3 !py-2.5 disabled:opacity-50"
            >
              {streaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
          <div className="mt-2 px-1 text-[11px] text-slate-500 flex items-center gap-2">
            <CornerDownLeft className="w-3 h-3" /> {locale === "ar" ? "اضغط Enter للإرسال" : "Press Enter to send · Shift+Enter for new line · Attach to analyze a statement"}
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
    phase === "planning" ? "Planning your question…" :
    phase === "specialist" ? `${(agent ?? "specialist").replace(/_/g, " ")} agent is reasoning…` :
    "Composing the final answer…";
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
          {turn.attachments && turn.attachments.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {turn.attachments.map((a) => (
                <span key={a.id} className="text-[11px] px-2 py-0.5 rounded bg-white/5 border border-white/10 text-slate-300 inline-flex items-center gap-1.5">
                  <FileText className="w-3 h-3 text-signal-300" />
                  <span className="max-w-[180px] truncate">{a.filename}</span>
                  {a.kind ? <span className="text-[10px] text-slate-500">{a.kind}</span> : null}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 w-full">
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-signal-400 to-gold-400 grid place-items-center shrink-0 shadow-glow">
        <Sparkles className="w-4 h-4 text-ink-950" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-signal-300/80 mb-1 flex items-center gap-2">
          {t.copilot}
          {turn.memory_used && turn.memory_used.length > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-violet-500/10 border border-violet-400/30 text-violet-200 text-[10px] inline-flex items-center gap-1"
                  title={turn.memory_used.map((f) => f.fact).join("\n")}>
              <Brain className="w-3 h-3" /> memory · {turn.memory_used.length}
            </span>
          )}
        </div>

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
        {turn.error && (
          <div className="glass-strong p-4 text-sm border border-rose-400/30 bg-rose-500/5 flex items-start gap-3">
            <AlertCircle className="w-4 h-4 text-rose-300 mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="text-rose-200 font-medium">Connection hiccup</div>
              <div className="text-slate-400 text-xs mt-0.5">{turn.error}</div>
              <button onClick={() => (window as any).__hf_retry?.()} className="btn-ghost !text-xs !py-1.5 mt-2">
                <RefreshCw className="w-3 h-3" /> Retry
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Block-aware lightweight markdown renderer (headings, lists, tables, bold,
 *  italics, code, citations). Avoids pulling a full markdown library to keep
 *  bundle size lean while still rendering the copilot's structured answers nicely. */
function Markdownish({ text }: { text: string }) {
  const escape = (raw: string) =>
    raw.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
  const inline = (raw: string) => {
    let s = escape(raw);
    // Citations [tool_name]
    s = s.replace(/\[([a-z_][a-z0-9_]*)\]/g, '<span class="citation">[$1]</span>');
    // Bold **x**
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    // Italic _x_
    s = s.replace(/(^|\W)_([^_]+)_(\W|$)/g, "$1<em>$2</em>$3");
    // Inline code
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    return s;
  };

  const lines = text.split(/\r?\n/);
  const html: string[] = [];
  let i = 0;
  const isTableRow = (l: string) => /^\s*\|.*\|\s*$/.test(l);
  const isTableSep = (l: string) => /^\s*\|?[-:\s|]+\|[-:\s|]+$/.test(l);
  while (i < lines.length) {
    const line = lines[i];

    // Pipe table
    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const split = (l: string) => l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      const header = split(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i])) {
        rows.push(split(lines[i]));
        i += 1;
      }
      html.push('<div class="md-table-wrap"><table class="md-table">');
      html.push("<thead><tr>" + header.map((h) => `<th>${inline(h)}</th>`).join("") + "</tr></thead>");
      html.push("<tbody>" + rows.map(
        (r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>",
      ).join("") + "</tbody></table></div>");
      continue;
    }

    // Headings
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const lvl = Math.min(h[1].length, 4);
      html.push(`<h${lvl + 2} class="md-h${lvl}">${inline(h[2])}</h${lvl + 2}>`);
      i += 1; continue;
    }

    // Unordered list
    if (/^\s*[-*•]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^\s*[-*•]\s+/, ""))}</li>`);
        i += 1;
      }
      html.push(`<ul class="md-ul">${items.join("")}</ul>`);
      continue;
    }

    // Ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^\s*\d+\.\s+/, ""))}</li>`);
        i += 1;
      }
      html.push(`<ol class="md-ol">${items.join("")}</ol>`);
      continue;
    }

    // Blank line -> paragraph break
    if (line.trim() === "") {
      html.push("");
      i += 1; continue;
    }

    // Default paragraph (collect consecutive non-block lines)
    const buf: string[] = [line];
    i += 1;
    while (
      i < lines.length && lines[i].trim() !== "" &&
      !/^(#{1,6})\s+/.test(lines[i]) &&
      !/^\s*[-*•]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i]) &&
      !isTableRow(lines[i])
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    html.push(`<p>${inline(buf.join(" "))}</p>`);
  }
  return <div dangerouslySetInnerHTML={{ __html: html.join("\n") }} />;
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
            <li>{locale === "ar" ? "المدير يخطط ويوزّع على المتخصصين." : "The Conductor agent plans and routes the question to the right specialists."}</li>
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
