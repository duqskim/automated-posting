"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
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
  is_urgent: boolean;
}

interface User {
  id: number;
  email: string;
  name: string;
}

const MARKET_FLAGS: Record<string, string> = {
  kr: "🇰🇷", us: "🇺🇸", jp: "🇯🇵", global: "🌍",
};

const STATUS_LABELS: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  created: { label: "생성됨", variant: "outline" },
  researching: { label: "리서치 중", variant: "secondary" },
  writing: { label: "글쓰기 중", variant: "secondary" },
  producing: { label: "미디어 제작", variant: "secondary" },
  passed: { label: "완료", variant: "default" },
  published: { label: "발행됨", variant: "default" },
  failed: { label: "실패", variant: "destructive" },
};

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [series, setSeries] = useState<{ id: number; name: string; market: string; category: string; episode_count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      router.push("/login");
      return;
    }

    Promise.all([api.auth.me(), api.projects.list(), api.series.list()])
      .then(([userData, projectsData, seriesData]) => {
        setUser(userData);
        setProjects(projectsData);
        setSeries(seriesData);
      })
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  const deleteProject = async (e: React.MouseEvent, id: number) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("프로젝트를 삭제하시겠습니까? 생성된 콘텐츠도 모두 삭제됩니다.")) return;
    setDeletingId(id);
    try {
      await api.projects.delete(id);
      setProjects(prev => prev.filter(p => p.id !== id));
    } catch {
      alert("삭제에 실패했습니다.");
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">로딩 중...</p>
      </div>
    );
  }

  const stats = {
    total: projects.length,
    inProgress: projects.filter((p) =>
      ["researching", "writing", "producing"].includes(p.status)
    ).length,
    completed: projects.filter((p) =>
      ["passed", "published"].includes(p.status)
    ).length,
    failed: projects.filter((p) => p.status === "failed").length,
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b">
        <div className="container mx-auto flex items-center justify-between h-14 px-4">
          <h1 className="text-lg font-bold">Automated Posting</h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">
              {user?.name}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                localStorage.removeItem("token");
                router.push("/login");
              }}
            >
              로그아웃
            </Button>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8">
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardContent className="pt-6 text-center">
              <div className="text-3xl font-bold">{stats.total}</div>
              <p className="text-sm text-muted-foreground">전체</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <div className="text-3xl font-bold text-yellow-500">
                {stats.inProgress}
              </div>
              <p className="text-sm text-muted-foreground">진행 중</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <div className="text-3xl font-bold text-green-500">
                {stats.completed}
              </div>
              <p className="text-sm text-muted-foreground">완료</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <div className="text-3xl font-bold text-red-500">
                {stats.failed}
              </div>
              <p className="text-sm text-muted-foreground">실패</p>
            </CardContent>
          </Card>
        </div>

        {/* Actions */}
        <div className="flex gap-3 flex-wrap mb-8">
          <Link href="/projects/new">
            <Button>새 프로젝트</Button>
          </Link>
          <Link href="/series/new">
            <Button variant="outline">새 시리즈</Button>
          </Link>
          <Link href="/accounts">
            <Button variant="outline">SNS 계정 관리</Button>
          </Link>
          <Link href="/plan">
            <Button variant="outline">Korea Untold 플랜</Button>
          </Link>
        </div>

        {/* Series List */}
        {series.length > 0 && (
          <Card className="mb-6">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">시리즈</CardTitle>
                <Link href="/series" className="text-xs text-primary hover:underline">
                  전체 보기
                </Link>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <div className="divide-y">
                {series.map(s => (
                  <Link key={s.id} href={`/series/${s.id}`}
                    className="flex items-center gap-3 py-3 -mx-4 px-4 hover:bg-muted/20 transition-colors rounded-lg"
                  >
                    <span className="text-lg">{MARKET_FLAGS[s.market] ?? "🌐"}</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm truncate">{s.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {s.category} · 에피소드 {s.episode_count}개
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Project List */}
        <Card>
          <CardHeader>
            <CardTitle>프로젝트</CardTitle>
          </CardHeader>
          <CardContent>
            {projects.length === 0 ? (
              <p className="text-muted-foreground text-center py-8">
                아직 프로젝트가 없습니다.
                <br />
                <Link
                  href="/projects/new"
                  className="text-primary underline mt-2 inline-block"
                >
                  첫 프로젝트 만들기
                </Link>
              </p>
            ) : (
              <div className="divide-y">
                {projects.map((project) => {
                  const statusInfo = STATUS_LABELS[project.status] || {
                    label: project.status,
                    variant: "outline" as const,
                  };
                  return (
                    <div key={project.id} className="flex items-center justify-between py-4 -mx-4 px-4 rounded-lg">
                      <Link
                        href={`/projects/${project.id}`}
                        className="flex-1 flex items-center justify-between hover:opacity-80 transition-opacity min-w-0"
                      >
                        <div className="font-medium truncate pr-4">{project.topic}</div>
                        <div className="flex items-center gap-3 flex-shrink-0">
                          <span className="text-lg">{MARKET_FLAGS[project.market] || ""}</span>
                          <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
                        </div>
                      </Link>
                      <button
                        onClick={(e) => deleteProject(e, project.id)}
                        disabled={deletingId === project.id}
                        className="ml-3 flex-shrink-0 text-muted-foreground hover:text-red-500 transition-colors disabled:opacity-40 text-sm"
                        title="삭제"
                      >
                        {deletingId === project.id ? "…" : "🗑️"}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
