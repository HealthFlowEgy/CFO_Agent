"use client";

import { useEffect, useState } from "react";
import { ScrollText, RefreshCcw } from "lucide-react";

import { AdminShell } from "@/components/AdminShell";
import { api } from "@/lib/api";

const EVENT_COLORS: Record<string, string> = {
  "auth.login":          "bg-blue-500/15   text-blue-200   border-blue-400/30",
  "agent.run":           "bg-violet-500/15 text-violet-200 border-violet-400/30",
  "billing.plan_changed":"bg-gold/15       text-gold-400   border-gold/30",
};

export default function AdminAuditPage() {
  return (
    <AdminShell>
      <Inner />
    </AdminShell>
  );
}

function Inner() {
  const [events, setEvents] = useState<any[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setRefreshing(true);
    try {
      const r = await api.adminAudit(200);
      setEvents(r.events);
    } finally { setRefreshing(false); }
  };

  useEffect(() => {
    load();
    const i = setInterval(load, 15000);
    return () => clearInterval(i);
  }, []);

  if (events === null) {
    return <div className="p-8 text-sm text-slate-500">Loading audit log…</div>;
  }

  return (
    <div className="p-6 lg:p-8 max-w-[1500px] mx-auto space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-violet-300/80 mb-1 flex items-center gap-2">
            <ScrollText className="w-3 h-3" /> Audit log
          </div>
          <h1 className="text-2xl font-semibold">Last {events.length} events</h1>
          <p className="text-sm text-slate-400">Append-only, hash-chained · auto-refresh every 15s</p>
        </div>
        <button onClick={load} className="btn-ghost" disabled={refreshing}>
          <RefreshCcw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      <div className="glass-strong overflow-hidden">
        <div className="overflow-x-auto max-h-[70vh]">
          <table className="w-full text-sm">
            <thead className="bg-violet-500/5 text-[11px] uppercase tracking-wider text-violet-200/80 sticky top-0 backdrop-blur">
              <tr>
                <th className="text-start px-4 py-2.5">When</th>
                <th className="text-start px-4 py-2.5">Event</th>
                <th className="text-start px-4 py-2.5">Tenant</th>
                <th className="text-start px-4 py-2.5">User</th>
                <th className="text-start px-4 py-2.5">Hash prefix</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t border-white/5 hover:bg-white/[0.03]">
                  <td className="px-4 py-2.5 font-mono text-[11px] text-slate-400 whitespace-nowrap">
                    {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`text-[11px] px-2 py-0.5 rounded font-mono border ${EVENT_COLORS[e.event] || "bg-white/5 text-slate-300 border-white/10"}`}>
                      {e.event}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-[11px] font-mono text-slate-300">{e.tenant_id || "—"}</td>
                  <td className="px-4 py-2.5 text-[11px] font-mono text-slate-300">{e.user_id || "—"}</td>
                  <td className="px-4 py-2.5 text-[11px] font-mono text-violet-300/80">{e.hash_prefix}…</td>
                </tr>
              ))}
              {events.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-12 text-center text-slate-500">No events yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
