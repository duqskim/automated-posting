"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

/* ─── 타입 ─────────────────────────────────────────────── */

interface Episode {
  id: number;
  episode_number: number;
  title: string;
  part_name: string | null;
  era_tag: string | null;
  drama_ref: string | null;
  notes: string | null;
  summary: string | null;
  status: string;
  project_id: number | null;
  pipeline_step: string; // idle | research_done | hooks_done | write_done | render_done | video_done
}

interface Character {
  id: number;
  name: string;
  status: string;
  concept: string | null;
  personality: string | null;
  visual_description: string | null;
  base_image_prompt: string | null;
  voice_id: string | null;
  reference_image_url: string | null;
}

interface Series {
  id: number;
  name: string;
  description: string | null;
  market: string;
  language: string;
  category: string;
  visual_style: string;
  fact_mode: string;
  target_platforms: string[];
  current_episode: number;
  episode_count: number;
  episodes: Episode[];
  characters: Character[];
}

/* ─── 상수 ─────────────────────────────────────────────── */

const MARKET_FLAGS: Record<string, string> = { kr: "🇰🇷", us: "🇺🇸", jp: "🇯🇵", global: "🌍" };

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  draft:      { label: "기획 중", color: "text-muted-foreground" },
  generating: { label: "생성 중", color: "text-blue-500" },
  ready:      { label: "완료",   color: "text-green-500" },
  published:  { label: "발행됨", color: "text-purple-500" },
};

// pipeline_step 순서 정의
const PIPELINE_STEPS = [
  { key: "research_done", label: "리서치" },
  { key: "hooks_done",    label: "훅" },
  { key: "write_done",    label: "글쓰기" },
  { key: "render_done",   label: "이미지" },
  { key: "video_done",    label: "영상" },
] as const;

const STEP_ORDER = ["idle", "research_done", "hooks_done", "write_done", "render_done", "video_done"];

