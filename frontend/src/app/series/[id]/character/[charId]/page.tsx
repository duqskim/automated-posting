"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

/* ─── 타입 ──────────────────────────────────────────────────── */

interface DesignSession {
  stage: string;
  audience_research?: AudienceResearch;
  archetypes?: ArchetypeAdvice;
  selected_archetype_index?: number;
  concepts?: ConceptOptions;
  selected_concept_index?: number;
  image_urls?: string[];
  selected_image_index?: number;
}

interface AudienceProfile {
  segment: string;
  who_they_are: string;
  demographics: string;
  psychographics: string;
  content_behavior: string;
  character_resonance: string;
  platforms: string[];
}

interface AudienceResearch {
  profiles: AudienceProfile[];
  competitive_landscape: string;
  content_gap: string;
  key_insight: string;
  recommended_primary: string;
}

interface ArchetypeOption {
  index: number;
  archetype_name: string;
  archetype_kr: string;
  why_fits: string;
  core_traits: string[];
  tone_of_voice: string;
  content_style: string;
  real_examples: string[];
  strengths: string[];
  risks: string[];
  fit_score: number;
  differentiation: string;
}

interface ArchetypeAdvice {
  options: ArchetypeOption[];
  recommendation: string;
  hybrid_note: string;
}

interface CharacterConcept {
  index: number;
  name: string;
  tagline: string;
  backstory: string;
  personality_summary: string;
  personality_traits: string[];
  speaking_style: string;
  example_dialogues: string[];
  visual_direction: string;
  color_palette: string[];
  image_prompt: string;
  why_this_concept: string;
  audience_appeal: string;
}

interface ConceptOptions {
  archetype_name: string;
  concepts: CharacterConcept[];
  design_note: string;
}

interface CharacterBible {
  name: string;
  tagline: string;
  archetype: string;
  origin_story: string;
  mission: string;
  worldview: string;
  core_personality: string[];
  positive_traits: string[];
  flaws: string[];
  quirks: string[];
  voice_description: string;
  vocabulary_style: string;
  phrase_patterns: string[];
  forbidden_phrases: string[];
  example_scripts: { situation: string; dialogue: string }[];
  visual_description: string;
  signature_elements: string[];
  color_palette: string[];
  base_image_prompt: string;
  content_dos: string[];
  content_donts: string[];
  topic_reactions: Record<string, string>;
  character_arc: string;
  future_directions: string[];
}

/* ─── 단계 진행 설정 ──────────────────────────────────────────
   각 단계별 예상 소요시간(초)과 표시 메시지 정의
─────────────────────────────────────────────────────────────── */

interface StageRunConfig {
  label: string;
  model: string;
  modelColor: string;
  messages: string[];       // 시간 경과에 따라 순서대로 표시
  estimatedSecs: number;    // 진행바 기준 시간 (90%까지)
}

