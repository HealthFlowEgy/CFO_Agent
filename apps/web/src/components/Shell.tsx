"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard, MessagesSquare, BookMarked, Settings as SettingsIcon,
  LogOut, ChevronsUpDown, Sparkles, Hospital, Globe2,
} from "lucide-react";
import clsx from "clsx";

import { api, tokenStore, type Tenant, type User } from "@/lib/api";
import { I18nCtx, dict, type Locale } from "@/lib/i18n";

type Health = { ok: boolean; llm_mode: "live" | "mock"; models: Record<string, string> };

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [activeTenantId, setActiveTenantId] = useState<string | null>(null);
  const [locale, setLocale] = useState<Locale>("en");
  const [health, setHealth] = useState<Health | null>(null);
  const [tenantMenu, setTenantMenu] = useState(false);

  useEffect(() => {
    if (!tokenStore.get()) { router.push("/login"); return; }
    (async () => {
      try {
        const me = await api.me();
        setUser(me.user);
        setTenants(me.tenants);
        setActiveTenantId(me.active_tenant_id);
        setLocale((me.user.locale || "en") as Locale);
        document.documentElement.dir = me.user.locale === "ar" ? "rtl" : "ltr";
        document.documentElement.lang = me.user.locale || "en";
      } catch {
        tokenStore.clear();
        router.push("/login");
      }
      try {
        const r = await fetch("/api/health");
        if (r.ok) setHealth(await r.json());
      } catch { /* noop */ }
    })();
  }, [router]);

  const t = dict[locale];

  const activeTenant = useMemo(
    () => tenants.find((x) => x.id === activeTenantId) || null,
    [tenants, activeTenantId],
  );

  const onSwitch = async (tenantId: string) => {
    await api.switchTenant(tenantId);
    setActiveTenantId(tenantId);
    setTenantMenu(false);
    router.refresh();
  };

  const toggleLocale = () => {
    const next: Locale = locale === "en" ? "ar" : "en";
    setLocale(next);
    document.documentElement.dir = next === "ar" ? "rtl" : "ltr";
    document.documentElement.lang = next;
  };

  if (!user) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Loading…</div>;
  }

  const nav = [
    { href: "/", label: t.dashboard, icon: LayoutDashboard },
    { href: "/workspace", label: t.workspace, icon: MessagesSquare },
    { href: "/library", label: t.library, icon: BookMarked },
    { href: "/settings", label: t.settings, icon: SettingsIcon },
  ];

  return (
    <I18nCtx.Provider value={{ locale, t }}>
      <div className="relative z-10 min-h-screen flex">
        {/* Sidebar */}
        <aside className="w-72 shrink-0 border-r border-white/5 bg-ink-900/40 backdrop-blur-xl flex flex-col">
          {/* Logo */}
          <div className="px-5 pt-6 pb-5 border-b border-white/5">
            <div className="flex items-center gap-3">
              <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-signal-400 to-gold-400 grid place-items-center shadow-glow">
                <Sparkles className="w-5 h-5 text-ink-950" />
              </div>
              <div>
                <div className="font-semibold leading-tight">HealthFlow</div>
                <div className="text-xs text-signal-200/80 leading-tight">CFO Copilot</div>
              </div>
            </div>
          </div>

          {/* Tenant switcher */}
          <div className="p-4 border-b border-white/5 relative">
            <button
              onClick={() => setTenantMenu((v) => !v)}
              className="w-full glass p-3 flex items-center gap-3 hover:bg-ink-800/70 transition"
            >
              <div className="w-9 h-9 rounded-lg bg-ink-700 grid place-items-center">
                <Hospital className="w-4 h-4 text-signal-300" />
              </div>
              <div className="flex-1 text-start min-w-0">
                <div className="text-sm font-medium truncate">
                  {locale === "ar" && activeTenant?.name_ar ? activeTenant.name_ar : activeTenant?.name}
                </div>
                <div className="text-[11px] text-slate-400">
                  {t.plan}: <span className="text-gold-400">{activeTenant?.plan}</span>
                  <span className="px-1.5">·</span>
                  {t.role}: <span className="text-signal-300">{activeTenant?.role}</span>
                </div>
              </div>
              <ChevronsUpDown className="w-4 h-4 text-slate-400" />
            </button>

            {tenantMenu && (
              <div className="absolute left-4 right-4 mt-2 z-30 glass-strong p-1.5">
                {tenants.map((tn) => (
                  <button
                    key={tn.id}
                    onClick={() => onSwitch(tn.id)}
                    className={clsx(
                      "w-full text-start px-3 py-2 rounded-lg text-sm hover:bg-white/5",
                      tn.id === activeTenantId && "bg-signal-500/10 text-signal-100"
                    )}
                  >
                    <div className="font-medium">
                      {locale === "ar" && tn.name_ar ? tn.name_ar : tn.name}
                    </div>
                    <div className="text-[11px] text-slate-500">{tn.plan} · {tn.role}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Nav */}
          <nav className="flex-1 p-3 space-y-1">
            {nav.map((it) => {
              const Active = path === it.href || (it.href !== "/" && path.startsWith(it.href));
              return (
                <Link
                  key={it.href}
                  href={it.href}
                  className={clsx(
                    "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition",
                    Active
                      ? "bg-signal-500/10 text-signal-100 border border-signal-400/20"
                      : "text-slate-300 hover:bg-white/5 border border-transparent"
                  )}
                >
                  <it.icon className="w-4 h-4" />
                  {it.label}
                </Link>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="p-3 border-t border-white/5 space-y-2">
            <button onClick={toggleLocale} className="w-full btn-ghost justify-between">
              <span className="flex items-center gap-2"><Globe2 className="w-4 h-4" /> {locale === "en" ? "العربية" : "English"}</span>
              <span className="text-xs text-slate-500">{locale.toUpperCase()}</span>
            </button>
            <div className="glass p-3">
              <div className="text-sm font-medium truncate">{user.name}</div>
              <div className="text-[11px] text-slate-500 truncate">{user.email}</div>
            </div>
            <button
              onClick={() => { tokenStore.clear(); router.push("/login"); }}
              className="w-full btn-ghost"
            >
              <LogOut className="w-4 h-4" /> {t.sign_out}
            </button>
            <div className="text-[10px] text-slate-600 text-center pt-1">{t.powered_by}</div>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 min-w-0 flex flex-col">
          {/* Top status bar */}
          <div className="border-b border-white/5 bg-ink-900/40 backdrop-blur-xl px-6 py-2.5 flex items-center justify-between">
            <div className="text-xs text-slate-400">
              {health?.llm_mode === "live" ? (
                <span className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-signal-400 shadow-glow animate-pulse-soft"></span>
                  {t.live_mode_banner}
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-gold-400"></span>
                  {t.mock_mode_banner}
                </span>
              )}
            </div>
            <div className="text-[11px] text-slate-500 font-mono">
              {health?.models?.conductor} · {health?.models?.specialist}
            </div>
          </div>

          <div className="flex-1 min-h-0">{children}</div>
        </main>
      </div>
    </I18nCtx.Provider>
  );
}
