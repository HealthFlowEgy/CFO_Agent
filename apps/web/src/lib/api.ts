// Thin client for the CFO Copilot API. Talks to the Next.js rewrite at /api/*.

export type Tenant = {
  id: string; name: string; name_ar?: string; currency: string; plan: string; role: string;
};

export type User = { id: string; email: string; name: string; locale: "en" | "ar"; role?: string };

const TOKEN_KEY = "hf_cfo_token";
const ACTIVE_KEY = "hf_cfo_active_tenant";

export const tokenStore = {
  get: () => (typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY)),
  set: (v: string) => localStorage.setItem(TOKEN_KEY, v),
  clear: () => { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(ACTIVE_KEY); },
  activeTenant: () => (typeof window === "undefined" ? null : localStorage.getItem(ACTIVE_KEY)),
  setActiveTenant: (v: string) => localStorage.setItem(ACTIVE_KEY, v),
};

function authHeaders(): HeadersInit {
  const t = tokenStore.get();
  const tid = tokenStore.activeTenant();
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (t) h["Authorization"] = `Bearer ${t}`;
  if (tid) h["X-Tenant-Id"] = tid;
  return h;
}

async function jfetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { ...init, headers: { ...authHeaders(), ...(init.headers || {}) } });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} — ${t}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async login(email: string, password: string, tenantId?: string) {
    const r = await jfetch<{ access_token: string; user: User; tenants: Tenant[]; active_tenant_id: string }>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify({ email, password, tenant_id: tenantId }) },
    );
    tokenStore.set(r.access_token);
    tokenStore.setActiveTenant(r.active_tenant_id);
    return r;
  },

  async me() {
    return jfetch<{ user: User; active_tenant_id: string; tenants: Tenant[] }>("/api/auth/me");
  },

  async switchTenant(tenant_id: string) {
    const r = await jfetch<{ access_token: string; active_tenant_id: string; role: string }>(
      "/api/auth/switch-tenant",
      { method: "POST", body: JSON.stringify({ tenant_id }) },
    );
    tokenStore.set(r.access_token);
    tokenStore.setActiveTenant(r.active_tenant_id);
    return r;
  },

  async dashboard() {
    return jfetch<any>("/api/dashboard/summary");
  },

  async listConversations() {
    return jfetch<{ id: string; title: string; created_at: string }[]>("/api/conversations");
  },

  async getConversation(id: string) {
    return jfetch<any>(`/api/conversations/${id}`);
  },

  // SSE streaming (POST + ReadableStream — native EventSource is GET-only).
  async *converseStream(message: string, conversationId?: string): AsyncGenerator<{ event: string; data: any }> {
    const res = await fetch("/api/converse/stream", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`stream failed: ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let currentEvent = "message";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n")) >= 0) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 1);
        const line = raw.replace(/\r$/, "");
        if (line === "") {
          currentEvent = "message";
          continue;
        }
        if (line.startsWith("event:")) {
          currentEvent = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          const payload = line.slice(5).trim();
          try {
            yield { event: currentEvent, data: JSON.parse(payload) };
          } catch {
            yield { event: currentEvent, data: payload };
          }
        }
      }
    }
  },
};
