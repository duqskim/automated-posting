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
    delete: (id: number) =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/projects/${id}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${typeof window !== "undefined" ? localStorage.getItem("token") ?? "" : ""}`,
        },
      }).then(res => {
        if (res.status === 401) { window.location.href = "/login"; throw new Error("Unauthorized"); }
        if (!res.ok) throw new Error("삭제 실패");
      }),
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

    /** Stage 3+4: 글쓰기 + 품질 검수 (fixFacts=true 시 팩트 오류 반영 재작성) */
    runWrite: (projectId: number, fixFacts = false) =>
      apiFetch(`/api/pipeline/${projectId}/stage/write`, {
        method: "POST",
        body: JSON.stringify({ fix_facts: fixFacts }),
      }),

    /** 슬라이드 텍스트 + 이미지 프롬프트 편집 저장 */
    saveSlides: (projectId: number, platform: string, slides: string[], image_prompts?: string[]) =>
      apiFetch(`/api/pipeline/${projectId}/stage/write`, {
        method: "PATCH",
        body: JSON.stringify({ platform, slides, image_prompts }),
      }),

    /** Stage 4: 씬 이미지 생성 (Imagen 4 / DALL-E 3) */
    runRender: (projectId: number, platform: string = "youtube", imageProvider: string = "auto") =>
      apiFetch(`/api/pipeline/${projectId}/stage/render`, {
        method: "POST",
        body: JSON.stringify({ platform, image_provider: imageProvider }),
      }),

    /** 단일 슬라이드 이미지 재생성 */
    regenerateImage: (projectId: number, slideIndex: number, platform: string = "youtube") =>
      apiFetch(`/api/pipeline/${projectId}/stage/render/${slideIndex}`, {
        method: "POST",
        body: JSON.stringify({ platform }),
      }),

    /** Stage 7: 영상 제작 (Veo + TTS + moviepy + BGM) */
    getLog: (projectId: number) =>
      apiFetch(`/api/pipeline/${projectId}/stage/log`),

    runVideo: (projectId: number, platform: string = "youtube", ttsProvider: string = "none", bgmCategory: string = "none") =>
      apiFetch(`/api/pipeline/${projectId}/stage/video`, {
        method: "POST",
        body: JSON.stringify({ platform, tts_provider: ttsProvider, bgm_category: bgmCategory }),
      }),
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
  series: {
    list: () => apiFetch("/api/series"),
    create: (data: {
      name: string;
      description?: string;
      market?: string;
      language?: string;
      category?: string;
      visual_style?: string;
      fact_mode?: string;
      target_platforms?: string[];
    }) => apiFetch("/api/series", { method: "POST", body: JSON.stringify(data) }),
    get: (id: number) => apiFetch(`/api/series/${id}`),
    update: (id: number, data: object) =>
      apiFetch(`/api/series/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    delete: (id: number) =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/series/${id}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${typeof window !== "undefined" ? localStorage.getItem("token") ?? "" : ""}`,
        },
      }).then(res => {
        if (!res.ok) throw new Error("삭제 실패");
      }),

    episodes: {
      add: (seriesId: number, episodes: object[]) =>
        apiFetch(`/api/series/${seriesId}/episodes`, {
          method: "POST",
          body: JSON.stringify({ episodes }),
        }),
      update: (seriesId: number, episodeId: number, data: object) =>
        apiFetch(`/api/series/${seriesId}/episodes/${episodeId}`, {
          method: "PATCH",
          body: JSON.stringify(data),
        }),
      delete: (seriesId: number, episodeId: number) =>
        fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/series/${seriesId}/episodes/${episodeId}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${typeof window !== "undefined" ? localStorage.getItem("token") ?? "" : ""}`,
          },
        }).then(res => { if (!res.ok) throw new Error("삭제 실패"); }),
      generate: (seriesId: number, episodeId: number) =>
        apiFetch(`/api/series/${seriesId}/episodes/${episodeId}/generate`, { method: "POST" }),
    },

    characters: {
      create: (seriesId: number, data: object) =>
        apiFetch(`/api/series/${seriesId}/characters`, {
          method: "POST",
          body: JSON.stringify(data),
        }),
      update: (seriesId: number, characterId: number, data: object) =>
        apiFetch(`/api/series/${seriesId}/characters/${characterId}`, {
          method: "PATCH",
          body: JSON.stringify(data),
        }),
      delete: (seriesId: number, characterId: number) =>
        fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/series/${seriesId}/characters/${characterId}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${typeof window !== "undefined" ? localStorage.getItem("token") ?? "" : ""}`,
          },
        }).then(res => { if (!res.ok) throw new Error("삭제 실패"); }),

      // ── Character Design Studio ──
      design: {
        get: (seriesId: number, characterId: number) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design`),
        runAudience: (seriesId: number, characterId: number) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design/audience`, { method: "POST" }),
        runArchetypes: (seriesId: number, characterId: number) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design/archetypes`, { method: "POST" }),
        selectArchetype: (seriesId: number, characterId: number, index: number) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design/archetypes/select`, {
            method: "POST",
            body: JSON.stringify({ index }),
          }),
        runConcepts: (seriesId: number, characterId: number) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design/concepts`, { method: "POST" }),
        selectConcept: (seriesId: number, characterId: number, index: number) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design/concepts/select`, {
            method: "POST",
            body: JSON.stringify({ index }),
          }),
        generateImages: (seriesId: number, characterId: number) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design/visual/generate`, { method: "POST" }),
        saveImageUrls: (seriesId: number, characterId: number, image_urls: string[]) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design/visual`, {
            method: "POST",
            body: JSON.stringify({ image_urls }),
          }),
        selectImage: (seriesId: number, characterId: number, index: number) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design/visual/select`, {
            method: "POST",
            body: JSON.stringify({ index }),
          }),
        runBible: (seriesId: number, characterId: number) =>
          apiFetch(`/api/series/${seriesId}/characters/${characterId}/design/bible`, { method: "POST" }),
      },
    },
  },
};
