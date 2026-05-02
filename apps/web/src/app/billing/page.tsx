"use client";

import { useEffect, useState } from "react";
import { Check, Sparkles, Receipt, Zap, BadgeCheck, Loader2, TrendingUp, MessageSquare, Wrench } from "lucide-react";
import clsx from "clsx";

import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";
import { compactCurrency, fmtNumber, fmtPct } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

export default function BillingPage() {
  return (
    <Shell>
      <Inner />
    </Shell>
  );
}

function Inner() {
  const { locale } = useI18n();
  const [plans, setPlans] = useState<Record<string, any> | null>(null);
  const [usage, setUsage] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.plans().then((r) => setPlans(r.plans)).catch(() => {});
    api.usage().then(setUsage).catch(() => {});
  }, []);

  const choose = async (planId: string) => {
    setBusy(planId);
    try {
      await api.changePlan(planId);
      const u = await api.usage();
      setUsage(u);
    } finally { setBusy(null); }
  };

  if (!plans || !usage) {
    return <div className="p-8 text-sm text-slate-500">{locale === "ar" ? "جارٍ التحميل…" : "Loading…"}</div>;
  }

  const order = ["starter", "pro", "enterprise"];
  const current = usage.plan_id;
  const tokensPct = Math.min(100, Math.round((usage.tokens_used / usage.tokens_budget) * 100));

  return (
    <div className="p-6 lg:p-8 max-w-[1500px] mx-auto space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-signal-300/80 mb-1">
          <Receipt className="w-3 h-3" /> {locale === "ar" ? "الفواتير والاشتراك" : "Billing & Subscription"}
        </div>
        <h1 className="text-2xl font-semibold">
          {locale === "ar" ? "خطتك واستهلاكك" : "Your plan & usage"}
        </h1>
        <p className="text-sm text-slate-400">
          {locale === "ar"
            ? "كل خطة تتضمن وكلاء متخصصين وميزانية شهرية للرموز."
            : "Each plan includes specialist agents and a monthly token budget for the Anthropic API."}
        </p>
      </div>

      {/* Usage strip */}
      <div className="grid md:grid-cols-4 gap-4">
        <UsageTile icon={MessageSquare} label={locale === "ar" ? "محادثات هذا الشهر" : "Conversations this month"}
          value={fmtNumber(usage.agent_runs, locale)} />
        <UsageTile icon={Wrench} label={locale === "ar" ? "استدعاءات الأدوات" : "Tool calls"}
          value={fmtNumber(usage.tool_calls, locale)} />
        <UsageTile icon={Zap} label={locale === "ar" ? "الرموز المستخدمة" : "Tokens used"}
          value={compactCurrency(usage.tokens_used, "USD", locale).replace("$", "")} />
        <div className="kpi-tile">
          <div className="text-xs uppercase tracking-wider text-slate-400">
            {locale === "ar" ? "ميزانية الشهر" : "Monthly budget"}
          </div>
          <div className="mt-2 text-2xl font-semibold font-mono">{fmtPct(usage.tokens_pct, locale)}</div>
          <div className="mt-2 h-1.5 bg-white/5 rounded-full overflow-hidden">
            <div
              className={clsx(
                "h-full rounded-full",
                tokensPct < 70 ? "bg-signal-400" : tokensPct < 90 ? "bg-gold-400" : "bg-danger",
              )}
              style={{ width: `${tokensPct}%` }}
            />
          </div>
          <div className="text-[11px] text-slate-500 mt-2 font-mono">
            {usage.tokens_used.toLocaleString()} / {usage.tokens_budget.toLocaleString()}
          </div>
        </div>
      </div>

      {/* Plans */}
      <div className="grid md:grid-cols-3 gap-4">
        {order.map((id) => {
          const p = plans[id];
          if (!p) return null;
          const active = id === current;
          const featured = id === "pro";
          return (
            <div
              key={id}
              className={clsx(
                "glass p-6 relative flex flex-col",
                active && "border-signal-400/50 shadow-glow",
                featured && !active && "border-gold/40",
              )}
            >
              {featured && (
                <div className="absolute -top-2 left-6 text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-gold text-ink-950 font-semibold">
                  {locale === "ar" ? "الأكثر شيوعًا" : "Most popular"}
                </div>
              )}
              {active && (
                <div className="absolute -top-2 right-6 text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-signal-400 text-ink-950 font-semibold flex items-center gap-1">
                  <BadgeCheck className="w-3 h-3" /> {locale === "ar" ? "خطتك الحالية" : "Current"}
                </div>
              )}

              <div className="flex items-baseline gap-1.5">
                <Sparkles className="w-4 h-4 text-signal-300" />
                <span className="text-lg font-semibold">{p.name}</span>
              </div>

              <div className="mt-4">
                <span className="text-4xl font-semibold font-mono">${p.price_usd_per_month.toLocaleString()}</span>
                <span className="text-slate-400 text-sm"> / {locale === "ar" ? "شهر" : "month"}</span>
              </div>
              <div className="text-[11px] text-slate-500 mt-1">
                {(p.monthly_token_budget / 1_000_000).toFixed(0)}M {locale === "ar" ? "رمز / شهر" : "tokens / month"}
              </div>

              <div className="my-5 border-t border-white/5" />

              <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">
                {locale === "ar" ? "وكلاء" : "Specialist agents"}
              </div>
              <div className="flex flex-wrap gap-1.5 mb-4">
                {p.agents.map((a: string) => (
                  <span key={a} className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 border border-white/10 text-signal-300">
                    {a}
                  </span>
                ))}
              </div>

              <ul className="text-sm text-slate-300 space-y-2 flex-1">
                {p.features.map((f: string) => (
                  <li key={f} className="flex items-start gap-2">
                    <Check className="w-4 h-4 text-signal-300 shrink-0 mt-0.5" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              <button
                disabled={active || busy === id}
                onClick={() => choose(id)}
                className={clsx(
                  "mt-6 w-full",
                  active ? "btn-ghost cursor-default" : featured ? "btn-primary" : "btn-ghost",
                )}
              >
                {busy === id ? <Loader2 className="w-4 h-4 animate-spin" /> :
                 active ? (locale === "ar" ? "خطتك الحالية" : "Current plan") :
                 (locale === "ar" ? `الترقية إلى ${p.name}` : `Switch to ${p.name}`)}
              </button>
            </div>
          );
        })}
      </div>

      <div className="glass p-5 text-xs text-slate-500">
        <div className="flex items-center gap-2 text-slate-400 mb-1">
          <TrendingUp className="w-3.5 h-3.5" />
          <span className="text-sm font-medium text-slate-300">
            {locale === "ar" ? "كيف نحسب" : "How we meter"}
          </span>
        </div>
        {locale === "ar"
          ? "نحسب رموز الإدخال + الإخراج من Anthropic لكل تشغيل وكيل (التخطيط + المتخصصون + التوليف). الفواتير المستحقة شهرياً."
          : "We meter Anthropic input + output tokens across every agent run (planning + specialists + synthesis). Billed monthly. Cache hits and Batch API discounts are passed through transparently."}
      </div>
    </div>
  );
}

function UsageTile({ icon: Icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <div className="kpi-tile">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-400">{label}</div>
          <div className="mt-2 text-2xl font-semibold font-mono">{value}</div>
        </div>
        <div className="w-9 h-9 rounded-lg bg-signal-500/10 grid place-items-center text-signal-300">
          <Icon className="w-4 h-4" />
        </div>
      </div>
    </div>
  );
}
