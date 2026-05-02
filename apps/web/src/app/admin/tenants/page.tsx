"use client";

import { useEffect, useState } from "react";
import { Building2, ExternalLink } from "lucide-react";

import { AdminShell } from "@/components/AdminShell";
import { api } from "@/lib/api";

export default function AdminTenantsPage() {
  return (
    <AdminShell>
      <Inner />
    </AdminShell>
  );
}

function Inner() {
  const [tenants, setTenants] = useState<any[] | null>(null);

  useEffect(() => {
    api.adminTenants().then((r) => setTenants(r.tenants)).catch(() => setTenants([]));
  }, []);

  if (tenants === null) {
    return <div className="p-8 text-sm text-slate-500">Loading tenants…</div>;
  }

  const totalUsd = tenants.reduce((acc, t) => acc + (t.plan_price_usd || 0), 0);

  return (
    <div className="p-6 lg:p-8 max-w-[1500px] mx-auto space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-violet-300/80 mb-1 flex items-center gap-2">
            <Building2 className="w-3 h-3" /> Tenants
          </div>
          <h1 className="text-2xl font-semibold">{tenants.length} tenants on the platform</h1>
          <p className="text-sm text-slate-400">Monthly contracted: ${totalUsd.toLocaleString()} USD</p>
        </div>
      </div>

      <div className="glass-strong overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-violet-500/5 text-[11px] uppercase tracking-wider text-violet-200/80">
              <tr>
                <th className="text-start px-4 py-2.5">Tenant</th>
                <th className="text-start px-4 py-2.5">Plan</th>
                <th className="text-end px-4 py-2.5">$ / mo</th>
                <th className="text-end px-4 py-2.5">Users</th>
                <th className="text-end px-4 py-2.5">Conversations</th>
                <th className="text-end px-4 py-2.5">Tokens MTD</th>
                <th className="text-end px-4 py-2.5">Runs MTD</th>
                <th className="text-end px-4 py-2.5">Last activity</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr key={t.id} className="border-t border-white/5 hover:bg-white/[0.03]">
                  <td className="px-4 py-3">
                    <div className="font-medium">{t.name}</div>
                    <div className="text-[11px] text-slate-500 font-mono">{t.id}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-violet-500/10 border border-violet-400/20 text-violet-200 capitalize">
                      {t.plan || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-end font-mono">${(t.plan_price_usd || 0).toLocaleString()}</td>
                  <td className="px-4 py-3 text-end font-mono">{t.user_count}</td>
                  <td className="px-4 py-3 text-end font-mono">{t.conversation_count}</td>
                  <td className="px-4 py-3 text-end font-mono">{(t.tokens_mtd || 0).toLocaleString()}</td>
                  <td className="px-4 py-3 text-end font-mono">{t.agent_runs_mtd || 0}</td>
                  <td className="px-4 py-3 text-end text-[11px] text-slate-400">
                    {t.last_activity ? new Date(t.last_activity).toLocaleDateString() : "—"}
                  </td>
                </tr>
              ))}
              {tenants.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-500 text-sm">No tenants.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="text-[11px] text-slate-500">
        Joining a tenant for support requires JIT elevation (SRS §FR-IDT-05) — coming in V1.
      </div>
    </div>
  );
}
