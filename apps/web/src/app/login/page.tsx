"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Sparkles, ArrowRight, Stethoscope, ShieldCheck, BarChart3 } from "lucide-react";
import { api } from "@/lib/api";

const DEMO = [
  { email: "amr.cfo@healthflow.demo",        name: "Amr Hassan",      role: "CFO @ Cairo + Alex",    pwd: "demo1234" },
  { email: "layla.controller@healthflow.demo", name: "Layla Ibrahim", role: "Controller (AR locale)", pwd: "demo1234" },
  { email: "omar.analyst@healthflow.demo",   name: "Omar Nabil",      role: "Analyst @ Alex",        pwd: "demo1234" },
  { email: "sara.admin@healthflow.demo",     name: "Sara Mostafa",    role: "Platform Super-Admin",  pwd: "admin1234" },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("amr.cfo@healthflow.demo");
  const [password, setPassword] = useState("demo1234");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api.login(email, password);
      router.push("/");
    } catch (err: any) {
      setError("Invalid credentials or backend unreachable.");
    } finally { setBusy(false); }
  };

  return (
    <div className="relative z-10 min-h-screen grid lg:grid-cols-2">
      {/* Brand panel */}
      <div className="hidden lg:flex flex-col justify-between p-12 border-r border-white/5 bg-ink-900/40 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-signal-400 to-gold-400 grid place-items-center shadow-glow">
            <Sparkles className="w-5 h-5 text-ink-950" />
          </div>
          <div>
            <div className="font-semibold text-lg">HealthFlow</div>
            <div className="text-xs text-signal-200/80">CFO Copilot</div>
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs bg-signal-500/10 border border-signal-400/30 text-signal-200 mb-4">
              <span className="w-1.5 h-1.5 rounded-full bg-signal-400 animate-pulse-soft" /> HealthFlow Copilot · multi-agent reasoning
            </div>
            <h1 className="text-4xl font-semibold leading-tight">
              Your hospital's CFO,<br />
              <span className="bg-gradient-to-r from-signal-400 to-gold-400 bg-clip-text text-transparent">
                amplified by HealthFlow.
              </span>
            </h1>
            <p className="mt-4 text-slate-400 max-w-md">
              Six specialist agents reason over your live operational and financial data —
              with deterministic tools, citation-backed answers, and audit-ready provenance.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 max-w-md">
            <Feature icon={Stethoscope} title="Built for hospitals"
              body="Service-line P&L, payer mix, denial trends, RCM, capex." />
            <Feature icon={ShieldCheck} title="Tenant-isolated, PDPL-aligned"
              body="Schema-per-tenant, no PHI in prompts, append-only audit." />
            <Feature icon={BarChart3} title="Every number cited"
              body="Numeric claims trace back to a deterministic tool result." />
          </div>
        </div>

        <div className="text-xs text-slate-500">© HealthFlow Group · CFO Copilot v0.1</div>
      </div>

      {/* Login panel */}
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-signal-400 to-gold-400 grid place-items-center shadow-glow">
              <Sparkles className="w-5 h-5 text-ink-950" />
            </div>
            <div>
              <div className="font-semibold">HealthFlow CFO Copilot</div>
            </div>
          </div>

          <div className="glass p-7">
            <h2 className="text-xl font-semibold">Sign in</h2>
            <p className="text-sm text-slate-400 mt-1">Use a demo account below or pick from the list.</p>

            <form onSubmit={submit} className="mt-6 space-y-4">
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1.5">Email</span>
                <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
              </label>
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1.5">Password</span>
                <input className="input" value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
              </label>
              {error && <div className="text-xs text-danger bg-danger-soft/30 border border-danger/30 px-3 py-2 rounded-lg">{error}</div>}
              <button className="btn-primary w-full" disabled={busy}>
                {busy ? "Signing in…" : "Continue"} <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          </div>

          <div className="mt-6 glass p-4">
            <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Demo accounts</div>
            <div className="space-y-1">
              {DEMO.map((d) => {
                const isAdmin = d.role.toLowerCase().includes("admin");
                return (
                  <button
                    key={d.email}
                    onClick={() => { setEmail(d.email); setPassword(d.pwd); }}
                    className="w-full text-start px-3 py-2 rounded-lg hover:bg-white/5 transition flex items-center justify-between"
                  >
                    <span>
                      <span className="text-sm">{d.name}</span>
                      <span className="block text-[11px] text-slate-500 font-mono">{d.email} · {d.pwd}</span>
                    </span>
                    <span className={`text-[11px] ${isAdmin ? "text-violet-300" : "text-signal-300"}`}>{d.role}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Feature({ icon: Icon, title, body }: { icon: any; title: string; body: string }) {
  return (
    <div className="glass p-4 flex items-start gap-3">
      <div className="w-9 h-9 rounded-lg bg-ink-700 grid place-items-center shrink-0">
        <Icon className="w-4 h-4 text-signal-300" />
      </div>
      <div>
        <div className="text-sm font-medium">{title}</div>
        <div className="text-xs text-slate-400">{body}</div>
      </div>
    </div>
  );
}
