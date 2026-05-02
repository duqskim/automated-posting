"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import AppShell from "@/components/AppShell";

/* ─── 타입 ─────────────────────────────────────────────── */

interface Project {
  id: number;
  topic: string;
  market: string;
  language: string;
  status: string;
  target_platforms: string[];
}

interface HookItem {
  text: string;
  style: string;
  score: number;
  platform_fit: string[];
}

interface PlatformContent {
  platform: string;
  hook: string;
  body: string[];
  image_prompts: string[];
  caption: string;
  hashtags: string[];
  cta: string;
}

interface VideoResult {
  platform: string;
  status?: string;  // "processing" | undefined
  task_id?: string;
  full_video_url: string | null;
  shorts_video_url: string | null;
  duration: number | null;
  clips_count: number;
  error?: string;
}

interface StageState {
  current_step: string;
  research: {
    topic: string;
    keywords: string[];
    top_content: { platform: string; title: string; hook_used?: string; format_notes?: string }[];
    winning_formula: {
      hook_patterns: string[];
      content_structure: string;
      avg_length: string;
      hashtag_strategy: string;
      content_gaps: string[];
    };
  } | null;
  hooks: {
    hooks: HookItem[];
    recommended_hook_index: number;
  } | null;
  selected_hook_index: number;
  content: {
    topic: string;
    thumbnail_text: string;
    platform_contents: PlatformContent[];
  } | null;
  image_urls: string[];
  image_prompts: string[];
  frame_motion_prompts: string[];
  shot_script: Record<string, unknown> | null;
  thumbnail_url: string | null;
  quality_score: number | null;
  quality_status: string | null;
  fact_check: {
    verified: boolean;
    disputed_count: number;
    uncertain_count: number;
    summary: string;
    claims: { claim: string; status: string; note: string }[];
  } | null;
  video: VideoResult | null;
}

/* ─── 상수 ─────────────────────────────────────────────── */

const MARKET_FLAGS: Record<string, string> = { kr: "🇰🇷", us: "🇺🇸", jp: "🇯🇵" };
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const HOOK_STYLE_LABELS: Record<string, string> = {
  data: "📊 데이터",
  result: "🏆 결과",
  contrarian: "🔄 반전",
  curiosity: "🤔 궁금증",
  urgency: "⚡ 긴박감",
};

const STEP_ORDER = ["idle", "research_done", "hooks_done", "write_done", "render_done", "video_processing", "video_done", "publish_done"];

function stepIndex(step: string) {
  return STEP_ORDER.indexOf(step);
}

// 전체 파이프라인 단계 메타데이터
const PIPELINE_STEPS = [
  { id: 1, label: "리서치",    short: "리서치",  minIdx: 0 },
  { id: 2, label: "훅 선택",   short: "훅",      minIdx: 1 },
  { id: 3, label: "글쓰기",    short: "글쓰기",  minIdx: 2 },
  { id: 4, label: "이미지",    short: "이미지",  minIdx: 3 },
  { id: 5, label: "영상",      short: "영상",    minIdx: 5 },
  { id: 6, label: "발행",      short: "발행",    minIdx: 7 },
];

