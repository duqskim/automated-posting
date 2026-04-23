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
    // 기존 풀 실행 (호환용)
    run: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/run`, { method: "POST" }),
    contents: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/contents`),

    // ── 단계별 실행 ──
    /** 현재 단계 상태 전체 조회 (페이지 로드 시 복원) */
    getStage: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/stage`),

    /** Stage 1: 리서치 실행 */
    runResearch: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/stage/research`, { method: "POST" }),

    /** Stage 2: 훅 5개 생성 */
    runHooks: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/stage/hooks`, { method: "POST" }),

    /** 훅 선택 (인덱스 저장) */
    selectHook: (projectId: number, index: number) =>
      apiFetch(`/api/pipeline/${projectId}/stage/hooks`, {
        method: "PATCH",
        body: JSON.stringify({ selected_hook_index: index }),
      }),

    /** Stage 3+4: 글쓰기 + 품질 검수 */
    runWrite: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/stage/write`, { method: "POST" }),

    /** 슬라이드 텍스트 직접 편집 저장 */
    saveSlides: (projectId: number, platform: string, slides: string[]) =>
      apiFetch(`/api/pipeline/${projectId}/stage/write`, {
        method: "PATCH",
        body: JSON.stringify({ platform, slides }),
      }),

    /** Stage 5+6: 이미지 렌더링 */
    runRender: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/stage/render`, { method: "POST" }),
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