const STAGE_RUN_CONFIGS: Record<string, StageRunConfig> = {
  audience: {
    label: "오디언스 리서치",
    model: "Gemini 2.5 Flash",
    modelColor: "text-blue-500",
    estimatedSecs: 30,
    messages: [
      "시리즈 카테고리와 시장을 분석하는 중...",
      "타겟 오디언스 세그먼트를 파악하는 중...",
      "경쟁 채널 환경을 조사하는 중...",
      "콘텐츠 갭 분석 중...",
      "핵심 인사이트를 도출하는 중...",
    ],
  },
  archetype: {
    label: "아키타입 분석",
    model: "Claude Opus 4.5",
    modelColor: "text-purple-500",
    estimatedSecs: 40,
    messages: [
      "오디언스 분석 결과를 검토하는 중...",
      "캐릭터 아키타입 프레임워크를 적용하는 중...",
      "각 아키타입의 적합도를 계산하는 중...",
      "실존 채널 사례를 매핑하는 중...",
      "3개 아키타입 추천안을 작성하는 중...",
    ],
  },
  archetype_select: {
    label: "컨셉 생성",
    model: "Claude Opus 4.5",
    modelColor: "text-purple-500",
    estimatedSecs: 55,
    messages: [
      "선택된 아키타입을 기반으로 구상하는 중...",
      "캐릭터 세계관을 설계하는 중...",
      "이름과 외형 방향을 구체화하는 중...",
      "성격과 말투를 정의하는 중...",
      "3개 차별화된 컨셉을 완성하는 중...",
    ],
  },
  concept_select: {
    label: "바이블 작성",
    model: "Claude Opus 4.5",
    modelColor: "text-purple-500",
    estimatedSecs: 70,
    messages: [
      "전체 리서치와 선택 내용을 통합하는 중...",
      "캐릭터 정체성과 세계관을 정립하는 중...",
      "목소리 톤 & 매너를 정의하는 중...",
      "시그니처 표현과 대사 예시를 작성하는 중...",
      "비주얼 가이드와 이미지 프롬프트를 완성하는 중...",
      "콘텐츠 가이드라인을 정리하는 중...",
      "IP 문서로 최종 정리하는 중...",
    ],
  },
  image_select: {
    label: "바이블 작성",
    model: "Claude Opus 4.5",
    modelColor: "text-purple-500",
    estimatedSecs: 70,
    messages: [
      "선택된 이미지를 분석하는 중...",
      "캐릭터 정체성을 완성하는 중...",
      "목소리와 성격을 정립하는 중...",
      "시그니처 대사 예시를 작성하는 중...",
      "캐릭터 바이블 IP 문서를 생성하는 중...",
    ],
  },
  visual_generate: {
    label: "Gemini 3 Pro Image 생성",
    model: "Gemini 3 Pro Image (Google)",
    modelColor: "text-blue-500",
    estimatedSecs: 60,
    messages: [
      "캐릭터 비주얼 프롬프트를 분석하는 중...",
      "Gemini 3 Pro로 이미지 1/4 생성 중...",
      "Gemini 3 Pro로 이미지 2/4 생성 중...",
      "Gemini 3 Pro로 이미지 3/4 생성 중...",
      "Gemini 3 Pro로 이미지 4/4 생성 중...",
    ],
  },
  bible: {
    label: "바이블 작성",
    model: "Claude Opus 4.5",
    modelColor: "text-purple-500",
    estimatedSecs: 70,
    messages: [
      "전체 리서치와 선택 내용을 통합하는 중...",
      "캐릭터 정체성과 세계관을 정립하는 중...",
      "목소리 톤 & 매너를 정의하는 중...",
      "시그니처 표현과 대사 예시를 작성하는 중...",
      "비주얼 가이드와 이미지 프롬프트를 완성하는 중...",
      "콘텐츠 가이드라인을 정리하는 중...",
      "IP 문서로 최종 정리하는 중...",
    ],
  },
};

/* ─── 단계 정보 ─────────────────────────────────────────────── */

const STAGES = [
  { key: "audience",         label: "오디언스 리서치", step: 1 },
  { key: "archetype",        label: "아키타입 분석",   step: 2 },
  { key: "archetype_select", label: "아키타입 선택",   step: 2 },
  { key: "concepts",         label: "컨셉 생성",       step: 3 },
  { key: "concept_select",   label: "컨셉 선택",       step: 3 },
  { key: "visual",           label: "비주얼 선택",     step: 4 },
  { key: "image_select",     label: "이미지 확정",     step: 4 },
  { key: "bible",            label: "캐릭터 바이블",   step: 5 },
  { key: "done",             label: "완성",            step: 5 },
];

function currentStep(stage: string) {
  return STAGES.find(s => s.key === stage)?.step ?? 1;
}

/* ─── 진행 상태 표시 컴포넌트 ────────────────────────────────── */

