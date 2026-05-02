"use client";
import { createContext, useContext } from "react";

export type Locale = "en" | "ar";

type Dict = {
  app_name: string; tagline: string; login: string; email: string; password: string;
  workspace: string; dashboard: string; library: string; settings: string; sign_out: string;
  ask_anything: string; placeholder_examples: readonly string[]; sources: string; tools_used: string;
  plan: string; role: string; cash_position: string; days_in_ar: string; denial_rate: string;
  operating_margin: string; top_payers: string; service_line_pnl: string; controls: string;
  new_chat: string; recent: string; switch_tenant: string; powered_by: string;
  mock_mode_banner: string; live_mode_banner: string;
  phases: { planning: string; specialist: string; synthesis: string; done: string };
  welcome_h: string; welcome_p: string; you: string; copilot: string;
};

export const dict: Record<Locale, Dict> = {
  en: {
    app_name: "HealthFlow CFO Copilot",
    tagline: "AI-powered financial intelligence for hospital CFOs",
    login: "Sign in",
    email: "Email",
    password: "Password",
    workspace: "Workspace",
    dashboard: "Overview",
    library: "Library",
    settings: "Settings",
    sign_out: "Sign out",
    ask_anything: "Ask anything about your numbers...",
    placeholder_examples: [
      "What's our Days in AR?",
      "Show service-line margins last quarter",
      "Forecast cash for 13 weeks under UHI delay",
      "Which payer is hurting us most?",
    ],
    sources: "Sources",
    tools_used: "Tools used",
    plan: "Plan",
    role: "Role",
    cash_position: "Cash position",
    days_in_ar: "Days in AR",
    denial_rate: "Denial rate",
    operating_margin: "Operating margin",
    top_payers: "Top payers (trailing 3 months)",
    service_line_pnl: "Service-line P&L (last 90 days)",
    controls: "Open controls exceptions",
    new_chat: "New conversation",
    recent: "Recent",
    switch_tenant: "Switch hospital",
    powered_by: "Powered by Anthropic Claude",
    mock_mode_banner: "Demo mode — running on a deterministic mock LLM. Set ANTHROPIC_API_KEY to enable live Claude.",
    live_mode_banner: "Live — connected to Anthropic Claude.",
    phases: { planning: "Planning", specialist: "Specialist analysis", synthesis: "Synthesis", done: "Done" },
    welcome_h: "Welcome back",
    welcome_p: "Ask a question, or pick one of these to get started:",
    you: "You",
    copilot: "Copilot",
  },
  ar: {
    app_name: "هيلث فلو — مساعد المدير المالي",
    tagline: "ذكاء مالي مدعوم بالذكاء الاصطناعي لمديري المستشفيات الماليين",
    login: "تسجيل الدخول",
    email: "البريد الإلكتروني",
    password: "كلمة المرور",
    workspace: "مساحة العمل",
    dashboard: "نظرة عامة",
    library: "المكتبة",
    settings: "الإعدادات",
    sign_out: "تسجيل الخروج",
    ask_anything: "اسأل أي شيء عن أرقامك...",
    placeholder_examples: [
      "ما هي عدد أيام التحصيل لدينا؟",
      "أظهر هوامش خطوط الخدمة في الربع الأخير",
      "توقع التدفق النقدي ١٣ أسبوعًا مع تأخير التأمين الصحي الشامل",
      "أي شركة تأمين تؤثر علينا أكثر؟",
    ],
    sources: "المصادر",
    tools_used: "الأدوات المستخدمة",
    plan: "الخطة",
    role: "الدور",
    cash_position: "المركز النقدي",
    days_in_ar: "أيام التحصيل",
    denial_rate: "معدل الرفض",
    operating_margin: "هامش التشغيل",
    top_payers: "أكبر شركات التأمين (٣ أشهر)",
    service_line_pnl: "ربحية خطوط الخدمة (٩٠ يومًا)",
    controls: "استثناءات الرقابة",
    new_chat: "محادثة جديدة",
    recent: "الأخيرة",
    switch_tenant: "تبديل المستشفى",
    powered_by: "مدعوم بـ Anthropic Claude",
    mock_mode_banner: "وضع تجريبي — يعمل على نموذج محاكاة. عيّن ANTHROPIC_API_KEY لتفعيل Claude.",
    live_mode_banner: "متصل مباشرة بـ Anthropic Claude.",
    phases: { planning: "التخطيط", specialist: "تحليل المتخصص", synthesis: "التركيب", done: "تم" },
    welcome_h: "مرحبًا بعودتك",
    welcome_p: "اطرح سؤالاً أو اختر أحد الأمثلة للبدء:",
    you: "أنت",
    copilot: "المساعد",
  },
};

export const I18nCtx = createContext<{ locale: Locale; t: Dict }>({
  locale: "en",
  t: dict.en,
});

export const useI18n = () => useContext(I18nCtx);
