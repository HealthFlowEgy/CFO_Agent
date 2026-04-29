"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BookMarked, ArrowRight, Sparkles } from "lucide-react";
import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function LibraryPage() {
  return (
    <Shell>
      <Inner />
    </Shell>
  );
}

function Inner() {
  const { t, locale } = useI18n();
  const [convos, setConvos] = useState<{ id: string; title: string; created_at: string }[]>([]);

  useEffect(() => {
    api.listConversations().then(setConvos).catch(() => {});
  }, []);

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-signal-300/80 mb-1">
        <BookMarked className="w-3 h-3" /> {t.library}
      </div>
      <h1 className="text-2xl font-semibold mb-4">
        {locale === "ar" ? "محادثاتك المحفوظة" : "Your saved conversations"}
      </h1>

      {convos.length === 0 ? (
        <div className="glass p-8 text-center text-slate-400">
          {locale === "ar"
            ? "لا توجد محادثات بعد. انتقل إلى مساحة العمل لطرح أول سؤال."
            : "No conversations yet. Head to the workspace to ask your first question."}
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {convos.map((c) => (
            <Link
              key={c.id}
              href={`/workspace?c=${c.id}`}
              className="glass p-4 hover:bg-ink-800/70 transition flex flex-col gap-2"
            >
              <div className="flex items-start justify-between gap-2">
                <Sparkles className="w-4 h-4 text-signal-300" />
                <ArrowRight className="w-4 h-4 text-slate-500" />
              </div>
              <div className="text-sm font-medium line-clamp-2">{c.title}</div>
              <div className="text-[11px] text-slate-500 font-mono">{new Date(c.created_at).toLocaleString()}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