function RunningIndicator({ stage }: { stage: string }) {
  const config = STAGE_RUN_CONFIGS[stage];
  const [elapsed, setElapsed] = useState(0);
  const [msgIdx, setMsgIdx] = useState(0);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    setElapsed(0);
    setMsgIdx(0);
    intervalRef.current = setInterval(() => {
      setElapsed(s => s + 1);
    }, 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [stage]);

  // 메시지 순환: 경과 시간 기준으로 다음 메시지로 이동
  useEffect(() => {
    if (!config) return;
    const interval = config.estimatedSecs / config.messages.length;
    const next = Math.min(Math.floor(elapsed / interval), config.messages.length - 1);
    setMsgIdx(next);
  }, [elapsed, config]);

  if (!config) return null;

  // 진행률: estimatedSecs 기준으로 0→90%, 그 이후는 천천히 90→97%로
  const rawProgress = elapsed / config.estimatedSecs;
  const progress = rawProgress < 1
    ? rawProgress * 90
    : 90 + Math.min((rawProgress - 1) * 7, 7);

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const elapsedStr = mins > 0 ? `${mins}분 ${secs}초` : `${secs}초`;

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardContent className="p-5 space-y-4">
        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {/* 애니메이션 점 */}
            <div className="flex gap-1">
              {[0, 1, 2].map(i => (
                <div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
            <span className="text-sm font-semibold">{config.label} 진행 중</span>
          </div>
          <div className="text-xs text-muted-foreground">{elapsedStr} 경과</div>
        </div>

        {/* 진행 바 */}
        <div className="space-y-1">
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-1000 ease-out"
              style={{ width: `${progress.toFixed(1)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{Math.round(progress)}%</span>
            <span>예상 {config.estimatedSecs}초</span>
          </div>
        </div>

        {/* 현재 작업 메시지 */}
        <div className="flex items-start gap-2 bg-background/60 rounded-lg p-3 border border-border/50">
          <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 shrink-0 animate-pulse" />
          <p className="text-sm text-foreground leading-relaxed">
            {config.messages[msgIdx]}
          </p>
        </div>

        {/* 모델 표시 */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span>AI 모델:</span>
          <span className={`font-medium ${config.modelColor}`}>{config.model}</span>
        </div>
      </CardContent>
    </Card>
  );
}

/* ─── 메인 컴포넌트 ─────────────────────────────────────────── */

export default function CharacterDesignPage() {
  const router = useRouter();
  const params = useParams();
  const seriesId = Number(params.id);
  const charId = Number(params.charId);

  const [session, setSession] = useState<DesignSession>({ stage: "audience" });
  const [charName, setCharName] = useState("");
  const [charStatus, setCharStatus] = useState("draft");
  const [bible, setBible] = useState<CharacterBible | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runningStage, setRunningStage] = useState("");
  const [error, setError] = useState("");

  // Image URL 입력 (visual 단계)
  const [imageUrlInput, setImageUrlInput] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api.series.characters.design.get(seriesId, charId);
      setCharName(data.name || "");
      setCharStatus(data.status || "draft");
      setSession(data.design_session || { stage: "audience" });
      if (data.bible) setBible(data.bible);
    } catch {
      router.push(`/series/${seriesId}`);
    } finally {
      setLoading(false);
    }
  }, [seriesId, charId, router]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { router.push("/login"); return; }
    load();
  }, [load, router]);

  const run = async (stageKey: string, action: () => Promise<unknown>) => {
    setRunning(true);
    setRunningStage(stageKey);
    setError("");
    try {
      const result = await action() as DesignSession & { bible?: CharacterBible; character?: { bible: CharacterBible; name: string } };
      if (result.stage) {
        setSession(prev => ({ ...prev, ...result }));
      }
      if (result.character) {
        setCharName(result.character.name || "");
        setCharStatus("active");
        setBible(result.character.bible);
        setSession(prev => ({ ...prev, stage: "done" }));
      }
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "오류가 발생했습니다");
    } finally {
      setRunning(false);
      setRunningStage("");
    }
  };

  /* ─── 로딩 ─────────────────────────────────────────────── */

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">로딩 중...</p>
      </div>
    );
  }

  const stage = session.stage;
  const step = currentStep(stage);

  /* ─── 렌더 ─────────────────────────────────────────────── */

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b sticky top-0 bg-background z-10">
        <div className="container mx-auto flex items-center justify-between h-14 px-4">
          <button onClick={() => router.push(`/series/${seriesId}`)} className="text-lg font-bold hover:opacity-80">
            ← 시리즈
          </button>
          <div className="text-sm text-muted-foreground">
            Character Design Studio
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 max-w-3xl">

        {/* 진행 스텝 */}
        <div className="flex items-center gap-1 mb-8 overflow-x-auto">
          {[1, 2, 3, 4, 5].map(s => (
            <div key={s} className="flex items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0
                ${s < step ? "bg-green-500 text-white" :
                  s === step ? "bg-primary text-primary-foreground" :
                  "bg-muted text-muted-foreground"}`}>
                {s < step ? "✓" : s}
              </div>
              {s < 5 && <div className={`w-8 h-0.5 ${s < step ? "bg-green-500" : "bg-muted"}`} />}
            </div>
          ))}
          <div className="ml-3 text-sm text-muted-foreground whitespace-nowrap">
            {["", "오디언스 리서치", "아키타입 선택", "캐릭터 컨셉", "비주얼 확정", "캐릭터 바이블"][step]}
          </div>
        </div>

        {charName && (
          <div className="mb-6 flex items-center gap-3">
            <h1 className="text-xl font-bold">{charName}</h1>
            {charStatus === "active" && (
              <Badge className="bg-green-500/10 text-green-500 border-green-500/20">완성</Badge>
            )}
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 text-red-500 rounded-lg text-sm border border-red-500/20">
            {error}
          </div>
        )}

        {/* AI 작업 진행 상태 표시 */}
        {running && runningStage && (
          <div className="mb-6">
            <RunningIndicator stage={runningStage} />
          </div>
        )}

        {/* ── 완성 상태 ─────────────────────────────────────── */}
        {stage === "done" && bible && (
          <BibleView
            bible={bible}
            seriesId={seriesId}
            router={router}
            imageUrls={session.image_urls}
            selectedImageIndex={session.selected_image_index ?? 0}
          />
        )}

        {/* ── Stage 1: 오디언스 리서치 실행 ─────────────────── */}
        {stage === "audience" && !running && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Step 1 — 오디언스 리서치</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                이 시리즈의 타겟 오디언스를 심층 분석합니다.
                누가 보는지, 어떤 캐릭터에 끌리는지, 경쟁 채널과의 차별화 포인트를 분석합니다.
              </p>
              <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/30 p-2 rounded-lg">
                <span className="text-blue-500 font-medium">Gemini 2.5 Flash</span>
                <span>·</span>
                <span>약 20~30초 소요</span>
              </div>
              <Button
                onClick={() => run("audience", () => api.series.characters.design.runAudience(seriesId, charId))}
                disabled={running}
              >
                오디언스 분석 시작
              </Button>
            </CardContent>
          </Card>
        )}

        {/* ── Stage 1 결과 + Stage 2 실행 ───────────────────── */}
        {stage === "archetype" && session.audience_research && !running && (
          <div className="space-y-4">
            <AudienceResearchView research={session.audience_research} />
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Step 2 — 아키타입 분석</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  오디언스 분석 결과를 바탕으로 3가지 캐릭터 아키타입을 추천합니다.
                  각 아키타입의 적합도 점수, 실존 채널 예시, 위험 요소를 함께 제공합니다.
                </p>
                <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/30 p-2 rounded-lg">
                  <span className="text-orange-500 font-medium">Claude Sonnet 4.6</span>
                  <span>·</span>
                  <span>약 35~50초 소요</span>
                </div>
                <Button
                  onClick={() => run("archetype", () => api.series.characters.design.runArchetypes(seriesId, charId))}
                  disabled={running}
                >
                  아키타입 분석 →
                </Button>
              </CardContent>
            </Card>
          </div>
        )}

        {/* ── Stage 2 결과: 아키타입 선택 ──────────────────────*/}
        {stage === "archetype_select" && session.archetypes && !running && (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Step 2 — 아키타입 선택</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-4">
                  {session.archetypes.recommendation}
                </p>
                {session.archetypes.hybrid_note !== "Pure archetype recommended" && (
                  <p className="text-xs bg-blue-500/10 text-blue-500 p-2 rounded mb-4">
                    혼합 옵션: {session.archetypes.hybrid_note}
                  </p>
                )}
              </CardContent>
            </Card>
            {session.archetypes.options.map(option => (
              <ArchetypeCard
                key={option.index}
                option={option}
                selected={session.selected_archetype_index === option.index}
                onSelect={() => {
                  // 선택만 하고 바로 컨셉 생성 진행
                  run("archetype_select", async () => {
                    await api.series.characters.design.selectArchetype(seriesId, charId, option.index);
                    return api.series.characters.design.runConcepts(seriesId, charId);
                  });
                }}
                disabled={running}
              />
            ))}
          </div>
        )}

        {/* ── Stage 3 결과: 컨셉 선택 ─────────────────────── */}
        {stage === "concept_select" && session.concepts && !running && (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Step 3 — 캐릭터 컨셉 선택</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{session.concepts.design_note}</p>
              </CardContent>
            </Card>
            {session.concepts.concepts.map(concept => (
              <ConceptCard
                key={concept.index}
                concept={concept}
                selected={session.selected_concept_index === concept.index}
                onSelect={() => run("concept_select", () => api.series.characters.design.selectConcept(seriesId, charId, concept.index))}
                disabled={running}
              />
            ))}
          </div>
        )}

        {/* ── Stage 4: 이미지 생성/업로드 ─────────────────── */}
        {stage === "visual" && !running && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Step 4 — 비주얼 확정</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* 이미지 프롬프트 표시 */}
              {session.concepts?.concepts[session.selected_concept_index ?? 0] && (
                <div className="p-3 bg-muted/20 rounded-lg">
                  <div className="text-xs text-muted-foreground mb-1">이미지 생성 프롬프트</div>
                  <p className="text-xs font-mono leading-relaxed">
                    {session.concepts.concepts[session.selected_concept_index ?? 0].image_prompt}
                  </p>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="mt-2 text-xs h-6"
                    onClick={() => {
                      const prompt = session.concepts?.concepts[session.selected_concept_index ?? 0]?.image_prompt;
                      if (prompt) navigator.clipboard.writeText(prompt);
                    }}
                  >
                    프롬프트 복사
                  </Button>
                </div>
              )}

              {/* 옵션 1: Imagen 직접 생성 */}
              <div className="rounded-xl border-2 border-primary/20 bg-primary/5 p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-blue-500" />
                  <span className="text-sm font-semibold">Imagen 4.0으로 바로 생성</span>
                  <Badge variant="outline" className="text-xs text-blue-500 border-blue-500/30">추천</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  위 프롬프트로 Gemini 3 Pro Image가 캐릭터 이미지 4장을 자동 생성합니다. 생성 후 마음에 드는 1장을 선택하세요.
                </p>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="text-blue-500 font-medium">Gemini 3 Pro Image</span>
                  <span>·</span>
                  <span>약 40~60초 소요 · 4장 생성</span>
                </div>
                <Button
                  onClick={() => run("visual_generate", () => api.series.characters.design.generateImages(seriesId, charId))}
                  disabled={running}
                >
                  Gemini로 생성 →
                </Button>
              </div>

              {/* 구분선 */}
              <div className="flex items-center gap-3">
                <div className="flex-1 h-px bg-border" />
                <span className="text-xs text-muted-foreground">또는 직접 URL 입력</span>
                <div className="flex-1 h-px bg-border" />
              </div>

              {/* 옵션 2: 외부 이미지 URL */}
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground">
                  Midjourney, Adobe Firefly 등 다른 도구로 생성한 이미지 URL을 붙여넣으세요.
                </p>
                <textarea
                  placeholder="https://example.com/character1.png&#10;https://example.com/character2.png"
                  value={imageUrlInput}
                  onChange={e => setImageUrlInput(e.target.value)}
                  rows={3}
                  className="w-full p-2 text-sm bg-background border border-input rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                />
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const urls = imageUrlInput.split("\n").map(u => u.trim()).filter(Boolean);
                      if (urls.length === 0) return;
                      run("image_select", () => api.series.characters.design.saveImageUrls(seriesId, charId, urls));
                    }}
                    disabled={running || !imageUrlInput.trim()}
                  >
                    URL로 저장 →
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => run("bible", () => api.series.characters.design.saveImageUrls(seriesId, charId, []))}
                    disabled={running}
                  >
                    이미지 없이 진행
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── Stage 4: 이미지 선택 ─────────────────────────── */}
        {stage === "image_select" && session.image_urls && session.image_urls.length > 0 && !running && (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Step 4 — 대표 이미지 선택</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  캐릭터의 대표 이미지를 선택하면 바이블 작성이 시작됩니다.
                </p>
              </CardContent>
            </Card>
            <div className="grid grid-cols-2 gap-3">
              {session.image_urls.map((url, idx) => (
                <div
                  key={idx}
                  className={`border-2 rounded-xl overflow-hidden cursor-pointer transition-colors
                    ${session.selected_image_index === idx ? "border-primary" : "border-transparent hover:border-primary/30"}`}
                  onClick={() => run("image_select", async () => {
                    await api.series.characters.design.selectImage(seriesId, charId, idx);
                    return api.series.characters.design.runBible(seriesId, charId);
                  })}
                >
                  <img src={url} alt={`Option ${idx + 1}`} className="w-full aspect-square object-cover" />
                  <div className="p-2 text-center text-xs text-muted-foreground">클릭하여 선택 + 바이블 작성</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Stage 5: 바이블 실행 (이미지 없는 경우) ──────── */}
        {stage === "bible" && !running && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Step 5 — 캐릭터 바이블 작성</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                지금까지의 리서치와 선택을 바탕으로 완성된 캐릭터 바이블을 작성합니다.
                이 문서가 이 캐릭터의 모든 것을 정의하는 IP 문서가 됩니다.
              </p>
              <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/30 p-2 rounded-lg">
                <span className="text-orange-500 font-medium">Claude Sonnet 4.6</span>
                <span>·</span>
                <span>약 60~80초 소요</span>
              </div>
              <Button
                onClick={() => run("bible", () => api.series.characters.design.runBible(seriesId, charId))}
                disabled={running}
              >
                캐릭터 바이블 완성
              </Button>
            </CardContent>
          </Card>
        )}

      </div>
    </div>
  );
}

/* ─── 서브 컴포넌트 ─────────────────────────────────────────── */

function AudienceResearchView({ research }: { research: AudienceResearch }) {
  const primary = research.profiles.find(p => p.segment === "Primary") ?? research.profiles[0];
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">오디언스 리서치 결과</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {primary && (
          <div className="p-3 bg-muted/20 rounded-lg space-y-1">
            <div className="font-medium">Primary: {primary.who_they_are}</div>
            <div className="text-xs text-muted-foreground">{primary.demographics}</div>
            <div className="text-xs bg-primary/5 border border-primary/10 p-2 rounded mt-2">
              원하는 캐릭터: {primary.character_resonance}
            </div>
          </div>
        )}
        <div className="p-3 bg-amber-500/5 border border-amber-500/10 rounded-lg">
          <div className="text-xs font-medium text-amber-600 mb-1">핵심 인사이트</div>
          <p className="text-xs">{research.key_insight}</p>
        </div>
        <div className="p-3 bg-blue-500/5 border border-blue-500/10 rounded-lg">
          <div className="text-xs font-medium text-blue-500 mb-1">콘텐츠 기회 (Gap)</div>
          <p className="text-xs">{research.content_gap}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function ArchetypeCard({
  option,
  selected,
  onSelect,
  disabled,
}: {
  option: ArchetypeOption;
  selected: boolean;
  onSelect: () => void;
  disabled: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Card className={`transition-colors ${selected ? "border-primary" : "hover:border-primary/30"}`}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <span className="font-semibold">{option.archetype_name}</span>
            <span className="text-muted-foreground ml-2 text-sm">({option.archetype_kr})</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`text-sm font-bold ${option.fit_score >= 80 ? "text-green-500" : option.fit_score >= 60 ? "text-yellow-500" : "text-red-500"}`}>
              {option.fit_score}점
            </div>
            {selected && <Badge className="bg-primary/10 text-primary border-primary/20 text-xs">선택됨</Badge>}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">{option.why_fits}</p>
        <div className="flex flex-wrap gap-1">
          {option.core_traits.map(t => (
            <span key={t} className="text-xs bg-muted/50 px-1.5 py-0.5 rounded">{t}</span>
          ))}
        </div>
        {expanded && (
          <div className="space-y-2 text-xs pt-2 border-t">
            <div>
              <div className="font-medium mb-1">말투/어조</div>
              <p className="text-muted-foreground">{option.tone_of_voice}</p>
            </div>
            <div>
              <div className="font-medium mb-1">실존 채널 예시</div>
              {option.real_examples.map((ex, i) => (
                <p key={i} className="text-muted-foreground">• {ex}</p>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="font-medium text-green-600 mb-1">강점</div>
                {option.strengths.map((s, i) => <p key={i} className="text-muted-foreground">+ {s}</p>)}
              </div>
              <div>
                <div className="font-medium text-red-500 mb-1">위험</div>
                {option.risks.map((r, i) => <p key={i} className="text-muted-foreground">- {r}</p>)}
              </div>
            </div>
            <div>
              <div className="font-medium mb-1">차별화 포인트</div>
              <p className="text-muted-foreground">{option.differentiation}</p>
            </div>
          </div>
        )}
        <div className="flex gap-2 pt-1">
          <Button size="sm" variant="ghost" className="text-xs h-7" onClick={() => setExpanded(!expanded)}>
            {expanded ? "접기" : "자세히"}
          </Button>
          <Button size="sm" className="text-xs h-7" onClick={onSelect} disabled={disabled}>
            {selected ? "선택됨" : "이 아키타입으로 컨셉 생성 →"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ConceptCard({
  concept,
  selected,
  onSelect,
  disabled,
}: {
  concept: CharacterConcept;
  selected: boolean;
  onSelect: () => void;
  disabled: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Card className={`transition-colors ${selected ? "border-primary" : "hover:border-primary/30"}`}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="font-semibold text-lg">{concept.name}</div>
            <div className="text-sm text-muted-foreground italic">{concept.tagline}</div>
          </div>
          {selected && <Badge className="bg-primary/10 text-primary border-primary/20 text-xs shrink-0">선택됨</Badge>}
        </div>
        <p className="text-xs text-muted-foreground">{concept.personality_summary}</p>
        <div className="flex flex-wrap gap-1">
          {concept.personality_traits.map(t => (
            <span key={t} className="text-xs bg-muted/50 px-1.5 py-0.5 rounded">{t}</span>
          ))}
        </div>
        {expanded && (
          <div className="space-y-3 text-xs pt-2 border-t">
            <div>
              <div className="font-medium mb-1">배경</div>
              <p className="text-muted-foreground">{concept.backstory}</p>
            </div>
            <div>
              <div className="font-medium mb-1">말투</div>
              <p className="text-muted-foreground">{concept.speaking_style}</p>
            </div>
            <div>
              <div className="font-medium mb-1">대사 예시</div>
              {concept.example_dialogues.map((d, i) => (
                <div key={i} className="bg-muted/30 p-2 rounded italic mb-1">&ldquo;{d}&rdquo;</div>
              ))}
            </div>
            <div>
              <div className="font-medium mb-1">외형 방향</div>
              <p className="text-muted-foreground">{concept.visual_direction}</p>
            </div>
            {concept.color_palette.length > 0 && (
              <div>
                <div className="font-medium mb-1">컬러 팔레트</div>
                <div className="flex gap-2">
                  {concept.color_palette.map((c, i) => (
                    <span key={i} className="text-xs bg-muted/50 px-2 py-1 rounded">{c}</span>
                  ))}
                </div>
              </div>
            )}
            <div>
              <div className="font-medium mb-1">오디언스 어필 포인트</div>
              <p className="text-muted-foreground">{concept.audience_appeal}</p>
            </div>
          </div>
        )}
        <div className="flex gap-2 pt-1">
          <Button size="sm" variant="ghost" className="text-xs h-7" onClick={() => setExpanded(!expanded)}>
            {expanded ? "접기" : "자세히"}
          </Button>
          <Button size="sm" className="text-xs h-7" onClick={onSelect} disabled={disabled}>
            {selected ? "선택됨" : "이 컨셉 선택 + 비주얼 확정 →"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function BibleView({
  bible,
  seriesId,
  router,
  imageUrls,
  selectedImageIndex,
}: {
  bible: CharacterBible;
  seriesId: number;
  router: ReturnType<typeof useRouter>;
  imageUrls?: string[];
  selectedImageIndex?: number;
}) {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const toFull = (url: string) =>
    url.startsWith("http") ? url : `${API_URL}${url}`;
  const selectedUrl = imageUrls && imageUrls.length > 0
    ? toFull(imageUrls[selectedImageIndex ?? 0])
    : null;

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="p-5">
          <div className="flex items-start gap-4 mb-3">
            {selectedUrl && (
              <img
                src={selectedUrl}
                alt={bible.name}
                className="w-24 h-24 rounded-xl object-cover border border-primary/20 flex-shrink-0"
              />
            )}
            <div className="flex-1">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-2xl font-bold">{bible.name}</h2>
                  <p className="text-muted-foreground italic">{bible.tagline}</p>
                </div>
                <Badge className="bg-green-500/10 text-green-500 border-green-500/20">완성</Badge>
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline" className="text-xs">{bible.archetype}</Badge>
          </div>
          {bible.color_palette.length > 0 && (
            <div className="flex gap-2 mt-3">
              {bible.color_palette.map((c, i) => (
                <span key={i} className="text-xs bg-background/50 px-2 py-1 rounded border">{c}</span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 생성된 이미지 전체 */}
      {imageUrls && imageUrls.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">생성된 이미지 ({imageUrls.length}장)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              {imageUrls.map((url, idx) => (
                <div key={idx} className="relative">
                  <img
                    src={toFull(url)}
                    alt={`${bible.name} ${idx + 1}`}
                    className="w-full aspect-square object-cover rounded-xl border border-border"
                  />
                  {idx === (selectedImageIndex ?? 0) && (
                    <div className="absolute top-2 right-2 bg-primary text-primary-foreground text-xs px-2 py-0.5 rounded-full">
                      선택됨
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 미션/세계관 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">정체성</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-1">미션</div>
            <p>{bible.mission}</p>
          </div>
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-1">세계관</div>
            <p>{bible.worldview}</p>
          </div>
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-1">배경</div>
            <p className="text-muted-foreground">{bible.origin_story}</p>
          </div>
        </CardContent>
      </Card>

      {/* 성격 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">성격</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-1">
            {bible.core_personality.map(t => (
              <span key={t} className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full">{t}</span>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="font-medium text-green-600 mb-1">장점</div>
              {bible.positive_traits.map((t, i) => <p key={i} className="text-muted-foreground">+ {t}</p>)}
            </div>
            <div>
              <div className="font-medium text-orange-500 mb-1">결점 (인간미)</div>
              {bible.flaws.map((f, i) => <p key={i} className="text-muted-foreground">• {f}</p>)}
            </div>
          </div>
          {bible.quirks.length > 0 && (
            <div className="text-xs">
              <div className="font-medium mb-1">특유의 버릇</div>
              {bible.quirks.map((q, i) => <p key={i} className="text-muted-foreground">✦ {q}</p>)}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 목소리 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">목소리 & 어조</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground text-xs">{bible.voice_description}</p>
          {bible.phrase_patterns.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-1">시그니처 표현</div>
              {bible.phrase_patterns.map((p, i) => (
                <p key={i} className="text-xs bg-muted/30 p-2 rounded mb-1 italic">&ldquo;{p}&rdquo;</p>
              ))}
            </div>
          )}
          {bible.example_scripts.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-2">상황별 대사 예시</div>
              {bible.example_scripts.map((s, i) => (
                <div key={i} className="mb-2">
                  <div className="text-xs text-muted-foreground">{s.situation}</div>
                  <div className="text-xs bg-primary/5 border border-primary/10 p-2 rounded mt-0.5 italic">
                    {s.dialogue}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 콘텐츠 가이드 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">콘텐츠 가이드</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-xs">
          {bible.content_dos.map((d, i) => (
            <p key={i} className="text-green-600">✓ {d}</p>
          ))}
          {bible.content_donts.map((d, i) => (
            <p key={i} className="text-red-500">✗ {d}</p>
          ))}
        </CardContent>
      </Card>

      {/* 미래 방향 */}
      {bible.future_directions.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">향후 확장 방향</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs text-muted-foreground">
            {bible.future_directions.map((d, i) => (
              <p key={i}>• {d}</p>
            ))}
          </CardContent>
        </Card>
      )}

      <Button
        variant="outline"
        className="w-full"
        onClick={() => router.push(`/series/${seriesId}`)}
      >
        시리즈로 돌아가기
      </Button>
    </div>
  );
}
