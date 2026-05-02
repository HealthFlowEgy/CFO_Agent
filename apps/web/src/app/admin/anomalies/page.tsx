"use client";

import { useEffect, useState } from "react";
import { Bell, AlertTriangle, MoonStar } from "lucide-react";

import { AdminShell } from "@/components/AdminShell";
import { api } from "@/lib/api";

export default function AdminAnomaliesPage() {
  return (
    <AdminShell>
      <Inner />
    </AdminShell>
  );
}

function Inner() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api.adminAnomalies().then(setData).catch(() => {});
  }, []);

  if (!data) {
    return <div className="p-8 text-sm text-slate-500">Loading signals…</div>;
  }

  return (
    <div className="p-6 lg:p-8 max-w-[1500px] mx-auto space-y-6">
      <div>
        <div className="text-xs uppercase tracking-wider text-violet-300/80 mb-1 flex items-center gap-2">
          <Bell className="w-3 h-3" /> Signals
        </div>
        <h1 className="text-2xl font-semibold">Platform health & risk signals</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Tenants near budget */}
        <div className="glass-strong p-5">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-gold-400" />
            <h3 className="font-medium">Tenants near monthly token budget (≥70%)</h3>
          </div>
          {data.tenants_near_budget?.length ? (
            <ul className="space-y-2">
              {data.tenants_near_budget.map((t: any, i: number) => (
                <li key={i} className="flex items-center justify-between p-3 rounded-lg bg-ink-800/40 border border-white/5">
                  <div>
                    <div className="text-sm font-medium">{t.tenant_name}</div>
                    <div className="text-[11px] text-slate-500 font-mono">{t.tenant_id} · {t.plan}</div>
                  </div>
                  <div className={`text-lg font-mono ${t.tokens_pct >= 90 ? "text-danger" : "text-gold-400"}`}>
                    {t.tokens_pct}%
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-slate-500 py-6 text-center">All tenants within budget.</div>
          )}
        </div>

        {/* Stale tenants */}
        <div className="glass-strong p-5">
          <div className="flex items-center gap-2 mb-3">
            <MoonStar className="w-4 h-4 text-slate-400" />
            <h3 className="font-medium">Stale tenants (no activity ≥14 days)</h3>
          </div>
          {data.stale_tenants?.length ? (
            <ul className="space-y-2">
              {data.stale_tenants.map((t: any, i: number) => (
                <li key={i} className="flex items-center justify-between p-3 rounded-lg bg-ink-800/40 border border-white/5">
                  <div>
                    <div className="text-sm font-medium">{t.tenant_name}</div>
                    <div className="text-[11px] text-slate-500 font-mono">{t.tenant_id}</div>
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono">
                    {t.last_activity ? `last: ${new Date(t.last_activity).toLocaleDateString()}` : "no activity"}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-slate-500 py-6 text-center">All tenants active.</div>
          )}
        </div>
      </div>

      <div className="glass p-4 text-[11px] text-slate-500">
        Signals are read-only in V0. V1 surfaces actions: (a) raise budget cap with audit trail,
        (b) request JIT impersonation for support, (c) suspend tenant pending review.
      </div>
    </div>
  );
}
