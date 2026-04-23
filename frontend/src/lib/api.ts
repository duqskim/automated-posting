const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function apiFetch(path: string, options: RequestInit = {}) {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "요청 실패" }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export const api = {
  auth: {
    login: (email: string, password: string) =>
      apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    register: (email: string, password: string, name: string) =>
      apiFetch("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, name }),
      }),
    me: () => apiFetch("/api/auth/me"),
  },
  projects: {
    list: (market?: string) =>
      apiFetch(`/api/projects${market ? `?market=${market}` : ""}`),
    create: (data: { topic: string; market: string; target_platforms?: string[]; is_urgent?: boolean }) =>
      apiFetch("/api/projects", { method: "POST", body: JSON.stringify(data) }),
    get: (id: number) => apiFetch(`/api/projects/${id}`),
  },
  pipeline: {
    run: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/run`, { method: "POST" }),
    research: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/research`, { method: "POST" }),
    contents: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/contents`),
  },
  accounts: {
    list: (market?: string) =>
      apiFetch(`/api/accounts${market ? `?market=${market}` : ""}`),
    connect: (data: { market: string; platform: string; account_name: string }) =>
      apiFetch("/api/accounts", { method: "POST", body: JSON.stringify(data) }),
    disconnect: (id: number) =>
      apiFetch(`/api/accounts/${id}`, { method: "DELETE" }),
  },
  markets: {
    list: () => apiFetch("/api/projects/markets"),
  },
};
