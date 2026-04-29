"use client";

import { useEffect, useState } from "react";
import { Settings as SettingsIcon, ShieldCheck, Sparkles, Hospital, KeyRound, Database, Building2 } from "lucide-react";
import { Shell } from "@/components/Shell";
import { api, type Tenant } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function SettingsPage() {
  return (
    <Shell>
      <Inner />
    </Shell>
  );
}

function Inner() {
  const { t, locale } = useI18n();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [llmMode, setLlmMode] = useState<string>("");

  useEffect(() => {
    api.me().then((m) => { setTenants(m.tenants); setActive(m.active_tenant_id); }).catch(() => {});
    fetch("/api/health").then((r) => r.json()).then((h) => setLlmMode(h.llm_mode)).catch(() => {});
  }, []);

  const activeT = tenants.find((x) => x.id === active);

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-signal-300/80 mb-1">
          <SettingsIcon className="w-3 h-3" /> {t.settings}
        </div>
        <h1 className="text-2xl font-semibold">
          {locale === "ar" ? "إعدادات المستأجر" : "Tenant settings"}
        </h1>
      </div>

      {/* Plan & LLM mode */}
      <div className="grid md:grid-cols-3 gap-4">
        <div className="glass p-5">
          <div className="text-xs uppercase tracking-wider text-slate-500">{t.plan}</div>
          <div className="text-2xl font-semibold mt-2 capitalize">{activeT?.plan || "—"}</div>
          <div className="text-xs text-slate-400 mt-1">
            {locale === "ar" ? "الحدود الشهرية للرموز قابلة للتكوين." : "Monthly token budgets configurable."}
          </div>
        </div>
        <div className="glass p-5">
          <div className="text-xs uppercase tracking-wider text-slate-500">LLM Mode</div>
          <div className="mt-2 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${llmMode === "live" ? "bg-signal-400 animate-pulse-soft" : "bg-gold-400"}`}></span>
            <div className="text-2xl font-semibold capitalize">{llmMode || "…"}</div>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {llmMode === "live" ? "Anthropic Claude API enabled" : "Deterministic mock provider"}
          </div>
        </div>
        <div className="glass p-5">
          <div className="text-xs uppercase tracking-wider text-slate-500">Currency</div>
          <div className="text-2xl font-semibold mt-2">{activeT?.currency || "EGP"}</div>
          <div className="text-xs text-slate-400 mt-1">Locale: {locale.toUpperCase()}</div>
        </div>
      </div>

      {/* Tenants */}
      <div className="glass p-5">
        <div className="flex items-center gap-2 mb-3">
          <Building2 className="w-4 h-4 text-signal-300" />
          <h3 className="font-medium">{locale === "ar" ? "المستشفيات المرتبطة" : "Linked hospitals"}</h3>
        </div>
        <div className="divide-y divide-white/5">
          {tenants.map((tn) => (
            <div key={tn.id} className="py-3 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{locale === "ar" ? (tn.name_ar || tn.name) : tn.name}</div>
                <div className="text-[11px] text-slate-500">{tn.id} · {tn.plan} · {tn.role}</div>
              </div>
              {tn.id === active ? (
                <span className="text-[11px] px-2 py-0.5 rounded bg-signal-500/15 border border-signal-400/30 text-signal-200">Active</span>
              ) : (
                <button
                  className="btn-ghost !py-1.5 !text-xs"
                  onClick={async () => { await api.switchTenant(tn.id); location.reload(); }}
                >
                  {t.switch_tenant}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Compliance & posture */}
      <div className="grid md:grid-cols-2 gap-4">
        <PostureCard icon={ShieldCheck} title={locale === "ar" ? "الأمان والامتثال" : "Security & compliance"}
          items={[
            "PDPL-aligned tenant isolation",
            "Schema-per-tenant SQLite (V0) → Postgres (V1)",
            "Append-only audit log with hash chaining",
            "JWT auth with tenant claim (Keycloak SSO planned)",
          ]} />
        <PostureCard icon={Sparkles} title={locale === "ar" ? "الذكاء الاصطناعي" : "AI posture"}
          items={[
            "Anthropic Claude (Opus + Sonnet routing)",
            "Tool-use over numeric reasoning",
            "Prompt caching on stable prefixes",
            "No PHI in prompts; tenant-scoped tool registry",
          ]} />
      </div>
    </div>
  );
}

function PostureCard({ icon: Icon, title, items }: { icon: any; title: string; items: string[] }) {
  return (
    <div className="glass p-5">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-4 h-4 text-signal-300" />
        <h3 className="font-medium">{title}</h3>
      </div>
      <ul className="text-sm text-slate-300 space-y-1.5">
        {items.map((it) => (
          <li key={it} className="flex items-start gap-2">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-signal-400 shrink-0"></span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
