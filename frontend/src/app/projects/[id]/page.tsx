"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

interface Project {
  id: number;
  topic: string;
  market: string;
  language: string;
  status: string;
  target_platforms: string[];
  is_urgent: boolean;
}

interface PipelineResult {
  project_id: number;
  stage: string;
  score: number | null;
  platforms_completed: number;
  platforms_total: number;
  error: string | null;
}

interface ContentPreview {
  platform: string;
  hook: string;
  body_parts: number;
  caption_preview: string;
  hashtags: string[];
}

const PIPELINE_STEPS = [
  { key: "researching", label: "리서치", icon: "🔍" },
  { key: "hooking", label: "훅 생성", icon: "🎣" },
  { key: "writing", label: "글쓰기", icon: "✍️" },
  { key: "quality_check", label: "품질 검수", icon: "✅" },
  { key: "designing", label: "디자인", icon: "🎨" },
  { key: "rendering", label: "이미지", icon: "🖼️" },
  { key: "review", label: "리뷰", icon: "👁️" },
  { key: "publishing", label: "발행", icon: "🚀" },
];

const MARKET_FLAGS: Record<string, string> = { kr: "🇰🇷", us: "🇺🇸", jp: "🇯🇵" };

function getStepStatus(currentStatus: string, stepKey: string) {
  const order = PIPELINE_STEPS.map((s) => s.key);
  const currentIndex = order.indexOf(currentStatus);
  const stepIndex = order.indexOf(stepKey);

  if (currentStatus === "passed" || currentStatus === "published") return "done";
  if (currentStatus === "failed") {
    if (stepIndex <= currentIndex) return "fail";
    return "pending";
  }
  if (stepIndex < currentIndex) return "done";
  if (stepIndex === currentIndex) return "active";
  return "pending";
}

export default function ProjectDetailPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = Number(params.id);

  const [project, setProject] = useState<Project | null>(null);
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null);
  const [previews, setPreviews] = useState<ContentPreview[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

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
  }, [loadProject, router]);

  const runPipeline = async () => {
    setRunning(true);
    setError("");
    setPipelineResult(null);
    setPreviews([]);

    try {
      const result = await api.pipeline.run(projectId);
      setPipelineResult(result);
      await loadProject();

      if (result.stage === "passed") {
        try {
          const previewData = await api.pipeline.preview(projectId);
          setPreviews(previewData);
        } catch {
          // 미리보기 실패해도 OK
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "파이프라인 실행 실패");
    } finally {
      setRunning(false);
    }
  };

  if (!project) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">로딩 중...</p>
      </div>
    );
  }

  const displayStatus = pipelineResult?.stage || project.status;

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto flex items-center justify-between h-14 px-4">
          <button onClick={() => router.push("/dashboard")} className="text-lg font-bold hover:opacity-80">
            Automated Posting
          </button>
          <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard")}>
            목록으로
          </Button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* 프로젝트 정보 */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xl">{MARKET_FLAGS[project.market]}</span>
            <h2 className="text-2xl font-bold">{project.topic}</h2>
          </div>
          <div className="flex gap-2">
            {project.target_platforms?.map((p) => (
              <Badge key={p} variant="outline">{p}</Badge>
            ))}
          </div>
        </div>

        {/* 파이프라인 진행 상태 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">파이프라인</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 md:grid-cols-8 gap-2 mb-6">
              {PIPELINE_STEPS.map((step) => {
                const status = getStepStatus(displayStatus, step.key);
                return (
                  <div
                    key={step.key}
                    className={`text-center p-3 rounded-lg text-xs ${
                      status === "done" ? "bg-green-500/10 text-green-500" :
                      status === "active" ? "bg-primary/10 text-primary animate-pulse" :
                      status === "fail" ? "bg-red-500/10 text-red-500" :
                      "bg-muted text-muted-foreground"
                    }`}
                  >
                    <div className="text-lg mb-1">
                      {status === "done" ? "✓" : status === "fail" ? "✗" : step.icon}
                    </div>
                    <div>{step.label}</div>
                  </div>
                );
              })}
            </div>

            {/* 점수 */}
            {pipelineResult?.score !== undefined && pipelineResult?.score !== null && (
              <div className="flex items-center gap-4 mb-4 p-4 bg-muted rounded-lg">
                <div className={`text-4xl font-bold ${
                  pipelineResult.score >= 80 ? "text-green-500" :
                  pipelineResult.score >= 60 ? "text-yellow-500" :
                  "text-red-500"
                }`}>
                  {pipelineResult.score}
                </div>
                <div className="text-sm text-muted-foreground">
                  <div>품질 점수 / 100</div>
                  <div>{pipelineResult.platforms_completed}/{pipelineResult.platforms_total} 플랫폼 완료</div>
                </div>
              </div>
            )}

            {error && (
              <div className="p-4 bg-red-500/10 text-red-500 rounded-lg mb-4 text-sm">
                {error}
              </div>
            )}

            {pipelineResult?.error && (
              <div className="p-4 bg-red-500/10 text-red-500 rounded-lg mb-4 text-sm">
                {pipelineResult.error}
              </div>
            )}

            <div className="flex gap-3">
              <Button onClick={runPipeline} disabled={running}>
                {running ? "파이프라인 실행 중..." :
                 project.status === "created" ? "파이프라인 시작" : "다시 실행"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* 콘텐츠 미리보기 */}
        {previews.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">콘텐츠 미리보기</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {previews.map((preview, i) => (
                  <div key={i} className="border rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <Badge>{preview.platform}</Badge>
                      <span className="text-sm text-muted-foreground">
                        {preview.body_parts}개 파트
                      </span>
                    </div>
                    <div className="mb-3">
                      <div className="text-sm text-muted-foreground mb-1">훅</div>
                      <div className="font-semibold">{preview.hook}</div>
                    </div>
                    <div className="mb-3">
                      <div className="text-sm text-muted-foreground mb-1">캡션</div>
                      <div className="text-sm">{preview.caption_preview}</div>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {preview.hashtags.map((tag, j) => (
                        <span key={j} className="text-xs text-primary">#{tag}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