function PipelineBar({ step }: { step: string }) {
  const currentIdx = STEP_ORDER.indexOf(step);
  return (
    <div className="flex items-center gap-1 mt-2">
      {PIPELINE_STEPS.map((s, i) => {
        const stepIdx = i + 1; // idle=0, research_done=1, ...
        const done = currentIdx > stepIdx;
        const active = currentIdx === stepIdx;
        return (
          <div key={s.key} className="flex items-center gap-1">
            <div className="flex flex-col items-center gap-0.5">
              <div className={`w-2 h-2 rounded-full ${
                done   ? "bg-green-500" :
                active ? "bg-blue-500 animate-pulse" :
                         "bg-muted-foreground/30"
              }`} />
              <span className={`text-[9px] leading-none ${
                done   ? "text-green-500" :
                active ? "text-blue-500" :
                         "text-muted-foreground/50"
              }`}>{s.label}</span>
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <div className={`h-px w-3 mb-3 ${done ? "bg-green-500/50" : "bg-muted-foreground/20"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ─── 메인 컴포넌트 ─────────────────────────────────────── */

export default function SeriesDetailPage() {
  const router = useRouter();
  const params = useParams();
  const seriesId = Number(params.id);

  const [series, setSeries] = useState<Series | null>(null);
  const [loading, setLoading] = useState(true);
  const [generatingEp, setGeneratingEp] = useState<number | null>(null);
  const [error, setError] = useState("");

  // 에피소드 추가 폼
  const [showAddEp, setShowAddEp] = useState(false);
  const [newEpTitle, setNewEpTitle] = useState("");
  const [newEpPartName, setNewEpPartName] = useState("");
  const [newEpEraTag, setNewEpEraTag] = useState("");
  const [newEpDramaRef, setNewEpDramaRef] = useState("");
  const [newEpNotes, setNewEpNotes] = useState("");
  const [addingEp, setAddingEp] = useState(false);

  // 캐릭터 폼
  const [showAddChar, setShowAddChar] = useState(false);
  const [newCharName, setNewCharName] = useState("");
  const [newCharConcept, setNewCharConcept] = useState("");
  const [newCharPersonality, setNewCharPersonality] = useState("");
  const [newCharVisual, setNewCharVisual] = useState("");
  const [newCharPrompt, setNewCharPrompt] = useState("");
  const [addingChar, setAddingChar] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.series.get(seriesId);
      setSeries(data);
    } catch {
      router.push("/series");
    } finally {
      setLoading(false);
    }
  }, [seriesId, router]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { router.push("/login"); return; }
    load();
  }, [load, router]);

  /* ─── 에피소드 추가 ────────────────────────────────────── */

  const addEpisode = async () => {
    if (!newEpTitle.trim() || !series) return;
    setAddingEp(true);
    setError("");
    try {
      const nextNum = (series.episodes.length > 0
        ? Math.max(...series.episodes.map(e => e.episode_number)) + 1
        : 1);
      await api.series.episodes.add(seriesId, [{
        episode_number: nextNum,
        title: newEpTitle.trim(),
        part_name: newEpPartName.trim() || undefined,
        era_tag: newEpEraTag.trim() || undefined,
        drama_ref: newEpDramaRef.trim() || undefined,
        notes: newEpNotes.trim() || undefined,
      }]);
      setNewEpTitle(""); setNewEpPartName(""); setNewEpEraTag("");
      setNewEpDramaRef(""); setNewEpNotes(""); setShowAddEp(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "추가 실패");
    } finally {
      setAddingEp(false);
    }
  };

  /* ─── 에피소드 생성 (프로젝트 → 파이프라인) ─────────────── */

  const generateEpisode = async (ep: Episode) => {
    setGeneratingEp(ep.id);
    setError("");
    try {
      const res = await api.series.episodes.generate(seriesId, ep.id);
      router.push(`/projects/${res.project_id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "생성 실패");
      setGeneratingEp(null);
    }
  };

  /* ─── 에피소드 삭제 ────────────────────────────────────── */

  const deleteEpisode = async (ep: Episode) => {
    if (!confirm(`EP${ep.episode_number} "${ep.title}"을 삭제하시겠습니까?`)) return;
    try {
      await api.series.episodes.delete(seriesId, ep.id);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "삭제 실패");
    }
  };

  /* ─── 캐릭터 추가 ──────────────────────────────────────── */

  const addCharacter = async () => {
    if (!newCharName.trim()) return;
    setAddingChar(true);
    setError("");
    try {
      await api.series.characters.create(seriesId, {
        name: newCharName.trim(),
        concept: newCharConcept.trim() || undefined,
        personality: newCharPersonality.trim() || undefined,
        visual_description: newCharVisual.trim() || undefined,
        base_image_prompt: newCharPrompt.trim() || undefined,
      });
      setNewCharName(""); setNewCharConcept(""); setNewCharPersonality("");
      setNewCharVisual(""); setNewCharPrompt(""); setShowAddChar(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "캐릭터 추가 실패");
    } finally {
      setAddingChar(false);
    }
  };

  const deleteCharacter = async (charId: number, name: string) => {
    if (!confirm(`캐릭터 "${name}"을 삭제하시겠습니까?`)) return;
    try {
      await api.series.characters.delete(seriesId, charId);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "삭제 실패");
    }
  };

  /* ─── 렌더 ─────────────────────────────────────────────── */

  if (loading || !series) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">로딩 중...</p>
      </div>
    );
  }

  // 파트별 그룹핑
  const parts: Record<string, Episode[]> = {};
  for (const ep of series.episodes) {
    const key = ep.part_name || "기타";
    if (!parts[key]) parts[key] = [];
    parts[key].push(ep);
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b sticky top-0 bg-background z-10">
        <div className="container mx-auto flex items-center justify-between h-14 px-4">
          <button onClick={() => router.push("/series")} className="text-lg font-bold hover:opacity-80">
            Automated Posting
          </button>
          <Button variant="ghost" size="sm" onClick={() => router.push("/series")}>
            시리즈 목록
          </Button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 max-w-3xl">

        {/* 시리즈 헤더 */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xl">{MARKET_FLAGS[series.market] ?? "🌐"}</span>
            <h1 className="text-2xl font-bold">{series.name}</h1>
          </div>
          {series.description && (
            <p className="text-muted-foreground text-sm mb-3">{series.description}</p>
          )}
          <div className="flex gap-2 flex-wrap">
            <Badge variant="outline">{series.category}</Badge>
            <Badge variant="outline">{series.visual_style}</Badge>
            <Badge variant="outline" className={
              series.fact_mode === "strict" ? "text-red-500 border-red-500/30" :
              series.fact_mode === "standard" ? "text-yellow-500 border-yellow-500/30" :
              ""
            }>
              팩트 {series.fact_mode}
            </Badge>
            {series.target_platforms.map(p => (
              <Badge key={p} variant="secondary" className="text-xs">{p}</Badge>
            ))}
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 text-red-500 rounded-lg text-sm border border-red-500/20">
            {error}
          </div>
        )}

        {/* ── 캐릭터 섹션 ──────────────────────────────────── */}
        <Card className="mb-6">
          <CardHeader className="pb-3 pt-4 px-5">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">캐릭터</CardTitle>
              {!showAddChar && (
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={async () => {
                      try {
                        const char = await api.series.characters.create(seriesId, { name: "" });
                        router.push(`/series/${seriesId}/character/${char.id}`);
                      } catch (e: unknown) {
                        setError(e instanceof Error ? e.message : "생성 실패");
                      }
                    }}
                  >
                    AI 캐릭터 설계
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setShowAddChar(true)}>
                    직접 입력
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="px-5 pb-5 space-y-4">
            {series.characters.length === 0 && !showAddChar && (
              <p className="text-xs text-muted-foreground">
                캐릭터가 없습니다. 시리즈 전반에 등장할 가이드 캐릭터를 추가해보세요.
              </p>
            )}

            {series.characters.map(c => (
              <div key={c.id} className="p-3 border rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{c.name || "이름 미정"}</span>
                    {c.status === "active" ? (
                      <span className="text-xs bg-green-500/10 text-green-500 px-1.5 py-0.5 rounded">완성</span>
                    ) : (
                      <span className="text-xs bg-yellow-500/10 text-yellow-500 px-1.5 py-0.5 rounded">설계 중</span>
                    )}
                  </div>
                  <button
                    className="text-xs text-muted-foreground hover:text-red-500"
                    onClick={() => deleteCharacter(c.id, c.name || "캐릭터")}
                  >
                    삭제
                  </button>
                </div>
                {c.concept && <p className="text-xs text-muted-foreground">{c.concept}</p>}
                {c.reference_image_url && (
                  <img
                    src={c.reference_image_url}
                    alt={c.name}
                    className="w-16 h-16 object-cover rounded-lg border"
                  />
                )}
                <Button
                  size="sm"
                  variant={c.status === "active" ? "outline" : "default"}
                  className="text-xs h-7"
                  onClick={() => router.push(`/series/${seriesId}/character/${c.id}`)}
                >
                  {c.status === "active" ? "캐릭터 바이블 보기" : "Character Design Studio →"}
                </Button>
              </div>
            ))}

            {showAddChar && (
              <div className="border rounded-xl p-4 space-y-3 bg-muted/10">
                <div className="text-sm font-medium">새 캐릭터</div>
                <Input
                  placeholder="이름 *"
                  value={newCharName}
                  onChange={e => setNewCharName(e.target.value)}
                />
                <textarea
                  placeholder="컨셉 (예: 조선 시대 선비가 현대로 와서 외국인에게 역사를 설명)"
                  value={newCharConcept}
                  onChange={e => setNewCharConcept(e.target.value)}
                  rows={2}
                  className="w-full p-2 text-sm bg-background border border-input rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <textarea
                  placeholder="성격/톤 (예: Warm, witty, slightly formal)"
                  value={newCharPersonality}
                  onChange={e => setNewCharPersonality(e.target.value)}
                  rows={2}
                  className="w-full p-2 text-sm bg-background border border-input rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <textarea
                  placeholder="외모 설명 (영문, Imagen 프롬프트용)"
                  value={newCharVisual}
                  onChange={e => setNewCharVisual(e.target.value)}
                  rows={2}
                  className="w-full p-2 text-sm bg-background border border-input rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <textarea
                  placeholder="기준 이미지 프롬프트 (Imagen4, 영문 40-80단어)"
                  value={newCharPrompt}
                  onChange={e => setNewCharPrompt(e.target.value)}
                  rows={3}
                  className="w-full p-2 text-sm bg-background border border-input rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={addCharacter} disabled={addingChar || !newCharName.trim()}>
                    {addingChar ? "추가 중..." : "추가"}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setShowAddChar(false)}>
                    취소
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── 에피소드 목록 ─────────────────────────────────── */}
        <Card>
          <CardHeader className="pb-3 pt-4 px-5">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                에피소드
                <span className="ml-2 text-sm text-muted-foreground font-normal">
                  {series.episode_count}개
                </span>
              </CardTitle>
              {!showAddEp && (
                <Button size="sm" variant="outline" onClick={() => setShowAddEp(true)}>
                  + 에피소드 추가
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="px-5 pb-5 space-y-6">

            {/* 파트별 그룹 */}
            {Object.entries(parts).map(([partName, episodes]) => (
              <div key={partName}>
                {partName !== "기타" && (
                  <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2 pb-1 border-b">
                    {partName}
                  </div>
                )}
                <div className="space-y-2">
                  {episodes.map(ep => (
                    <div key={ep.id}
                      className="flex items-start gap-3 p-3 border rounded-xl hover:border-primary/30 transition-colors"
                    >
                      {/* 에피소드 번호 */}
                      <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                        {ep.episode_number}
                      </div>

                      {/* 내용 */}
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm mb-1 leading-tight">{ep.title}</div>
                        <div className="flex flex-wrap gap-1.5 items-center">
                          {ep.era_tag && (
                            <span className="text-xs bg-amber-500/10 text-amber-600 px-1.5 py-0.5 rounded">
                              {ep.era_tag}
                            </span>
                          )}
                          {ep.drama_ref && (
                            <span className="text-xs bg-blue-500/10 text-blue-500 px-1.5 py-0.5 rounded">
                              드라마: {ep.drama_ref}
                            </span>
                          )}
                          <span className={`text-xs ${STATUS_CONFIG[ep.status]?.color ?? "text-muted-foreground"}`}>
                            {STATUS_CONFIG[ep.status]?.label ?? ep.status}
                          </span>
                        </div>
                        {ep.notes && (
                          <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{ep.notes}</p>
                        )}
                        {ep.project_id && (
                          <PipelineBar step={ep.pipeline_step ?? "idle"} />
                        )}
                      </div>

                      {/* 액션 */}
                      <div className="flex items-center gap-1 shrink-0">
                        {ep.project_id ? (
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-xs h-7"
                            onClick={() => router.push(`/projects/${ep.project_id}`)}
                          >
                            프로젝트 보기
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            className="text-xs h-7"
                            disabled={generatingEp === ep.id}
                            onClick={() => generateEpisode(ep)}
                          >
                            {generatingEp === ep.id ? "생성 중..." : "생성 시작 →"}
                          </Button>
                        )}
                        <button
                          className="text-xs text-muted-foreground hover:text-red-500 ml-1"
                          onClick={() => deleteEpisode(ep)}
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            {series.episodes.length === 0 && !showAddEp && (
              <p className="text-sm text-muted-foreground text-center py-4">
                에피소드가 없습니다. 추가 버튼으로 에피소드를 기획해보세요.
              </p>
            )}

            {/* 에피소드 추가 폼 */}
            {showAddEp && (
              <div className="border rounded-xl p-4 space-y-3 bg-muted/10">
                <div className="text-sm font-medium">새 에피소드</div>
                <Input
                  placeholder="에피소드 제목 * (예: Dangun Myth — Korea's Origin Story)"
                  value={newEpTitle}
                  onChange={e => setNewEpTitle(e.target.value)}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="파트명 (예: Part 1: Origins)"
                    value={newEpPartName}
                    onChange={e => setNewEpPartName(e.target.value)}
                  />
                  <Input
                    placeholder="시대 태그 (예: 고조선, 삼국시대)"
                    value={newEpEraTag}
                    onChange={e => setNewEpEraTag(e.target.value)}
                  />
                </div>
                <Input
                  placeholder="K드라마 연결 (예: 주몽, 대장금)"
                  value={newEpDramaRef}
                  onChange={e => setNewEpDramaRef(e.target.value)}
                />
                <textarea
                  placeholder="기획 메모 (선택)"
                  value={newEpNotes}
                  onChange={e => setNewEpNotes(e.target.value)}
                  rows={2}
                  className="w-full p-2 text-sm bg-background border border-input rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={addEpisode} disabled={addingEp || !newEpTitle.trim()}>
                    {addingEp ? "추가 중..." : "추가"}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setShowAddEp(false)}>
                    취소
                  </Button>
                </div>
              </div>
            )}

          </CardContent>
        </Card>
      </div>
    </div>
  );
}
