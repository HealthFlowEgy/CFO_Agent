"use client";

import { useState } from "react";
import { ChevronDown, Wrench } from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  LineChart, Line, AreaChart, Area,
} from "recharts";

import { compactCurrency, fmtCurrency, fmtNumber, fmtPct } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

export function ToolResultCard({ tool, result }: { tool: string; result: any }) {
  const [open, setOpen] = useState(false);
  const { locale } = useI18n();

  return (
    <div className="glass overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-sm bg-ink-800/40 hover:bg-ink-800/70 transition"
      >
        <span className="flex items-center gap-2">
          <Wrench className="w-3.5 h-3.5 text-signal-300" />
          <span className="font-mono text-signal-200">{tool}</span>
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="p-4">
          <ToolResultBody tool={tool} result={result} locale={locale} />
        </div>
      )}
    </div>
  );
}

function ToolResultBody({ tool, result, locale }: { tool: string; result: any; locale: string }) {
  if (!result || result.error) {
    return <div className="text-xs text-danger">Error: {result?.error || "no result"}</div>;
  }

  if (tool === "query_service_line_pnl" && result.service_lines) {
    return (
      <div className="space-y-3">
        <KVGrid items={[
          ["Revenue", fmtCurrency(result.totals.revenue, "EGP", locale)],
          ["Cost", fmtCurrency(result.totals.cost, "EGP", locale)],
          ["Margin", fmtCurrency(result.totals.contribution_margin, "EGP", locale)],
          ["Margin %", fmtPct(result.totals.margin_pct, locale)],
        ]} />
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={result.service_lines.map((s: any) => ({
            name: locale === "ar" ? (s.name_ar || s.name) : s.code,
            margin: s.contribution_margin,
          }))}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} />
            <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} tickFormatter={(v) => compactCurrency(Number(v), "EGP", locale)} />
            <Tooltip contentStyle={tipStyle} formatter={(v: any) => fmtCurrency(Number(v), "EGP", locale)} />
            <Bar dataKey="margin" fill="#2dd4bf" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (tool === "query_revenue_cycle") {
    return (
      <KVGrid items={[
        ["Days in AR", fmtNumber(result.days_in_ar, locale)],
        ["Denial rate", fmtPct(result.denial_rate_pct, locale)],
        ["Net collection", fmtPct(result.net_collection_rate_pct, locale)],
        ["Outstanding", fmtCurrency(result.totals?.outstanding, "EGP", locale)],
      ].filter((p): p is [string, string] => Boolean(p[1]) && p[1] !== "—")} />
    );
  }

  if (tool === "query_payer_performance" && result.payers) {
    return (
      <table className="w-full text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="text-start py-1.5">Payer</th>
            <th className="text-end py-1.5">Billed</th>
            <th className="text-end py-1.5">Denial%</th>
            <th className="text-end py-1.5">DSO</th>
          </tr>
        </thead>
        <tbody>
          {result.payers.slice(0, 8).map((p: any) => (
            <tr key={p.code} className="border-t border-white/5">
              <td className="py-1.5">{locale === "ar" ? (p.name_ar || p.name) : p.name}</td>
              <td className="text-end font-mono">{compactCurrency(p.billed, "EGP", locale)}</td>
              <td className={`text-end font-mono ${p.denial_rate_pct > 10 ? "text-danger" : "text-slate-300"}`}>
                {fmtPct(p.denial_rate_pct, locale)}
              </td>
              <td className="text-end font-mono">{fmtNumber(p.days_in_ar, locale)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (tool === "query_cash_position" && result.accounts) {
    return (
      <div className="space-y-3">
        <KVGrid items={[
          ["Total", fmtCurrency(result.total, "EGP", locale)],
          ["WoW Δ", fmtPct(result.wow_delta_pct, locale)],
          ["As of", result.as_of],
        ]} />
        <table className="w-full text-xs">
          <tbody>
            {result.accounts.map((a: any) => (
              <tr key={a.account} className="border-t border-white/5">
                <td className="py-1.5">{a.account}</td>
                <td className="text-end font-mono">{fmtCurrency(a.balance, a.currency, locale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (tool === "forecast_cash" && result.scenarios) {
    const s = result.scenarios[0];
    const series = s.weeks.map((w: any) => ({ week: `W${w.week}`, balance: w.ending_balance }));
    return (
      <div className="space-y-3">
        <KVGrid items={[
          ["Opening", fmtCurrency(result.opening_balance, "EGP", locale)],
          ["Ending", fmtCurrency(s.ending_balance, "EGP", locale)],
          ["Scenario", s.scenario],
        ]} />
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={series}>
            <defs>
              <linearGradient id="cf" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#f4c66a" stopOpacity={0.6} />
                <stop offset="100%" stopColor="#f4c66a" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis dataKey="week" tick={{ fill: "#94a3b8", fontSize: 11 }} />
            <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} tickFormatter={(v) => compactCurrency(Number(v), "EGP", locale)} />
            <Tooltip contentStyle={tipStyle} formatter={(v: any) => fmtCurrency(Number(v), "EGP", locale)} />
            <Area dataKey="balance" stroke="#f4c66a" fill="url(#cf)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (tool === "compute_kpi") {
    return (
      <div className="text-3xl font-mono">
        {result.unit === "percent" ? fmtPct(result.value, locale) :
         result.unit === "EGP" ? fmtCurrency(result.value, "EGP", locale) :
         fmtNumber(result.value, locale)}
        <div className="text-[11px] text-slate-500 mt-1 font-sans uppercase tracking-wider">{result.kpi}</div>
      </div>
    );
  }

  if (tool === "run_controls_check") {
    return (
      <div className="space-y-2">
        <KVGrid items={[
          ["Exceptions", String(result.exception_count)],
          ["Rules", String(result.rules_evaluated?.length ?? 0)],
        ]} />
        {result.exceptions?.slice(0, 5).map((e: any, i: number) => (
          <div key={i} className="text-xs glass p-2.5">
            <div className="flex items-center justify-between">
              <span className="font-mono text-signal-200">{e.rule_id}</span>
              <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded ${
                e.severity === "high" ? "bg-danger/15 text-danger" : "bg-gold/15 text-gold-400"
              }`}>{e.severity}</span>
            </div>
            <div className="text-slate-300 mt-1">{e.subject}</div>
            <div className="text-slate-500 mt-0.5">{e.detail}</div>
          </div>
        ))}
      </div>
    );
  }

  if (tool === "compose_chart" && result.chart) {
    const { type, series, title } = result.chart;
    const data = series?.[0]?.data || [];
    return (
      <div className="space-y-2">
        <div className="text-xs text-slate-400">{title}</div>
        <ResponsiveContainer width="100%" height={180}>
          {type === "line" ? (
            <LineChart data={data}>
              <XAxis dataKey="x" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <Tooltip contentStyle={tipStyle} />
              <Line dataKey="y" stroke="#2dd4bf" />
            </LineChart>
          ) : (
            <BarChart data={data}>
              <XAxis dataKey="x" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <Tooltip contentStyle={tipStyle} />
              <Bar dataKey="y" fill="#2dd4bf" radius={[4, 4, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    );
  }

  if (tool === "analyze_uploaded_statement") {
    const s = result.summary || {};
    const items: [string, string][] = [];
    items.push(["Filename", String(result.filename || "—")]);
    items.push(["Kind", String(result.kind || "—")]);
    if (result.sheet_count) items.push(["Sheets", String(result.sheet_count)]);
    if (s.rows != null) items.push(["Rows", String(s.rows)]);
    if (s.net != null) items.push(["Net", fmtCurrency(s.net, "EGP", locale)]);
    if (s.credits) items.push(["Credits", `${s.credits.count} · ${fmtCurrency(s.credits.sum, "EGP", locale)}`]);
    if (s.debits) items.push(["Debits", `${s.debits.count} · ${fmtCurrency(s.debits.sum, "EGP", locale)}`]);
    if (s.outstanding) items.push(["Outstanding", fmtCurrency(s.outstanding, "EGP", locale)]);
    if (s.margin_pct != null) items.push(["Margin %", fmtPct(s.margin_pct, locale)]);
    return (
      <div className="space-y-3">
        {items.length > 0 && <KVGrid items={items} />}
        {Array.isArray(result.sheets) && result.sheets.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Sheets</div>
            <div className="flex flex-wrap gap-1.5">
              {result.sheets.slice(0, 24).map((sn: string) => (
                <span key={sn} className="text-[11px] px-2 py-0.5 rounded bg-white/5 border border-white/10 text-slate-300 truncate max-w-[160px]" title={sn}>{sn}</span>
              ))}
              {result.sheets.length > 24 && <span className="text-[11px] text-slate-500">+{result.sheets.length - 24} more</span>}
            </div>
          </div>
        )}
        {result.headline?.largest_numeric_aggregates?.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Largest aggregates</div>
            <table className="w-full text-xs">
              <thead className="text-slate-500">
                <tr><th className="text-start py-1">Sheet</th><th className="text-start py-1">Column</th><th className="text-end py-1">Sum</th></tr>
              </thead>
              <tbody>
                {result.headline.largest_numeric_aggregates.slice(0, 6).map((r: any, i: number) => (
                  <tr key={i} className="border-t border-white/5">
                    <td className="py-1 truncate max-w-[120px]" title={r.sheet}>{r.sheet}</td>
                    <td className="py-1 truncate max-w-[140px]" title={r.column}>{r.column}</td>
                    <td className="py-1 text-end font-mono">{compactCurrency(Number(r.sum) || 0, "EGP", locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  if (tool === "recommend_actions_from_statement" && Array.isArray(result.recommendations)) {
    const sevColor = (s: string) =>
      s === "high" ? "bg-danger/15 text-danger border-danger/30" :
      s === "medium" ? "bg-gold/15 text-gold-400 border-gold/30" :
      "bg-signal-500/10 text-signal-200 border-signal-400/30";
    return (
      <div className="space-y-2">
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{result.recommendations.length} recommendation{result.recommendations.length === 1 ? "" : "s"} · focus: {result.focus || "general"}</div>
        {result.recommendations.map((r: any, i: number) => (
          <div key={i} className="glass p-2.5 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-200">{r.action}</span>
              <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded border ${sevColor(r.severity)}`}>{r.severity}</span>
            </div>
            <div className="text-slate-400 mt-1 leading-relaxed">{r.rationale}</div>
          </div>
        ))}
      </div>
    );
  }

  if (tool === "recall_memory" && Array.isArray(result.facts)) {
    if (result.facts.length === 0) return <div className="text-xs text-slate-500">No prior facts on file.</div>;
    return (
      <div className="space-y-1.5">
        {result.facts.map((f: any) => (
          <div key={f.id} className="text-xs glass p-2 flex items-start gap-2">
            <span className={`text-[10px] mt-0.5 px-1 rounded ${f.pinned ? "bg-violet-500/15 text-violet-200" : "bg-white/5 text-slate-400"}`}>{f.pinned ? "pinned" : "recall"}</span>
            <span className="text-slate-300">{f.fact}</span>
          </div>
        ))}
      </div>
    );
  }

  if (tool === "pin_memory" && result.fact) {
    return (
      <div className="text-xs glass p-2.5">
        <div className="text-violet-200 font-medium mb-1">Pinned to memory</div>
        <div className="text-slate-300">{result.fact.fact}</div>
      </div>
    );
  }

  // Fallback: collapsible JSON (closed by default to keep panel tidy)
  return (
    <details className="text-[11px] font-mono text-slate-400">
      <summary className="cursor-pointer text-slate-500 hover:text-slate-300">Raw result</summary>
      <pre className="mt-2 max-h-72 overflow-auto bg-black/30 p-3 rounded-lg">
        {JSON.stringify(result, null, 2)}
      </pre>
    </details>
  );
}

function KVGrid({ items }: { items: [string, string][] }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {items.map(([k, v]) => (
        <div key={k} className="bg-ink-800/40 border border-white/5 rounded-lg p-2.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div>
          <div className="text-sm font-mono mt-0.5">{v}</div>
        </div>
      ))}
    </div>
  );
}

const tipStyle = {
  background: "#0b1220",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 12,
  fontSize: 12,
};
