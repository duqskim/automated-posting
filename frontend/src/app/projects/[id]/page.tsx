"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

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
  platform_fit: string[];
}

interface PlatformContent {
  platform: string;
  hook: string;
  body: string[];
  caption: string;
  hashtags: string[];
  cta: string;
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
    platform_contents: PlatformContent[];
  } | null;
  image_urls: string[];
  quality_score: number | null;
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

const STEP_ORDER = ["idle", "research_done", "hooks_done", "write_done", "render_done"];

function stepIndex(step: string) {
  return STEP_ORDER.indexOf(step);
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
    quality_score: null,
  });
  const [loading, setLoading] = useState<string | null>(null); // 로딩 중인 스텝 이름
  const [error, setError] = useState("");

  // 편집 상태
  const [editingPlatform, setEditingPlatform] = useState<string | null>(null);
  const [editedSlides, setEditedSlides] = useState<string[]>([]);
  const [savingSlides, setSavingSlides] = useState(false);

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
      .then((data: StageState) => setStage(data))
      .catch(() => {});
  }, [loadProject, router, projectId]);

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

  const runWrite = async () => {
    setLoading("write");
    setError("");
    try {
      const res = await api.pipeline.runWrite(projectId);
      setStage(prev => ({
        ...prev,
        current_step: "write_done",
        content: res.content,
        quality_score: res.quality_score,
        image_urls: [],
      }));
      await loadProject();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "글쓰기 실패");
    } finally {
      setLoading(null);
    }
  };

  const startEditSlides = (platform: PlatformContent) => {
    setEditingPlatform(platform.platform);
    setEditedSlides([...platform.body]);
  };

  const saveSlides = async () => {
    if (!editingPlatform) return;
    setSavingSlides(true);
    try {
      await api.pipeline.saveSlides(projectId, editingPlatform, editedSlides);
      // 로컬 상태 업데이트
      setStage(prev => {
        if (!prev.content) return prev;
        return {
          ...prev,
          content: {
            ...prev.content,
            platform_contents: prev.content.platform_contents.map(pc =>
              pc.platform === editingPlatform ? { ...pc, body: editedSlides } : pc
            ),
          },
          image_urls: [], // 편집 후 이미지 무효화
        };
      });
      setEditingPlatform(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSavingSlides(false);
    }
  };

  const runRender = async () => {
    setLoading("render");
    setError("");
    try {
      const res = await api.pipeline.runRender(projectId);
      setStage(prev => ({
        ...prev,
        current_step: "render_done",
        image_urls: res.image_urls,
      }));
      await loadProject();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "이미지 생성 실패");
    } finally {
      setLoading(null);
    }
  };

  /* ─── 렌더 헬퍼 ─────────────────────────────────────────── */

  if (!project) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">로딩 중...</p>
      </div>
    );
  }

  const currentStepIdx = stepIndex(stage.current_step);

  return (
    <div className="min-h-screen bg-background">
      {/* 헤더 */}
      <header className="border-b sticky top-0 bg-background z-10">
        <div className="container mx-auto flex items-center justify-between h-14 px-4">
          <button onClick={() => router.push("/dashboard")} className="text-lg font-bold hover:opacity-80">
            Automated Posting
          </button>
          <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard")}>
            목록으로
          </Button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 max-w-3xl">
        {/* 프로젝트 헤더 */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xl">{MARKET_FLAGS[project.market]}</span>
            <h1 className="text-2xl font-bold">{project.topic}</h1>
          </div>
          <div className="flex gap-2 flex-wrap">
            {project.target_platforms?.map((p) => (
              <Badge key={p} variant="outline">{p}</Badge>
            ))}
          </div>
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
          active={currentStepIdx >= 0}
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
        {currentStepIdx >= 1 && (
          <StepCard
            step={2}
            title="훅 선택"
            icon="🎣"
            done={currentStepIdx >= 2}
            active={currentStepIdx >= 1}
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
                    <Button size="sm" onClick={runWrite} disabled={!!loading}>
                      {loading === "write" ? "글쓰기 중... (1분 소요)" : "이 훅으로 글쓰기 →"}
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
        )}

        {/* ── Step 3: 콘텐츠 확인/편집 ────────────────────────── */}
        {currentStepIdx >= 2 && (
          <StepCard
            step={3}
            title="콘텐츠 확인 / 편집"
            icon="✍️"
            done={currentStepIdx >= 3}
            active={currentStepIdx >= 2}
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
                        <div className="space-y-2">
                          <div className="text-xs text-muted-foreground font-medium mb-2">
                            슬라이드 텍스트 편집 ({editedSlides.length}개)
                          </div>
                          {editedSlides.map((slide, k) => (
                            <div key={k} className="flex gap-2">
                              <span className="text-xs text-muted-foreground font-mono w-6 shrink-0 mt-2">{k+1}</span>
                              <textarea
                                value={slide}
                                onChange={(e) => {
                                  const updated = [...editedSlides];
                                  updated[k] = e.target.value;
                                  setEditedSlides(updated);
                                }}
                                rows={3}
                                className="flex-1 p-3 text-sm bg-background border border-border rounded-lg resize-y focus:outline-none focus:ring-1 focus:ring-primary"
                              />
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <div className="text-xs text-muted-foreground font-medium">
                            본문 ({pc.body.length}개 {pc.platform === "instagram" ? "슬라이드" : pc.platform === "x" ? "트윗" : "파트"})
                          </div>
                          {pc.body.map((part, k) => (
                            <div key={k} className="flex gap-3 p-3 bg-muted/20 rounded-lg">
                              <span className="text-xs text-muted-foreground font-mono shrink-0 mt-0.5">
                                {String(k + 1).padStart(2, "0")}
                              </span>
                              <div className="text-sm leading-relaxed whitespace-pre-wrap">{part}</div>
                            </div>
                          ))}
                        </div>
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
                  <Button size="sm" onClick={runWrite} disabled={!!loading} variant="outline">
                    {loading === "write" ? "재작성 중..." : "다시 작성"}
                  </Button>
                  {currentStepIdx < 4 && (
                    <Button size="sm" onClick={runRender} disabled={!!loading}>
                      {loading === "render" ? "이미지 생성 중... (1~2분)" : "이미지 생성 →"}
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <Button onClick={runWrite} disabled={!!loading}>
                {loading === "write" ? "글쓰기 중... (1분 소요)" : "글쓰기 시작"}
              </Button>
            )}
          </StepCard>
        )}

        {/* ── Step 4: 이미지 확인 + 발행 ──────────────────────── */}
        {currentStepIdx >= 3 && (
          <StepCard
            step={4}
            title="이미지 확인 / 발행"
            icon="🖼️"
            done={currentStepIdx >= 4}
            active={currentStepIdx >= 3}
          >
            {stage.image_urls.length > 0 ? (
              <div className="space-y-4">
                {/* 이미지 캐러셀 */}
                <div>
                  <div className="text-xs text-muted-foreground mb-2 font-medium">
                    캐러셀 이미지 ({stage.image_urls.length}장)
                  </div>
                  <div className="flex gap-3 overflow-x-auto pb-2">
                    {stage.image_urls.map((url, k) => (
                      <img
                        key={k}
                        src={`${API_BASE}${url}`}
                        alt={`슬라이드 ${k + 1}`}
                        className="w-44 h-56 object-cover rounded-xl border flex-shrink-0 shadow-md"
                      />
                    ))}
                  </div>
                </div>

                <div className="flex gap-2 flex-wrap">
                  <Button size="sm" onClick={runRender} disabled={!!loading} variant="outline">
                    {loading === "render" ? "재생성 중..." : "이미지 재생성"}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => alert("발행 기능은 SNS 계정 연결 후 사용 가능합니다.\n\n/accounts 에서 계정을 먼저 연결해주세요.")}
                  >
                    🚀 발행하기
                  </Button>
                </div>
              </div>
            ) : (
              <Button onClick={runRender} disabled={!!loading}>
                {loading === "render" ? "이미지 생성 중... (1~2분 소요)" : "이미지 생성"}
              </Button>
            )}
          </StepCard>
        )}
      </div>
    </div>
  );
}

/* ─── StepCard 컴포넌트 ─────────────────────────────────── */

function StepCard({
  step,
  title,
  icon,
  done,
  active,
  children,
}: {
  step: number;
  title: string;
  icon: string;
  done: boolean;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-4 relative pl-10">
      {/* 세로 연결선 */}
      <div className="absolute left-[18px] top-10 bottom-0 w-px bg-border" />

      {/* 스텝 아이콘 */}
      <div className={`absolute left-0 top-4 w-9 h-9 rounded-full border-2 flex items-center justify-center text-sm font-bold z-10 ${
        done
          ? "bg-green-500 border-green-500 text-white"
          : active
          ? "bg-primary border-primary text-white"
          : "bg-background border-border text-muted-foreground"
      }`}>
        {done ? "✓" : icon}
      </div>

      <Card className={`ml-2 ${!active ? "opacity-50" : ""}`}>
        <CardHeader className="pb-3 pt-4 px-5">
          <CardTitle className="text-base flex items-center gap-2">
            <span className="text-muted-foreground text-sm">Step {step}</span>
            <span>{title}</span>
            {done && <Badge variant="outline" className="text-green-600 border-green-500/40 text-xs ml-auto">완료</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-5 pb-5">
          {children}
        </CardContent>
      </Card>
    </div>
  );
}
