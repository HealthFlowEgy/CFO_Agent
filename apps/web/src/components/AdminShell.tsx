"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ShieldCheck, Users, Building2, Activity, Bell, ScrollText, LogOut,
  ArrowLeft, Sparkles, Crown,
} from "lucide-react";
import clsx from "clsx";

import { api, tokenStore, type User } from "@/lib/api";

export function AdminShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    if (!tokenStore.get()) { router.push("/login"); return; }
    api.me().then((m) => {
      if (!m.user.is_platform_admin) {
        setDenied(true);
        return;
      }
      setUser(m.user);
    }).catch(() => { tokenStore.clear(); router.push("/login"); });
  }, [router]);

  if (denied) {
    return (
      <div className="min-h-screen grid place-items-center p-6 text-center">
        <div className="max-w-md">
          <ShieldCheck className="w-10 h-10 text-violet-300 mx-auto mb-3" />
          <h2 className="text-xl font-semibold mb-1">Restricted area</h2>
          <p className="text-sm text-slate-400 mb-4">
            The Super-Admin Console is reserved for HealthFlow platform staff
            with the <code className="text-violet-300">platform.admin</code> role.
          </p>
          <Link href="/" className="btn-ghost">
            <ArrowLeft className="w-4 h-4" /> Back to your workspace
          </Link>
        </div>
      </div>
    );
  }

  if (!user) {
    return <div className="min-h-screen grid place-items-center text-slate-500">Loading…</div>;
  }

  const nav = [
    { href: "/admin",          label: "Overview",  icon: Activity },
    { href: "/admin/tenants",  label: "Tenants",   icon: Building2 },
    { href: "/admin/users",    label: "Users",     icon: Users },
    { href: "/admin/audit",    label: "Audit log", icon: ScrollText },
    { href: "/admin/anomalies",label: "Signals",   icon: Bell },
  ];

  return (
    <div className="relative z-10 min-h-screen flex">
      {/* Backdrop overlay tinted violet to make the privileged context obvious */}
      <div
        className="fixed inset-0 pointer-events-none -z-10"
        style={{
          backgroundImage:
            "radial-gradient(ellipse 80% 50% at 50% -10%, rgba(167,139,250,0.10), transparent 60%), radial-gradient(ellipse 70% 60% at 100% 100%, rgba(244,114,182,0.06), transparent 60%)",
        }}
      />

      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-white/5 bg-ink-900/50 backdrop-blur-xl flex flex-col">
        <div className="px-5 pt-6 pb-5 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-violet-400 to-fuchsia-500 grid place-items-center"
                 style={{ boxShadow: "0 0 0 1px rgba(167,139,250,0.35), 0 0 24px rgba(167,139,250,0.20)" }}>
              <Crown className="w-5 h-5 text-ink-950" />
            </div>
            <div>
              <div className="font-semibold leading-tight">Super-Admin</div>
              <div className="text-xs text-violet-300/80 leading-tight">Platform Console</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {nav.map((it) => {
            const active = path === it.href || (it.href !== "/admin" && path.startsWith(it.href));
            return (
              <Link
                key={it.href}
                href={it.href}
                className={clsx(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition border",
                  active
                    ? "bg-violet-500/10 text-violet-100 border-violet-400/30"
                    : "text-slate-300 hover:bg-white/5 border-transparent",
                )}
              >
                <it.icon className="w-4 h-4" />
                {it.label}
              </Link>
            );
          })}
        </nav>

        <div className="p-3 border-t border-white/5 space-y-2">
          <Link href="/" className="btn-ghost w-full">
            <ArrowLeft className="w-4 h-4" /> Back to workspace
          </Link>
          <div className="bg-ink-900/60 border border-white/5 rounded-xl p-3">
            <div className="flex items-center gap-2 mb-1">
              <Sparkles className="w-3.5 h-3.5 text-violet-300" />
              <span className="text-xs font-medium">{user.name}</span>
            </div>
            <div className="text-[11px] text-slate-500 truncate">{user.email}</div>
            <div className="text-[10px] text-violet-300/80 mt-1 font-mono">platform.admin</div>
          </div>
          <button
            onClick={() => { tokenStore.clear(); router.push("/login"); }}
            className="w-full btn-ghost"
          >
            <LogOut className="w-4 h-4" /> Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 flex flex-col">
        <div className="border-b border-violet-400/20 bg-violet-500/5 backdrop-blur-xl px-6 py-2 flex items-center justify-between">
          <div className="text-xs text-violet-200 flex items-center gap-2">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>You are operating in <strong>privileged platform mode</strong>. All actions are audited.</span>
          </div>
          <span className="text-[11px] text-slate-500 font-mono">healthflow-admin</span>
        </div>
        <div className="flex-1 min-h-0">{children}</div>
      </main>
    </div>
  );
}
