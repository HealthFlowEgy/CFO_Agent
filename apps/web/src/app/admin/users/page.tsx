"use client";

import { useEffect, useState } from "react";
import { Users, Crown } from "lucide-react";

import { AdminShell } from "@/components/AdminShell";
import { api } from "@/lib/api";

export default function AdminUsersPage() {
  return (
    <AdminShell>
      <Inner />
    </AdminShell>
  );
}

function Inner() {
  const [users, setUsers] = useState<any[] | null>(null);

  useEffect(() => {
    api.adminUsers().then((r) => setUsers(r.users)).catch(() => setUsers([]));
  }, []);

  if (users === null) {
    return <div className="p-8 text-sm text-slate-500">Loading users…</div>;
  }

  const adminCount = users.filter((u) => u.is_platform_admin).length;

  return (
    <div className="p-6 lg:p-8 max-w-[1500px] mx-auto space-y-6">
      <div>
        <div className="text-xs uppercase tracking-wider text-violet-300/80 mb-1 flex items-center gap-2">
          <Users className="w-3 h-3" /> Users
        </div>
        <h1 className="text-2xl font-semibold">{users.length} users · {adminCount} platform admin{adminCount === 1 ? "" : "s"}</h1>
      </div>

      <div className="glass-strong overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-violet-500/5 text-[11px] uppercase tracking-wider text-violet-200/80">
              <tr>
                <th className="text-start px-4 py-2.5">Name / email</th>
                <th className="text-start px-4 py-2.5">Locale</th>
                <th className="text-start px-4 py-2.5">Tenant memberships</th>
                <th className="text-start px-4 py-2.5">Role flags</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-white/5 hover:bg-white/[0.03]">
                  <td className="px-4 py-3">
                    <div className="font-medium flex items-center gap-2">
                      {u.is_platform_admin && <Crown className="w-3.5 h-3.5 text-violet-300" />}
                      {u.name}
                    </div>
                    <div className="text-[11px] text-slate-500 font-mono">{u.email}</div>
                  </td>
                  <td className="px-4 py-3 text-[11px] uppercase tracking-wider text-slate-400">{u.locale}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {(u.memberships || []).length === 0 && <span className="text-[11px] text-slate-500">—</span>}
                      {(u.memberships || []).map((m: any, i: number) => (
                        <span key={i} className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10">
                          <span className="text-slate-400">{m.tenant_id}</span>
                          <span className="text-slate-600 mx-1">·</span>
                          <span className="text-violet-300">{m.role}</span>
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {u.is_platform_admin ? (
                      <span className="text-[11px] px-2 py-0.5 rounded bg-violet-500/15 border border-violet-400/30 text-violet-200 font-medium">platform.admin</span>
                    ) : (
                      <span className="text-[11px] text-slate-500">tenant user</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
