"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import AppShell from "@/components/AppShell";

interface Project {
  id: number;
  topic: string;
  market: string;
  status: string;
  is_urgent: boolean;
}

interface SeriesItem {
  id: number;
  name: string;
  market: string;
  category: string;
  episode_count: number;
}

const MARKET_FLAGS: Record<string, string> = {
  kr: "🇰🇷", us: "🇺🇸", jp: "🇯🇵", global: "🌍",
};

const STATUS_META: Record<string, { label: string; color: string }> = {
  created:     { label: "대기",     color: "text-muted-foreground" },
  researching: { label: "리서치",   color: "text-blue-500" },
  writing:     { label: "글쓰기",   color: "text-blue-500" },
  producing:   { label: "미디어",   color: "text-blue-500" },
  passed:      { label: "완료",     color: "text-green-500" },
  published:   { label: "발행됨",   color: "text-green-600" },
  failed:      { label: "실패",     color: "text-red-500" },
};

function StatusDot({ status }: { status: string }) {
  const meta = STATUS_META[status] ?? { label: status, color: "text-muted-foreground" };
  return (
    <span className={`text-xs font-medium ${meta.color}`}>{meta.label}</span>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [series, setSeries] = useState<SeriesItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.projects.list(), api.series.list()])
      .then(([p, s]) => { setProjects(p); setSeries(s); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const deleteProject = async (e: React.MouseEvent, id: number) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("프로젝트를 삭제하시겠습니까?")) return;
    await api.projects.delete(id).catch(() => {});
    setProjects(prev => prev.filter(p => p.id !== id));
  };

  const inProgress = projects.filter(p => ["researching", "writing", "producing"].includes(p.status)).length;
  const done = projects.filter(p => ["passed", "published"].includes(p.status)).length;

  return (
    <AppShell>
      <div className="p-6 max-w-4xl mx-auto">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold">대시보드</h1>
          <div className="flex gap-2">
            <Link href="/series/new">
              <Button variant="outline" size="sm">새 시리즈</Button>
            </Link>
            <Link href="/projects/new">
              <Button size="sm">새 프로젝트</Button>
            </Link>
          </div>
        </div>

        {/* 통계 */}
        <div className="grid grid-cols-3 gap-3 mb-8">
          {[
            { label: "전체 프로젝트", value: projects.length, color: "" },
            { label: "진행 중", value: inProgress, color: "text-blue-500" },
            { label: "완료", value: done, color: "text-green-500" },
          ].map(s => (
            <div key={s.label} className="border rounded-lg p-4 text-center">
              <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>

        {/* 시리즈 */}
        {series.length > 0 && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">시리즈</h2>
              <Link href="/series" className="text-xs text-primary hover:underline">전체 보기</Link>
            </div>
            <div className="space-y-2">
              {series.map(s => (
                <Link
                  key={s.id}
                  href={`/series/${s.id}`}
                  className="flex items-center gap-3 border rounded-lg px-4 py-3 hover:bg-muted/30 transition-colors"
                >
                  <span className="text-xl">{MARKET_FLAGS[s.market] ?? "🌐"}</span>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{s.name}</div>
                    <div className="text-xs text-muted-foreground">{s.category} · 에피소드 {s.episode_count}개</div>
                  </div>
                  <span className="text-muted-foreground text-xs">→</span>
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* 최근 프로젝트 */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">최근 프로젝트</h2>
          </div>
          {loading ? (
            <div className="text-center py-8 text-muted-foreground text-sm">로딩 중...</div>
          ) : projects.length === 0 ? (
            <div className="text-center py-12 border rounded-lg">
              <p className="text-muted-foreground text-sm mb-4">아직 프로젝트가 없습니다.</p>
              <Link href="/projects/new">
                <Button size="sm">첫 프로젝트 만들기</Button>
              </Link>
            </div>
          ) : (
            <div className="space-y-1">
              {projects.slice(0, 20).map(p => (
                <div key={p.id} className="flex items-center gap-2">
                  <Link
                    href={`/projects/${p.id}`}
                    className="flex-1 flex items-center gap-3 border rounded-lg px-4 py-3 hover:bg-muted/30 transition-colors min-w-0"
                  >
                    <span>{MARKET_FLAGS[p.market] ?? ""}</span>
                    <span className="flex-1 text-sm truncate">{p.topic}</span>
                    <StatusDot status={p.status} />
                    {p.is_urgent && <Badge variant="destructive" className="text-xs py-0">긴급</Badge>}
                  </Link>
                  <button
                    onClick={e => deleteProject(e, p.id)}
                    className="p-2 text-muted-foreground hover:text-red-500 transition-colors text-sm flex-shrink-0"
                    title="삭제"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
