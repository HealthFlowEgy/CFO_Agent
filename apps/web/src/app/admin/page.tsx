"use client";

import { useEffect, useState } from "react";
import {
  Building2, Users, MessageSquare, DollarSign, Zap, KeyRound, Sparkles, Activity,
} from "lucide-react";
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";

import { AdminShell } from "@/components/AdminShell";
import { api } from "@/lib/api";

const COLORS = ["#a78bfa", "#f472b6", "#60a5fa", "#fbbf24", "#34d399", "#fb7185"];

export default function AdminOverviewPage() {
  return (
    <AdminShell>
      <Inner />
    </AdminShell>
  );
}

function Inner() {
  const [data, setData] = useState<any>(null);
  const [tenants, setTenants] = useState<any[]>([]);

  useEffect(() => {
    api.adminOverview().then(setData).catch(() => {});
    api.adminTenants().then((r) => setTenants(r.tenants)).catch(() => {});
  }, []);

  if (!data) {
    return <div className="p-8 grid grid-cols-4 gap-4">
      {[...Array(4)].map((_, i) => <div key={i} className="kpi-tile h-28 shimmer" />)}
    </div>;
  }

  const planEntries = Object.entries(data.plan_distribution || {}).map(([k, v]) => ({ name: k, value: v as number }));
  const topTenants = tenants
    .slice()
    .sort((a, b) => (b.tokens_mtd || 0) - (a.tokens_mtd || 0))
    .slice(0, 6);

  return (
    <div className="p-6 lg:p-8 max-w-[1500px] mx-auto space-y-6">
      <div>
        <div className="text-xs uppercase tracking-wider text-violet-300/80 mb-1 flex items-center gap-2">
          <Activity className="w-3 h-3" /> Platform overview
        </div>
        <h1 className="text-2xl font-semibold">HealthFlow CFO Copilot — Operations</h1>
        <p className="text-sm text-slate-400">Cross-tenant view across the entire fleet.</p>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <Kpi icon={Building2}    label="Tenants"           value={data.tenants_total} />
        <Kpi icon={Users}        label="Users"             value={data.users_total} />
        <Kpi icon={MessageSquare} label="Conversations"    value={data.conversations_total} />
        <Kpi icon={KeyRound}     label="Logins (24h)"      value={data.logins_24h} />
        <Kpi icon={DollarSign}   label="MRR (USD)"         value={`$${(data.mrr_usd || 0).toLocaleString()}`} accent="gold" />
        <Kpi icon={Zap}          label="Tokens (30d)"      value={(data.usage_30d?.tokens || 0).toLocaleString()} />
      </div>

      {/* Mid row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass-strong p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium">Plan distribution</h3>
            <span className="text-[11px] text-slate-500 font-mono">/admin/overview</span>
          </div>
          {planEntries.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={planEntries} dataKey="value" innerRadius={50} outerRadius={80} paddingAngle={2}>
                  {planEntries.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="rgba(0,0,0,0)" />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: "#0b1220", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-sm text-slate-500 py-12 text-center">No tenants yet.</div>
          )}
          <div className="grid grid-cols-3 gap-2 mt-3">
            {planEntries.map((p, i) => (
              <div key={p.name} className="text-xs">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                  <span className="capitalize">{p.name}</span>
                </div>
                <div className="text-base font-mono">{p.value}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-strong p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium">Top tenants by token consumption (MTD)</h3>
            <span className="text-[11px] text-slate-500 font-mono">/admin/tenants</span>
          </div>
          {topTenants.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={topTenants.map((t) => ({ name: t.name, tokens: t.tokens_mtd }))}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} interval={0} angle={-15} textAnchor="end" height={60} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#0b1220", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }}
                  formatter={(v: any) => Number(v).toLocaleString() + " tok"}
                />
                <Bar dataKey="tokens" fill="#a78bfa" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-sm text-slate-500 py-12 text-center">No agent activity in the current month.</div>
          )}
        </div>
      </div>

      {/* Bottom row: usage breakdowns */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <UsageTile label="Agent runs (24h)" value={data.usage_24h?.runs ?? 0} />
        <UsageTile label="Tool calls (24h)" value={data.usage_24h?.tools ?? 0} />
        <UsageTile label="Agent runs (30d)" value={data.usage_30d?.runs ?? 0} />
        <UsageTile label="Tool calls (30d)" value={data.usage_30d?.tools ?? 0} />
      </div>

      <div className="glass p-4 text-xs text-slate-400">
        <div className="flex items-center gap-2 text-slate-300 mb-1">
          <Sparkles className="w-3.5 h-3.5 text-violet-300" />
          <span className="text-sm font-medium">LLM mode: <span className="font-mono text-violet-200">{data.llm_mode}</span></span>
        </div>
        {data.llm_mode === "live"
          ? "Anthropic API is configured; the orchestrator routes Conductor traffic to Opus and specialists to Sonnet."
          : "ANTHROPIC_API_KEY is not set — running on the deterministic mock provider. Set it in DO console (api → Settings) to enable live Claude."}
      </div>
    </div>
  );
}

function Kpi({
  icon: Icon, label, value, accent,
}: { icon: any; label: string; value: number | string; accent?: "gold" }) {
  return (
    <div className="kpi-tile">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
          <div className="mt-2 text-2xl font-semibold font-mono">{value}</div>
        </div>
        <div className={`w-9 h-9 rounded-lg grid place-items-center ${
          accent === "gold" ? "bg-gold/10 text-gold-400" : "bg-violet-500/10 text-violet-300"
        }`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
    </div>
  );
}

function UsageTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="glass p-4">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className="mt-1 text-xl font-mono">{Number(value).toLocaleString()}</div>
    </div>
  );
}
