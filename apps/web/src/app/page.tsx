"use client";

import { useEffect, useState } from "react";
import {
  Wallet, Calendar, AlertTriangle, TrendingUp, Building2, Activity,
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  AreaChart, Area, PieChart, Pie, Cell, Legend,
} from "recharts";

import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";
import { compactCurrency, fmtCurrency, fmtPct, fmtNumber } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

const PIE_COLORS = ["#2dd4bf", "#f4c66a", "#a78bfa", "#fb7185", "#60a5fa", "#facc15"];

export default function DashboardPage() {
  return (
    <Shell>
      <DashboardInner />
    </Shell>
  );
}

function DashboardInner() {
  const { locale, t } = useI18n();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await api.dashboard();
        if (alive) setData(d);
      } finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);

  if (loading || !data) {
    return (
      <div className="p-8 grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="kpi-tile h-28 shimmer" />)}
      </div>
    );
  }

  const pnl = data.pnl;
  const rcm = data.revenue_cycle;
  const cash = data.cash;
  const payers = data.payers?.payers || [];
  const exceptions = data.controls?.exception_count || 0;

  const opMargin = pnl.totals.margin_pct;

  return (
    <div className="p-6 lg:p-8 max-w-[1500px] mx-auto space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-signal-300/80 mb-1">{t.dashboard}</div>
          <h1 className="text-2xl font-semibold">
            {locale === "ar" ? "نظرة المدير المالي السريعة" : "CFO Quick View"}
          </h1>
          <p className="text-sm text-slate-400">
            {locale === "ar" ? "أهم المؤشرات لآخر ٩٠ يومًا — مدعومة بأدوات حتمية." : "Headline numbers for the last 90 days — sourced from deterministic tools."}
          </p>
        </div>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi
          icon={Wallet}
          label={t.cash_position}
          value={compactCurrency(cash.total, "EGP", locale)}
          delta={fmtPct(cash.wow_delta_pct, locale)}
          deltaPositive={(cash.wow_delta_pct || 0) >= 0}
        />
        <Kpi
          icon={Calendar}
          label={t.days_in_ar}
          value={fmtNumber(rcm.days_in_ar, locale)}
          accent="gold"
          subtle={`${cash.as_of}`}
        />
        <Kpi
          icon={Activity}
          label={t.denial_rate}
          value={fmtPct(rcm.denial_rate_pct, locale)}
          deltaPositive={false}
          accent="danger"
        />
        <Kpi
          icon={TrendingUp}
          label={t.operating_margin}
          value={fmtPct(opMargin, locale)}
          deltaPositive={opMargin >= 0}
        />
      </div>

      {/* Mid row: service line bars + payer donut */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium">{t.service_line_pnl}</h3>
            <span className="text-xs text-slate-500 font-mono">[query_service_line_pnl]</span>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={pnl.service_lines.map((s: any) => ({
              name: locale === "ar" ? (s.name_ar || s.name) : s.name,
              revenue: s.revenue,
              margin: s.contribution_margin,
            }))}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} tickFormatter={(v) => compactCurrency(Number(v), "EGP", locale)} />
              <Tooltip
                contentStyle={{ background: "#0b1220", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }}
                formatter={(v: any) => fmtCurrency(Number(v), "EGP", locale)}
              />
              <Bar dataKey="revenue" fill="#2dd4bf" radius={[6, 6, 0, 0]} />
              <Bar dataKey="margin" fill="#f4c66a" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="glass p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium">{t.top_payers}</h3>
            <span className="text-xs text-slate-500 font-mono">[query_payer_performance]</span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={payers.slice(0, 6).map((p: any) => ({
                  name: locale === "ar" ? (p.name_ar || p.name) : p.name,
                  value: p.billed,
                }))}
                dataKey="value"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
              >
                {payers.slice(0, 6).map((_: any, i: number) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} stroke="rgba(0,0,0,0)" />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: "#0b1220", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }}
                formatter={(v: any) => fmtCurrency(Number(v), "EGP", locale)}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bottom row: aging buckets + controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium">{locale === "ar" ? "أعمار الذمم المدينة" : "AR Aging Buckets"}</h3>
            <span className="text-xs text-slate-500 font-mono">[query_revenue_cycle]</span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={Object.entries(rcm.aging_buckets || {}).map(([bucket, value]) => ({ bucket, value }))}>
              <defs>
                <linearGradient id="ag" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.8} />
                  <stop offset="100%" stopColor="#2dd4bf" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="bucket" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} tickFormatter={(v) => compactCurrency(Number(v), "EGP", locale)} />
              <Tooltip
                contentStyle={{ background: "#0b1220", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }}
                formatter={(v: any) => fmtCurrency(Number(v), "EGP", locale)}
              />
              <Area dataKey="value" stroke="#2dd4bf" fill="url(#ag)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="glass p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium">{t.controls}</h3>
            <span className="text-xs text-slate-500 font-mono">[run_controls_check]</span>
          </div>
          <div className="text-3xl font-semibold flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl grid place-items-center ${exceptions > 0 ? "bg-danger/15 text-danger" : "bg-signal-500/10 text-signal-300"}`}>
              <AlertTriangle className="w-5 h-5" />
            </div>
            {exceptions}
          </div>
          <p className="text-xs text-slate-400 mt-2">
            {exceptions > 0
              ? (locale === "ar" ? "استثناءات تحتاج للمراجعة." : "Exceptions awaiting review.")
              : (locale === "ar" ? "لا استثناءات مفتوحة." : "All controls clean.")}
          </p>
        </div>
      </div>
    </div>
  );
}

function Kpi({
  icon: Icon, label, value, delta, deltaPositive, accent, subtle,
}: {
  icon: any; label: string; value: string; delta?: string; deltaPositive?: boolean;
  accent?: "gold" | "danger"; subtle?: string;
}) {
  return (
    <div className="kpi-tile">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-400">{label}</div>
          <div className="mt-2 text-2xl font-semibold font-mono">{value}</div>
          {delta && (
            <div className={`mt-1 text-xs ${deltaPositive ? "text-signal-300" : "text-danger"}`}>
              {deltaPositive ? "▲" : "▼"} {delta}
            </div>
          )}
          {subtle && <div className="text-[11px] text-slate-500 mt-1">{subtle}</div>}
        </div>
        <div className={`w-10 h-10 rounded-xl grid place-items-center ${
          accent === "gold" ? "bg-gold/10 text-gold-400" :
          accent === "danger" ? "bg-danger/10 text-danger" :
          "bg-signal-500/10 text-signal-300"
        }`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
}