function PipelineProgress({ currentIdx }: { currentIdx: number }) {
  return (
    <div className="flex items-center gap-1 py-3 px-1 overflow-x-auto">
      {PIPELINE_STEPS.map((s, i) => {
        const done = currentIdx > s.minIdx;
        const active = currentIdx === s.minIdx || (s.id === 5 && currentIdx === 6);
        return (
          <div key={s.id} className="flex items-center gap-1 flex-shrink-0">
            <div className={`
              flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors
              ${done    ? "bg-green-500/15 text-green-600 border border-green-500/30" :
                active  ? "bg-primary/15 text-primary border border-primary/30" :
                          "bg-muted/30 text-muted-foreground border border-transparent"}
            `}>
              <span>{done ? "✓" : s.id}</span>
              <span>{s.short}</span>
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <span className={`text-xs ${done ? "text-green-400" : "text-muted-foreground/30"}`}>→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ─── 메인 컴포넌트 ─────────────────────────────────────── */

export default function ProjectDetailPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = Number(params.id);

  const [project, setProject] = useState<Project | null>(null);
  const [stage, setStage] = useState<StageState>({
    current_step: "idle",
    research: null,
    hooks: null,
    selected_hook_index: 0,
    content: null,
    image_urls: [],
    image_prompts: [],
    frame_motion_prompts: [],
    shot_script: null,
    thumbnail_url: null,
    quality_score: null,
    quality_status: null,
    fact_check: null,
    video: null,
  });
  const [videoPlatform, setVideoPlatform] = useState("youtube");
  const [imageProvider, setImageProvider] = useState<"auto" | "imagen" | "gemini-flash" | "gemini-pro" | "gpt-image-1" | "dalle">("gemini-flash");
  const [ttsPlatform, setTtsPlatform] = useState<"none" | "gemini" | "elevenlabs">("gemini");
  const [bgmCategory, setBgmCategory] = useState<"none" | "cinematic" | "ambient" | "upbeat" | "dramatic">("cinematic");
  const [publishPlatform, setPublishPlatform] = useState("youtube");
  const [publishResult, setPublishResult] = useState<{ results: { platform: string; success: boolean; post_url?: string; error?: string }[] } | null>(null);
  const [loading, setLoading] = useState<string | null>(null); // 로딩 중인 스텝 이름
  const [writeStep, setWriteStep] = useState<string>("");
  const [imageStep, setImageStep] = useState<string>("");
  const [error, setError] = useState("");
  const [videoLog, setVideoLog] = useState<{ lines: string[]; step: string } | null>(null);

  // 편집 상태
  const [editingPlatform, setEditingPlatform] = useState<string | null>(null);
  const [editedSlides, setEditedSlides] = useState<string[]>([]);
  const [editedImagePrompts, setEditedImagePrompts] = useState<string[]>([]);
  const [savingSlides, setSavingSlides] = useState(false);
  const [expandedPrompts, setExpandedPrompts] = useState<Record<string, boolean>>({});

  // 이미지 프롬프트 협업 수정 상태
  const [rewritePanel, setRewritePanel] = useState<{
    slideIndex: number;
    correctionIntent: string;
    rewrittenPrompt: string | null;
    originalPrompt: string;
    loading: boolean;
  } | null>(null);

  /* ─── 로드 ─────────────────────────────────────────────── */

  const loadProject = useCallback(async () => {
    try {
      const data = await api.projects.get(projectId);
      setProject(data);
    } catch {
      router.push("/dashboard");
    }
  }, [projectId, router]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { router.push("/login"); return; }

    loadProject();
    api.pipeline.getStage(projectId)
      .then((data: StageState) => {
        if (data.image_urls?.length) {
          const ts = Date.now();
          data.image_urls = data.image_urls.map((u: string) => u.includes("?t=") ? u : `${u}?t=${ts}`);
        }
        setStage(data);
      })
      .catch(() => {});
  }, [loadProject, router, projectId]);

  // 영상 백그라운드 처리 중 자동 폴링 (10초 간격) + 로그 갱신
  useEffect(() => {
    if (stage.current_step !== "video_processing") return;
    const poll = async () => {
      try {
        const [stageData, logData] = await Promise.all([
          api.pipeline.getStage(projectId),
          api.pipeline.getLog(projectId),
        ]);
        setStage(stageData);
        setVideoLog(logData);
        if (stageData.current_step === "video_done" || (stageData.video && !stageData.video.status)) {
          await loadProject();
        }
      } catch { /* 무시 */ }
    };
    poll(); // 즉시 1회
    const interval = setInterval(poll, 10_000);
    return () => clearInterval(interval);
  }, [stage.current_step, projectId, loadProject]);

  /* ─── 단계 실행 ─────────────────────────────────────────── */

  const runResearch = async () => {
    setLoading("research");
    setError("");
    try {
      const res = await api.pipeline.runResearch(projectId);
      setStage(prev => ({
        ...prev,
        current_step: "research_done",
        research: res.research,
        hooks: null,
        content: null,
        image_urls: [],
      }));
      await loadProject();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "리서치 실패");
    } finally {
      setLoading(null);
    }
  };

  const runHooks = async () => {
    setLoading("hooks");
    setError("");
    try {
      const res = await api.pipeline.runHooks(projectId);
      setStage(prev => ({
        ...prev,
        current_step: "hooks_done",
        hooks: res.hooks,
        selected_hook_index: res.hooks?.recommended_hook_index ?? 0,
        content: null,
        image_urls: [],
      }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "훅 생성 실패");
    } finally {
      setLoading(null);
    }
  };

  const selectHook = async (index: number) => {
    setStage(prev => ({ ...prev, selected_hook_index: index }));
    try {
      await api.pipeline.selectHook(projectId, index);
    } catch { /* 무시 */ }
  };

  const runWrite = async (fixFacts = false) => {
    setLoading(fixFacts ? "write_fix" : "write");
    setWriteStep("선택한 훅 분석 중...");
    setError("");

    // 단계별 상태 메시지 (시간 기반)
    const writeSteps = [
      [3000,  "플랫폼별 콘텐츠 작성 중..."],
      [20000, "품질 검수 중..."],
      [35000, "팩트 체크 중 (Google 검색)..."],
      [55000, "마무리 중..."],
    ] as const;
    const timers = writeSteps.map(([ms, msg]) =>
      setTimeout(() => setWriteStep(msg), ms)
    );

    try {
      const res = await api.pipeline.runWrite(projectId, fixFacts);
      timers.forEach(clearTimeout);
      setStage(prev => ({
        ...prev,
        current_step: "write_done",
        content: res.content,
        quality_score: res.quality_score,
        fact_check: res.fact_check ?? null,
        image_urls: [],
      }));
      await loadProject();
    } catch (e: unknown) {
      timers.forEach(clearTimeout);
      setError(e instanceof Error ? e.message : "글쓰기 실패");
    } finally {
      setWriteStep("");
      setLoading(null);
    }
  };

  const startEditSlides = (platform: PlatformContent) => {
    setEditingPlatform(platform.platform);
    setEditedSlides([...platform.body]);
    // 실제 렌더 프롬프트(stage.image_prompts) 우선, 없으면 content의 placeholder
    const realPrompts = stage?.image_prompts?.length ? stage.image_prompts : null;
    setEditedImagePrompts([...(realPrompts || platform.image_prompts || platform.body.map((_, i) => `슬라이드 ${i+1}: 이미지 방향을 입력하세요`))]);
  };

  const saveSlides = async () => {
    if (!editingPlatform) return;
    setSavingSlides(true);
    try {
      await api.pipeline.saveSlides(projectId, editingPlatform, editedSlides, editedImagePrompts);
      setStage(prev => {
        if (!prev.content) return prev;
        return {
          ...prev,
          content: {
            ...prev.content,
            platform_contents: prev.content.platform_contents.map(pc =>
              pc.platform === editingPlatform
                ? { ...pc, body: editedSlides, image_prompts: editedImagePrompts }
                : pc
            ),
          },
          image_urls: [],
        };
      });
      setEditingPlatform(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSavingSlides(false);
    }
  };

  const runRender = async (platform: string = videoPlatform) => {
    setLoading("render");
    setImageStep("이미지 프롬프트 준비 중...");
    setError("");

    // 시간 기반 단계 메시지 (슬라이드 25개 기준 약 3~6분)
    const imageSteps: [number, string][] = [
      [5000,   "씬 1~5 이미지 생성 중..."],
      [50000,  "씬 6~10 이미지 생성 중..."],
      [100000, "씬 11~15 이미지 생성 중..."],
      [150000, "씬 16~20 이미지 생성 중..."],
      [200000, "씬 21~25 이미지 생성 중..."],
      [260000, "썸네일 생성 중..."],
      [290000, "마무리 중..."],
    ];
    const stepTimers = imageSteps.map(([ms, msg]) => setTimeout(() => setImageStep(msg), ms));

    try {
      const res = await api.pipeline.runRender(projectId, platform, imageProvider);

      // 비동기 모드(Celery): render_processing 반환 → 완료될 때까지 폴링
      if (res.step === "render_processing") {
        setImageStep("이미지 생성 중... (최대 10분 소요)");
        const deadline = Date.now() + 10 * 60 * 1000; // 10분 타임아웃
        const poll = async (): Promise<void> => {
          await new Promise(r => setTimeout(r, 5000));
          if (Date.now() > deadline) {
            throw new Error("이미지 생성 시간 초과 (10분). 더 빠른 엔진(gemini-flash)으로 재시도해 주세요.");
          }
          const state = await api.pipeline.getStage(projectId);
          if (state.current_step === "render_done" || (state.image_urls?.length ?? 0) > 0) {
            const ts = Date.now();
            setStage(prev => ({
              ...prev,
              current_step: "render_done",
              image_urls: (state.image_urls as string[]).map((u: string) => `${u}?t=${ts}`),
              thumbnail_url: state.thumbnail_url ?? prev.thumbnail_url,
            }));
            return;
          }
          if (state.current_step === "render_failed") {
            const errMsg = (state as Record<string, unknown>).render_error as string | undefined;
            throw new Error(`이미지 생성 실패: ${errMsg ?? "알 수 없는 오류"}`);
          }
          return poll();
        };
        await poll();
      } else {
        // 동기 모드(인라인): 결과 바로 반환
        setStage(prev => ({
          ...prev,
          current_step: "render_done",
          image_urls: (res.image_urls as string[]).map((u: string) => `${u}?t=${Date.now()}`),
          thumbnail_url: res.thumbnail_url ?? prev.thumbnail_url,
        }));
      }
      await loadProject();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "이미지 생성 실패");
    } finally {
      stepTimers.forEach(clearTimeout);
      setLoading(null);
      setImageStep("");
    }
  };

  const regenerateImage = async (slideIndex: number) => {
    setLoading(`regen_${slideIndex}`);
    setError("");
    try {
      const res = await api.pipeline.regenerateImage(projectId, slideIndex, videoPlatform);
      // cache-bust: append timestamp so browser doesn't serve old image
      const bustUrl = `${res.image_url}?t=${Date.now()}`;
      setStage(prev => {
        const urls = [...prev.image_urls];
        urls[slideIndex] = bustUrl;
        return { ...prev, image_urls: urls };
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : `슬라이드 ${slideIndex + 1} 재생성 실패`);
    } finally {
      setLoading(null);
    }
  };

  const requestRewrite = async () => {
    if (!rewritePanel || !rewritePanel.correctionIntent.trim()) return;
    setRewritePanel(prev => prev ? { ...prev, loading: true } : prev);
    try {
      const res = await api.pipeline.rewriteFramePrompt(
        projectId,
        rewritePanel.slideIndex,
        rewritePanel.correctionIntent,
        videoPlatform,
      );
      setRewritePanel(prev => prev ? { ...prev, rewrittenPrompt: res.rewritten_prompt, loading: false } : prev);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "프롬프트 재작성 실패");
      setRewritePanel(prev => prev ? { ...prev, loading: false } : prev);
    }
  };

  const confirmRewrite = async () => {
    if (!rewritePanel?.rewrittenPrompt) return;
    setRewritePanel(prev => prev ? { ...prev, loading: true } : prev);
    try {
      const res = await api.pipeline.confirmFramePrompt(
        projectId,
        rewritePanel.slideIndex,
        rewritePanel.rewrittenPrompt,
        videoPlatform,
        true,
      );
      // image_urls + image_prompts 동시 업데이트
      const frameIdx = rewritePanel.slideIndex;
      setStage(prev => {
        const updates: Partial<typeof prev> = {};
        if (res.image_url) {
          const bustUrl = `${res.image_url}?t=${Date.now()}`;
          const urls = [...prev.image_urls];
          urls[frameIdx] = bustUrl;
          updates.image_urls = urls;
        }
        const prompts = [...(prev.image_prompts ?? [])];
        prompts[frameIdx] = rewritePanel.rewrittenPrompt!;
        updates.image_prompts = prompts;
        return { ...prev, ...updates };
      });
      setRewritePanel(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "프롬프트 확정 실패");
      setRewritePanel(prev => prev ? { ...prev, loading: false } : prev);
    }
  };

  const runVideo = async () => {
    setLoading("video");
    setError("");
    try {
      const res = await api.pipeline.runVideo(projectId, videoPlatform, ttsPlatform, bgmCategory);
      if (res.step === "video_processing") {
        // Celery 모드: 백그라운드 처리 시작 — 폴링으로 완료 감지
        setStage(prev => ({
          ...prev,
          current_step: "video_processing",
          video: { platform: videoPlatform, status: "processing", full_video_url: null, shorts_video_url: null, duration: null, clips_count: 0 },
        }));
      } else {
        // 동기 폴백 (Redis 없을 때)
        setStage(prev => ({
          ...prev,
          current_step: "video_done",
          video: res,
        }));
        await loadProject();
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "영상 제작 실패");
    } finally {
      setLoading(null);
    }
  };

  const runPublish = async (dryRun: boolean) => {
    setLoading(dryRun ? "publish_dry" : "publish_live");
    setError("");
    try {
      const res = await api.pipeline.publish(projectId, publishPlatform, dryRun);
      setPublishResult(res);
      if (!dryRun) {
        setStage(prev => ({ ...prev, current_step: "publish_done" }));
        await loadProject();
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "발행 실패");
    } finally {
      setLoading(null);
    }
  };

  /* ─── 렌더 헬퍼 ─────────────────────────────────────────── */

  if (!project) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-full py-24 text-muted-foreground">로딩 중...</div>
      </AppShell>
    );
  }

  const currentStepIdx = stepIndex(stage.current_step);

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 py-6">
        {/* 프로젝트 헤더 */}
        <div className="mb-4">
          <div className="flex items-center justify-between gap-3 mb-1">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xl">{MARKET_FLAGS[project.market]}</span>
              <h1 className="text-lg font-bold truncate">{project.topic}</h1>
            </div>
            <button
              onClick={async () => {
                if (!confirm("프로젝트를 삭제하시겠습니까?")) return;
                await api.projects.delete(projectId);
                router.push("/dashboard");
              }}
              className="flex-shrink-0 text-xs text-muted-foreground hover:text-red-500 transition-colors"
            >
              삭제
            </button>
          </div>
          <div className="flex gap-1.5 flex-wrap">
            {project.target_platforms?.map((p) => (
              <Badge key={p} variant="outline" className="text-xs">{p}</Badge>
            ))}
          </div>
        </div>

        {/* 전체 파이프라인 진행 상황 */}
        <div className="border rounded-xl px-3 mb-6 bg-muted/10">
          <PipelineProgress currentIdx={currentStepIdx} />
        </div>

        {/* 에러 */}
        {error && (
          <div className="mb-4 p-4 bg-red-500/10 text-red-500 rounded-lg text-sm border border-red-500/20">
            {error}
          </div>
        )}

        {/* ── Step 1: 리서치 ─────────────────────────────────── */}
        <StepCard
          step={1}
          title="리서치"
          icon="🔍"
          done={currentStepIdx >= 1}
          active={currentStepIdx === 0}
        >
          {stage.research ? (
            <div className="space-y-4">
              {/* 키워드 */}
              <div>
                <div className="text-xs text-muted-foreground mb-2 font-medium uppercase tracking-wide">발견된 키워드 {stage.research.keywords.length}개</div>
                <div className="flex flex-wrap gap-2">
                  {stage.research.keywords.map((kw, i) => (
                    <span key={i} className="text-xs bg-primary/10 text-primary px-2 py-1 rounded-md">{kw}</span>
                  ))}
                </div>
              </div>

              {/* 윈닝 포뮬라 */}
              {stage.research.winning_formula && (
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Winning Formula</div>
                  <div className="grid grid-cols-1 gap-2">
                    {stage.research.winning_formula.hook_patterns.slice(0, 3).map((p, i) => (
                      <div key={i} className="flex gap-2 p-3 bg-muted/30 rounded-lg">
                        <span className="text-muted-foreground text-xs shrink-0 mt-0.5">훅 {i+1}</span>
                        <span className="text-sm">{p}</span>
                      </div>
                    ))}
                    {stage.research.winning_formula.content_gaps.slice(0, 2).map((gap, i) => (
                      <div key={i} className="flex gap-2 p-3 bg-green-500/5 border border-green-500/20 rounded-lg">
                        <span className="text-green-600 text-xs shrink-0 mt-0.5">빈틈 {i+1}</span>
                        <span className="text-sm">{gap}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-2">
                <Button size="sm" onClick={runResearch} disabled={!!loading} variant="outline">
                  {loading === "research" ? "리서치 중..." : "다시 리서치"}
                </Button>
                {currentStepIdx < 2 && (
                  <Button size="sm" onClick={runHooks} disabled={!!loading}>
                    {loading === "hooks" ? "훅 생성 중..." : "훅 생성 →"}
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <Button onClick={runResearch} disabled={!!loading}>
              {loading === "research" ? "리서치 중... (30초 소요)" : "리서치 시작"}
            </Button>
          )}
        </StepCard>

        {/* ── Step 2: 훅 선택 ─────────────────────────────────── */}
        <StepCard
            step={2}
            title="훅 선택"
            icon="🎣"
            done={currentStepIdx >= 2}
            active={currentStepIdx === 1}
            locked={currentStepIdx < 1}
            lockedMsg="리서치 완료 후 활성화됩니다."
          >
            {stage.hooks ? (
              <div className="space-y-4">
                <div className="text-sm text-muted-foreground">
                  훅을 선택하면 이 훅을 기반으로 슬라이드가 작성됩니다.
                </div>
                <div className="space-y-2">
                  {stage.hooks.hooks.map((hook, i) => (
                    <button
                      key={i}
                      onClick={() => selectHook(i)}
                      className={`w-full text-left p-4 rounded-xl border-2 transition-all ${
                        stage.selected_hook_index === i
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/40 bg-muted/20"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`w-6 h-6 rounded-full border-2 flex-shrink-0 mt-0.5 flex items-center justify-center text-xs font-bold ${
                          stage.selected_hook_index === i ? "border-primary bg-primary text-white" : "border-border"
                        }`}>
                          {stage.selected_hook_index === i ? "✓" : i + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium leading-relaxed mb-1">{hook.text}</div>
                          <div className="flex gap-2 flex-wrap">
                            <span className="text-xs bg-muted px-2 py-0.5 rounded">
                              {HOOK_STYLE_LABELS[hook.style] || hook.style}
                            </span>
                            {hook.platform_fit.slice(0, 2).map(p => (
                              <span key={p} className="text-xs text-muted-foreground">{p}</span>
                            ))}
                            {i === stage.hooks!.recommended_hook_index && (
                              <span className="text-xs bg-yellow-500/10 text-yellow-600 px-2 py-0.5 rounded">⭐ 추천</span>
                            )}
                            {hook.style === "data" && hook.score < 0.5 && (
                              <span className="text-xs bg-red-500/10 text-red-500 px-2 py-0.5 rounded" title="수치가 리서치 데이터에서 확인되지 않음">⚠️ 미검증 수치</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={runHooks} disabled={!!loading} variant="outline">
                    {loading === "hooks" ? "생성 중..." : "다시 생성"}
                  </Button>
                  {currentStepIdx < 3 && (
                    <Button size="sm" onClick={() => runWrite(false)} disabled={!!loading}>
                      {loading === "write" ? (writeStep || "글쓰기 중...") : "이 훅으로 글쓰기 →"}
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <Button onClick={runHooks} disabled={!!loading}>
                {loading === "hooks" ? "훅 생성 중..." : "훅 생성"}
              </Button>
            )}
          </StepCard>

        {/* ── Step 3: 콘텐츠 확인/편집 ────────────────────────── */}
          <StepCard
            step={3}
            title="콘텐츠 확인 / 편집"
            icon="✍️"
            done={currentStepIdx >= 3}
            active={currentStepIdx === 2}
            locked={currentStepIdx < 2}
            lockedMsg="훅 선택 완료 후 활성화됩니다."
          >
            {stage.content ? (
              <div className="space-y-4">
                {stage.quality_score !== null && (
                  <div className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg">
                    <span className={`text-2xl font-bold ${
                      stage.quality_score >= 80 ? "text-green-500" :
                      stage.quality_score >= 60 ? "text-yellow-500" : "text-red-500"
                    }`}>{stage.quality_score}</span>
                    <span className="text-sm text-muted-foreground">품질 점수 / 100</span>
                  </div>
                )}

                {/* 팩트 체크 결과 */}
                {stage.fact_check && (
                  <div className={`rounded-xl border overflow-hidden ${
                    stage.fact_check.disputed_count > 0
                      ? "border-red-500/30"
                      : stage.fact_check.uncertain_count > 0
                      ? "border-yellow-500/30"
                      : "border-green-500/30"
                  }`}>
                    <div className={`flex items-center justify-between px-3 py-2 ${
                      stage.fact_check.disputed_count > 0
                        ? "bg-red-500/10"
                        : stage.fact_check.uncertain_count > 0
                        ? "bg-yellow-500/10"
                        : "bg-green-500/10"
                    }`}>
                      <div className="flex items-center gap-2">
                        <span>{stage.fact_check.disputed_count > 0 ? "⚠️" : stage.fact_check.uncertain_count > 0 ? "🔍" : "✅"}</span>
                        <span className="text-xs font-medium">팩트 체크</span>
                        <div className="flex gap-1">
                          {stage.fact_check.disputed_count > 0 && (
                            <span className="text-xs bg-red-500/20 text-red-500 px-1.5 py-0.5 rounded">
                              오류 {stage.fact_check.disputed_count}
                            </span>
                          )}
                          {stage.fact_check.uncertain_count > 0 && (
                            <span className="text-xs bg-yellow-500/20 text-yellow-600 px-1.5 py-0.5 rounded">
                              불확실 {stage.fact_check.uncertain_count}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="p-3 space-y-2">
                      <p className="text-xs text-muted-foreground">{stage.fact_check.summary}</p>
                      {stage.fact_check.claims.filter(c => c.status !== "confirmed").map((c, i) => (
                        <div key={i} className={`p-2 rounded-lg text-xs ${
                          c.status === "disputed"
                            ? "bg-red-500/10 border border-red-500/20"
                            : "bg-yellow-500/10 border border-yellow-500/10"
                        }`}>
                          <div className="font-medium mb-0.5">
                            {c.status === "disputed" ? "❌" : "❓"} {c.claim}
                          </div>
                          <div className="text-muted-foreground">{c.note}</div>
                        </div>
                      ))}
                      {(stage.fact_check.disputed_count > 0 || stage.fact_check.uncertain_count > 0) && (
                        <Button
                          size="sm"
                          variant={stage.fact_check.disputed_count > 0 ? "destructive" : "outline"}
                          className="mt-2 w-full"
                          onClick={() => runWrite(true)}
                          disabled={!!loading}
                        >
                          {loading === "write_fix"
                            ? (writeStep || "팩트 수정 후 재작성 중...")
                            : stage.fact_check.disputed_count > 0
                              ? `오류 ${stage.fact_check.disputed_count}개 + 불확실 ${stage.fact_check.uncertain_count}개 수정 후 재작성`
                              : `불확실 수치 ${stage.fact_check.uncertain_count}개 제거 후 재작성`}
                        </Button>
                      )}
                    </div>
                  </div>
                )}

                {/* 썸네일 키카피 */}
                {stage.content.thumbnail_text && (
                  <div className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-xl">
                    <div className="text-xs text-yellow-600 font-medium mb-1">🖼️ 썸네일 키카피</div>
                    <div className="font-semibold">{stage.content.thumbnail_text}</div>
                  </div>
                )}

                {stage.content.platform_contents.map((pc) => (
                  <div key={pc.platform} className="border rounded-xl overflow-hidden">
                    <div className="flex items-center justify-between p-3 bg-muted/40 border-b">
                      <Badge>{pc.platform}</Badge>
                      {editingPlatform !== pc.platform ? (
                        <Button size="sm" variant="outline" onClick={() => startEditSlides(pc)}>
                          슬라이드 편집
                        </Button>
                      ) : (
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => setEditingPlatform(null)}>취소</Button>
                          <Button size="sm" onClick={saveSlides} disabled={savingSlides}>
                            {savingSlides ? "저장 중..." : "저장"}
                          </Button>
                        </div>
                      )}
                    </div>
                    <div className="p-4">
                      {/* 훅 */}
                      <div className="mb-3 p-3 bg-primary/5 border border-primary/20 rounded-lg">
                        <div className="text-xs text-primary mb-1 font-medium">훅</div>
                        <div className="font-semibold">{pc.hook}</div>
                      </div>

                      {/* 슬라이드 편집 or 표시 */}
                      {editingPlatform === pc.platform ? (
                        <div className="space-y-3">
                          <div className="text-xs text-muted-foreground font-medium mb-1">
                            슬라이드 텍스트 + 이미지 방향 편집 ({editedSlides.length}개)
                          </div>
                          {editedSlides.map((slide, k) => (
                            <div key={k} className="border border-border rounded-xl overflow-hidden">
                              <div className="flex gap-2 p-3 bg-muted/20">
                                <span className="text-xs text-muted-foreground font-mono w-6 shrink-0 mt-2">{k+1}</span>
                                <textarea
                                  value={slide}
                                  onChange={(e) => {
                                    const updated = [...editedSlides];
                                    updated[k] = e.target.value;
                                    setEditedSlides(updated);
                                  }}
                                  rows={3}
                                  className="flex-1 p-2 text-sm bg-background border border-border rounded-lg resize-y focus:outline-none focus:ring-1 focus:ring-primary"
                                />
                              </div>
                              <div className="px-3 pb-3 pt-1 bg-purple-500/5 border-t border-purple-500/10">
                                <div className="text-xs text-purple-400 mb-1 flex items-center gap-1">
                                  🎨 이미지 방향
                                </div>
                                <textarea
                                  value={editedImagePrompts[k] || ""}
                                  onChange={(e) => {
                                    const updated = [...editedImagePrompts];
                                    updated[k] = e.target.value;
                                    setEditedImagePrompts(updated);
                                  }}
                                  rows={2}
                                  placeholder="예: 링차트 93%, 어두운 배경 / 5개 아이콘 목록 / A vs B 비교표"
                                  className="w-full p-2 text-xs bg-background border border-purple-500/20 rounded-lg resize-y focus:outline-none focus:ring-1 focus:ring-purple-500 text-muted-foreground"
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between mb-1">
                            <div className="text-xs text-muted-foreground font-medium">
                              본문 ({pc.body.length}개 {pc.platform === "instagram" ? "슬라이드" : pc.platform === "x" ? "트윗" : "파트"})
                            </div>
                            {(pc.image_prompts?.length ?? 0) > 0 && (
                              <button
                                onClick={() => setExpandedPrompts(prev => ({ ...prev, [pc.platform]: !prev[pc.platform] }))}
                                className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1"
                              >
                                🎨 이미지 방향 {expandedPrompts[pc.platform] ? "숨기기" : "보기"}
                              </button>
                            )}
                          </div>
                          {pc.body.map((part, k) => (
                            <div key={k} className="rounded-xl border border-border overflow-hidden">
                              <div className="flex gap-3 p-3 bg-muted/20">
                                <span className="text-xs text-muted-foreground font-mono shrink-0 mt-0.5">
                                  {String(k + 1).padStart(2, "0")}
                                </span>
                                <div className="text-sm leading-relaxed whitespace-pre-wrap">{part}</div>
                              </div>
                              {expandedPrompts[pc.platform] && pc.image_prompts?.[k] && (
                                <div className="px-3 py-2 bg-purple-500/5 border-t border-purple-500/10">
                                  <span className="text-xs text-purple-400 mr-2">🎨</span>
                                  <span className="text-xs text-muted-foreground">{pc.image_prompts[k]}</span>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* 이미지 방향 프롬프트 뷰어 (글쓰기 단계) */}
                      {!editingPlatform && (pc.image_prompts?.length ?? 0) > 0 && (
                        <details className="mt-3 border rounded-lg overflow-hidden">
                          <summary className="px-3 py-2 bg-purple-500/5 border-purple-500/10 text-xs font-medium cursor-pointer hover:bg-purple-500/10 select-none text-purple-400">
                            🎨 이미지 방향 프롬프트 ({pc.image_prompts!.length}개)
                          </summary>
                          <div className="divide-y max-h-48 overflow-y-auto">
                            {pc.image_prompts!.map((p, k) => (
                              <div key={k} className="px-3 py-2 bg-muted/10 flex gap-2">
                                <span className="text-xs text-muted-foreground font-mono shrink-0">{k+1}</span>
                                <span className="text-xs text-muted-foreground break-all">{p}</span>
                              </div>
                            ))}
                          </div>
                        </details>
                      )}

                      {/* CTA + 해시태그 */}
                      <div className="mt-3 flex flex-wrap gap-2 items-center">
                        {pc.cta && (
                          <span className="text-xs bg-green-500/10 text-green-600 px-2 py-1 rounded">
                            CTA: {pc.cta.slice(0, 30)}…
                          </span>
                        )}
                        {pc.hashtags.slice(0, 3).map((tag, j) => (
                          <span key={j} className="text-xs bg-primary/10 text-primary px-2 py-1 rounded">
                            #{tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}

                <div className="flex gap-2">
                  <Button size="sm" onClick={() => runWrite(false)} disabled={!!loading} variant="outline">
                    {loading === "write" ? (writeStep || "재작성 중...") : "다시 작성"}
                  </Button>
                  {currentStepIdx < 4 && (
                    <Button size="sm" onClick={() => runRender(videoPlatform)} disabled={!!loading}>
                      {loading === "render" ? (imageStep || "씬 이미지 생성 중...") : "씬 이미지 생성 →"}
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <Button onClick={() => runWrite(false)} disabled={!!loading}>
                {loading === "write" ? (writeStep || "글쓰기 중...") : "글쓰기 시작"}
              </Button>
            )}
          </StepCard>

        {/* ── Step 4: 씬 이미지 생성 ──────────────────────── */}
          <StepCard
            step={4}
            title="씬 이미지 생성"
            icon="🖼️"
            done={currentStepIdx >= 4}
            active={currentStepIdx === 3}
            locked={currentStepIdx < 3}
            lockedMsg="글쓰기 완료 후 활성화됩니다."
          >
            {/* 플랫폼 선택 (비율 결정) */}
            <div className="mb-4">
              <div className="text-xs text-muted-foreground mb-2 font-medium">플랫폼 (이미지 비율)</div>
              <div className="flex flex-wrap gap-2">
                {[
                  { key: "youtube", label: "📺 YouTube (16:9)" },
                  { key: "youtube_shorts", label: "⚡ Shorts (9:16)" },
                  { key: "instagram", label: "📸 Instagram (1:1)" },
                  { key: "tiktok", label: "🎵 TikTok (9:16)" },
                ].map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => setVideoPlatform(key)}
                    className={`px-3 py-1.5 rounded-lg text-sm border transition-all ${
                      videoPlatform === key
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-muted/20 text-muted-foreground hover:border-primary/40"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {(() => {
              const targetPlatform = videoPlatform === "youtube_shorts" ? "youtube" : videoPlatform;
              const renderPc =
                stage.content?.platform_contents.find(c => c.platform === targetPlatform) ??
                stage.content?.platform_contents[0];

              return stage.image_urls.length > 0 ? (
                <div className="space-y-3">
                  <div className="text-xs text-muted-foreground font-medium">
                    씬 이미지 {stage.image_urls.length}장 생성 완료
                  </div>

                  {stage.image_urls.map((url, k) => (
                    <div key={k} className="border rounded-xl overflow-hidden">
                      {/* 씬 헤더 */}
                      <div className="flex items-center justify-between px-3 py-2 bg-muted/30 border-b">
                        <span className="text-xs text-muted-foreground font-mono">씬 {k + 1}</span>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => {
                              const currentPrompt = stage.image_prompts[k] ?? "";
                              setRewritePanel({
                                slideIndex: k,
                                correctionIntent: "",
                                rewrittenPrompt: null,
                                originalPrompt: currentPrompt,
                                loading: false,
                              });
                            }}
                            disabled={!!loading}
                            className="text-xs text-purple-400 hover:underline disabled:opacity-50"
                          >
                            ✏️ 프롬프트 수정
                          </button>
                          <button
                            onClick={() => regenerateImage(k)}
                            disabled={!!loading}
                            className="text-xs text-primary hover:underline disabled:opacity-50"
                          >
                            {loading === `regen_${k}` ? "재생성 중..." : "🔄 재생성"}
                          </button>
                        </div>
                      </div>

                      {/* 프롬프트 협업 수정 패널 */}
                      {rewritePanel?.slideIndex === k && (
                        <div className="px-3 py-3 bg-purple-500/5 border-b border-purple-500/20 space-y-2">
                          <div className="text-xs font-medium text-purple-400">프롬프트 협업 수정</div>
                          {rewritePanel.originalPrompt && (
                            <div className="text-xs text-muted-foreground bg-muted/30 rounded p-2 break-words">
                              <span className="font-medium">현재:</span> {rewritePanel.originalPrompt}
                            </div>
                          )}
                          <input
                            className="w-full text-xs border rounded px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-purple-500"
                            placeholder="수정 요청 입력 (예: 더 어둡게, 카메라를 낮게, make it more dramatic)"
                            value={rewritePanel.correctionIntent}
                            onChange={e => setRewritePanel(prev => prev ? { ...prev, correctionIntent: e.target.value } : prev)}
                            onKeyDown={e => e.key === "Enter" && requestRewrite()}
                          />
                          {rewritePanel.rewrittenPrompt && (
                            <div className="text-xs text-green-400 bg-green-500/5 rounded p-2 break-words">
                              <span className="font-medium">재작성:</span> {rewritePanel.rewrittenPrompt}
                            </div>
                          )}
                          <div className="flex gap-2">
                            {!rewritePanel.rewrittenPrompt ? (
                              <button
                                onClick={requestRewrite}
                                disabled={rewritePanel.loading || !rewritePanel.correctionIntent.trim()}
                                className="text-xs px-3 py-1 rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50"
                              >
                                {rewritePanel.loading ? "재작성 중..." : "AI 재작성"}
                              </button>
                            ) : (
                              <>
                                <button
                                  onClick={confirmRewrite}
                                  disabled={rewritePanel.loading}
                                  className="text-xs px-3 py-1 rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
                                >
                                  {rewritePanel.loading ? "적용 중..." : "확정 + 이미지 재생성"}
                                </button>
                                <button
                                  onClick={() => setRewritePanel(prev => prev ? { ...prev, rewrittenPrompt: null } : prev)}
                                  className="text-xs px-3 py-1 rounded border hover:bg-muted"
                                >
                                  다시 수정
                                </button>
                              </>
                            )}
                            <button
                              onClick={() => setRewritePanel(null)}
                              className="text-xs px-3 py-1 rounded border hover:bg-muted ml-auto"
                            >
                              닫기
                            </button>
                          </div>
                        </div>
                      )}

                      {/* 이미지 + 텍스트 */}
                      <div className="flex">
                        <img
                          src={`${API_BASE}${url}`}
                          alt={`씬 ${k + 1}`}
                          className="w-1/2 flex-shrink-0 object-cover"
                          style={{ maxHeight: "200px" }}
                        />
                        <div className="flex-1 p-3 space-y-2 min-w-0 overflow-hidden">
                          <div className="text-sm leading-relaxed whitespace-pre-wrap">
                            {renderPc?.body[k] ?? ""}
                          </div>
                          {/* 실제 Imagen 프롬프트 (씬 기준, stage.image_prompts와 1:1 대응) */}
                          {stage.image_prompts[k] && (
                            <div className="text-xs text-purple-400 bg-purple-500/5 rounded p-2 break-words font-mono">
                              🎨 {stage.image_prompts[k]}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}

                  {/* 썸네일 이미지 */}
                  {stage.thumbnail_url && (
                    <div className="border border-yellow-500/30 rounded-xl overflow-hidden">
                      <div className="flex items-center justify-between px-3 py-2 bg-yellow-500/10 border-b border-yellow-500/20">
                        <span className="text-xs text-yellow-600 font-medium">🖼️ 썸네일</span>
                        <span className="text-xs text-muted-foreground">{stage.content?.thumbnail_text}</span>
                      </div>
                      <img
                        src={`${API_BASE}${stage.thumbnail_url}`}
                        alt="썸네일"
                        className="w-full object-cover"
                        style={{ maxHeight: "200px" }}
                      />
                    </div>
                  )}

                  <Button
                    size="sm"
                    onClick={() => runRender(videoPlatform)}
                    disabled={!!loading}
                    variant="outline"
                  >
                    {loading === "render" ? (imageStep || "재생성 중...") : "전체 이미지 재생성"}
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex gap-2 text-xs">
                    <span className="text-muted-foreground self-center">이미지 엔진:</span>
                    {(["gpt-image-1", "gemini-pro", "gemini-flash", "imagen", "dalle"] as const).map(p => (
                      <button
                        key={p}
                        onClick={() => setImageProvider(p)}
                        className={`px-2 py-1 rounded border text-xs ${imageProvider === p ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-muted"}`}
                      >
                        {p === "gpt-image-1" ? "GPT-image-1 ✨" : p === "gemini-pro" ? "Gemini 2.5 Pro" : p === "gemini-flash" ? "Gemini 2.0 Flash" : p === "imagen" ? "Imagen 4" : "DALL-E 3"}
                      </button>
                    ))}
                  </div>
                  <Button onClick={() => runRender(videoPlatform)} disabled={!!loading}>
                    {loading === "render" ? (imageStep || "씬 이미지 생성 중...") : "🖼️ 씬 이미지 생성"}
                  </Button>
                  {loading === "render" && imageStep && (
                    <div className="text-xs text-muted-foreground animate-pulse">{imageStep}</div>
                  )}
                </div>
              );
            })()}
          </StepCard>

        {/* ── Step 5: 영상 제작 (Veo + TTS) ──────────────────── */}
          <StepCard
            step={5}
            title="영상 제작"
            icon="🎬"
            done={stage.current_step === "video_done" || currentStepIdx >= 7}
            active={currentStepIdx >= 4 && currentStepIdx < 7}
            locked={currentStepIdx < 4}
            lockedMsg="이미지 생성 완료 후 활성화됩니다."
          >
            {stage.video?.status === "processing" ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3 p-4 bg-muted/20 rounded-lg border border-blue-500/20">
                  <div className="text-2xl animate-spin">⏳</div>
                  <div className="flex-1">
                    <div className="font-medium text-blue-500">영상 제작 중...</div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {videoLog?.step ?? "처리 중"} · 10초마다 자동 갱신
                    </div>
                  </div>
                </div>
                {videoLog && videoLog.lines.length > 0 && (
                  <div className="rounded-lg border bg-black/80 p-3 max-h-48 overflow-y-auto font-mono">
                    {videoLog.lines.slice(-15).map((line, i) => {
                      const color = line.includes("ERROR") || line.includes("error") ? "text-red-400"
                        : line.includes("완료") || line.includes("성공") ? "text-green-400"
                        : line.includes("INFO") ? "text-blue-300"
                        : "text-gray-300";
                      // 타임스탬프 + 모듈명 제거하고 메시지만 표시
                      const msg = line.replace(/^.*\| (INFO|WARNING|ERROR)\s+\|[^|]+\|\s*/, "").trim();
                      return <div key={i} className={`text-[10px] leading-5 ${color}`}>{msg || line}</div>;
                    })}
                  </div>
                )}
              </div>
            ) : stage.video && !stage.video.error ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3 p-3 bg-muted/30 rounded-lg">
                  <span className="text-2xl">🎬</span>
                  <div>
                    <div className="font-medium">{stage.video.platform} 영상 완성</div>
                    <div className="text-xs text-muted-foreground">
                      {stage.video.clips_count}개 씬 · {stage.video.duration}초
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  {stage.video.full_video_url && (
                    <div className="border rounded-xl p-3">
                      <div className="text-xs text-muted-foreground mb-2 font-medium">풀 영상</div>
                      <video
                        src={`${API_BASE}${stage.video.full_video_url}`}
                        controls
                        preload="metadata"
                        className="w-full rounded-lg max-h-64"
                      />
                      <a
                        href={`${API_BASE}${stage.video.full_video_url}`}
                        download
                        className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        ⬇️ 다운로드
                      </a>
                    </div>
                  )}
                  {stage.video.shorts_video_url && (
                    <div className="border rounded-xl p-3">
                      <div className="text-xs text-muted-foreground mb-2 font-medium">쇼츠 버전 (앞 3씬)</div>
                      <video
                        src={`${API_BASE}${stage.video.shorts_video_url}`}
                        controls
                        preload="metadata"
                        className="w-full rounded-lg max-h-64"
                      />
                      <a
                        href={`${API_BASE}${stage.video.shorts_video_url}`}
                        download
                        className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        ⬇️ 쇼츠 다운로드
                      </a>
                    </div>
                  )}
                </div>

                {/* 영상 모션 프롬프트 뷰어 */}
                {stage.frame_motion_prompts.length > 0 && (
                  <details className="border rounded-lg overflow-hidden">
                    <summary className="px-3 py-2 bg-muted/30 text-xs font-medium cursor-pointer hover:bg-muted/50 select-none">
                      🎬 Kling AI 모션 프롬프트 보기 ({stage.frame_motion_prompts.length}개 샷)
                    </summary>
                    <div className="divide-y max-h-64 overflow-y-auto">
                      {stage.frame_motion_prompts.map((p, k) => (
                        <div key={k} className="px-3 py-2 bg-muted/10">
                          <span className="text-xs text-muted-foreground font-mono mr-2">샷 {k+1}</span>
                          <span className="text-xs font-mono break-all">{p}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                <Button size="sm" onClick={runVideo} disabled={!!loading} variant="outline">
                  {loading === "video" ? "재생성 중... (5~10분)" : "영상 재생성"}
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                {stage.video?.error && (
                  <div className="p-3 bg-red-500/10 text-red-500 rounded-lg text-sm">
                    {stage.video.error}
                  </div>
                )}
                <div className="space-y-3">
                  {/* 나레이션 선택 */}
                  <div>
                    <div className="text-xs text-muted-foreground mb-2 font-medium">나레이션</div>
                    <div className="flex gap-2">
                      {[
                        { key: "none", label: "없음" },
                        { key: "gemini", label: "🤖 Gemini TTS (무료)" },
                        { key: "elevenlabs", label: "🎙️ ElevenLabs (고품질)" },
                      ].map(({ key, label }) => (
                        <button
                          key={key}
                          onClick={() => setTtsPlatform(key as "none" | "gemini" | "elevenlabs")}
                          className={`px-3 py-1.5 rounded-lg text-sm border transition-all ${
                            ttsPlatform === key
                              ? "border-primary bg-primary/10 text-primary"
                              : "border-border bg-muted/20 text-muted-foreground hover:border-primary/40"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* BGM 선택 */}
                  <div>
                    <div className="text-xs text-muted-foreground mb-2 font-medium">배경음악 (BGM)</div>
                    <div className="flex gap-2 flex-wrap">
                      {[
                        { key: "none",      label: "없음" },
                        { key: "cinematic", label: "🎻 Cinematic (역사/다큐)" },
                        { key: "ambient",   label: "🌊 Ambient (잔잔)" },
                        { key: "upbeat",    label: "✨ Upbeat (경쾌)" },
                        { key: "dramatic",  label: "⚡ Dramatic (긴장)" },
                      ].map(({ key, label }) => (
                        <button
                          key={key}
                          onClick={() => setBgmCategory(key as typeof bgmCategory)}
                          className={`px-3 py-1.5 rounded-lg text-sm border transition-all ${
                            bgmCategory === key
                              ? "border-primary bg-primary/10 text-primary"
                              : "border-border bg-muted/20 text-muted-foreground hover:border-primary/40"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="p-3 bg-muted/20 rounded-lg text-xs text-muted-foreground space-y-1">
                    <div className="font-medium text-foreground mb-1">플랫폼: {videoPlatform}</div>
                    <div>🎬 Veo로 슬라이드당 씬 클립 생성</div>
                    {ttsPlatform !== "none" && <div>🎙️ {ttsPlatform === "gemini" ? "Gemini TTS" : "ElevenLabs"} 나레이션 생성</div>}
                    {bgmCategory !== "none" && <div>🎵 {bgmCategory} BGM 믹싱</div>}
                    <div>🔗 moviepy로 클립 + 나레이션 조립</div>
                    <div className="text-yellow-500">⏱️ {ttsPlatform !== "none" ? "나레이션 포함 " : ""}슬라이드 수에 따라 5~15분 소요</div>
                  </div>
                </div>
                <Button onClick={runVideo} disabled={!!loading}>
                  {loading === "video" ? "영상 제작 중... (5~15분 소요)" : "🎬 영상 제작 시작"}
                </Button>
              </div>
            )}
          </StepCard>

        {/* ── Step 6: 발행 ─────────────────────────────────────── */}
          <StepCard
            step={6}
            title="발행"
            icon="🚀"
            done={stage.current_step === "publish_done"}
            active={currentStepIdx >= 3}
            locked={currentStepIdx < 3}
            lockedMsg="글쓰기 완료 후 드라이런 발행이 가능합니다."
          >
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium w-20">플랫폼</label>
                <select
                  className="border rounded px-2 py-1 text-sm bg-background"
                  value={publishPlatform}
                  onChange={e => setPublishPlatform(e.target.value)}
                >
                  <option value="youtube">YouTube</option>
                  <option value="instagram">Instagram</option>
                  <option value="x">X (Twitter)</option>
                </select>
              </div>

              {publishResult && (
                <div className="rounded border p-3 space-y-2 text-sm">
                  {publishResult.results.map((r, i) => (
                    <div key={i} className={`flex items-center gap-2 ${r.success ? "text-green-600" : "text-red-500"}`}>
                      <span>{r.success ? "✓" : "✗"}</span>
                      <span className="font-medium">{r.platform}</span>
                      {r.post_url && (
                        <a href={r.post_url} target="_blank" rel="noopener noreferrer" className="underline truncate max-w-[200px]">
                          {r.post_url}
                        </a>
                      )}
                      {r.error && <span className="text-muted-foreground">{r.error}</span>}
                    </div>
                  ))}
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => runPublish(true)}
                  disabled={!!loading}
                >
                  {loading === "publish_dry" ? "확인 중..." : "드라이런 확인"}
                </Button>
                <Button
                  size="sm"
                  onClick={() => runPublish(false)}
                  disabled={!!loading}
                >
                  {loading === "publish_live" ? "발행 중..." : "🚀 실제 발행"}
                </Button>
              </div>
            </div>
          </StepCard>
      </div>
    </AppShell>
  );
}

/* ─── StepCard 컴포넌트 ─────────────────────────────────── */
// status: "done" | "active" | "locked"
// done   → 접힘(기본), 헤더 클릭으로 펼치기
// active → 항상 펼쳐짐, 강조 테두리
// locked → 흐릿하게, 자물쇠 아이콘, 내용 미표시

function StepCard({
  step,
  title,
  icon,
  done,
  active,
  locked,
  lockedMsg,
  children,
}: {
  step: number;
  title: string;
  icon: string;
  done: boolean;
  active: boolean;
  locked?: boolean;
  lockedMsg?: string;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(!done);

  // active가 되면 자동으로 펼쳐짐
  useEffect(() => {
    if (active && !done) setExpanded(true);
  }, [active, done]);

  const isLocked = locked && !done && !active;

  return (
    <div className="mb-3 relative pl-10">
      {/* 세로 연결선 */}
      <div className="absolute left-[18px] top-10 bottom-0 w-px bg-border" />

      {/* 스텝 배지 */}
      <div className={`absolute left-0 top-4 w-9 h-9 rounded-full border-2 flex items-center justify-center text-sm font-bold z-10 ${
        done
          ? "bg-green-500 border-green-500 text-white"
          : active
          ? "bg-primary border-primary text-white"
          : "bg-background border-border text-muted-foreground"
      }`}>
        {done ? "✓" : isLocked ? "○" : icon}
      </div>

      <Card className={`ml-2 transition-opacity ${isLocked ? "opacity-40" : ""} ${active ? "border-primary/30" : ""}`}>
        {/* 헤더 — done이면 클릭으로 접기/펼치기 */}
        <div
          className={`flex items-center justify-between px-5 py-3 ${done ? "cursor-pointer select-none hover:bg-muted/20" : ""}`}
          onClick={() => done && setExpanded(e => !e)}
        >
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground text-xs font-medium">Step {step}</span>
            <span className="font-semibold text-sm">{title}</span>
            {done && (
              <Badge variant="outline" className="text-green-600 border-green-500/40 text-xs">완료</Badge>
            )}
            {active && !done && (
              <Badge className="text-xs py-0">진행 중</Badge>
            )}
          </div>
          {done && (
            <span className="text-muted-foreground text-xs">{expanded ? "▲ 접기" : "▼ 결과 보기"}</span>
          )}
        </div>

        {/* 바디 */}
        {isLocked ? (
          <CardContent className="px-5 pb-4 pt-0">
            <p className="text-xs text-muted-foreground">{lockedMsg ?? "이전 단계를 완료하면 활성화됩니다."}</p>
          </CardContent>
        ) : (expanded || active) ? (
          <CardContent className="px-5 pb-5 pt-1 border-t">
            {children}
          </CardContent>
        ) : null}
      </Card>
    </div>
  );
}
