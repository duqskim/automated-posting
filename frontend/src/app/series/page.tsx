"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

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
  characters: { id: number; name: string }[];
}

const CATEGORY_LABELS: Record<string, string> = {
  history: "역사",
  finance: "재테크",
  kids: "어린이",
  drama: "드라마",
  science: "과학",
  custom: "커스텀",
};

const MARKET_FLAGS: Record<string, string> = {
  kr: "🇰🇷", us: "🇺🇸", jp: "🇯🇵", global: "🌍",
};

const FACT_MODE_LABELS: Record<string, { label: string; color: string }> = {
  strict: { label: "팩트 엄격", color: "text-red-500" },
  standard: { label: "팩트 표준", color: "text-yellow-500" },
  none: { label: "팩트 없음", color: "text-muted-foreground" },
};

export default function SeriesListPage() {
  const router = useRouter();
  const [seriesList, setSeriesList] = useState<Series[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { router.push("/login"); return; }

    api.series.list()
      .then(setSeriesList)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [router]);

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`"${name}" 시리즈를 삭제하시겠습니까?\n에피소드와 캐릭터도 모두 삭제됩니다.`)) return;
    await api.series.delete(id);
    setSeriesList(prev => prev.filter(s => s.id !== id));
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b sticky top-0 bg-background z-10">
        <div className="container mx-auto flex items-center justify-between h-14 px-4">
          <button onClick={() => router.push("/dashboard")} className="text-lg font-bold hover:opacity-80">
            Automated Posting
          </button>
          <Button size="sm" onClick={() => router.push("/series/new")}>
            + 새 시리즈
          </Button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 max-w-3xl">
        <div className="mb-6">
          <h2 className="text-2xl font-bold mb-1">시리즈</h2>
          <p className="text-muted-foreground text-sm">
            연속 에피소드로 구성된 콘텐츠 시리즈를 관리합니다
          </p>
        </div>

        {loading ? (
          <p className="text-muted-foreground text-sm">로딩 중...</p>
        ) : seriesList.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-muted-foreground mb-4">아직 시리즈가 없습니다</p>
              <Button onClick={() => router.push("/series/new")}>
                첫 시리즈 만들기
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {seriesList.map(s => (
              <Card
                key={s.id}
                className="cursor-pointer hover:border-primary/40 transition-colors"
                onClick={() => router.push(`/series/${s.id}`)}
              >
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-lg">{MARKET_FLAGS[s.market] ?? "🌐"}</span>
                        <h3 className="font-semibold text-base truncate">{s.name}</h3>
                      </div>
                      {s.description && (
                        <p className="text-sm text-muted-foreground mb-2 line-clamp-2">
                          {s.description}
                        </p>
                      )}
                      <div className="flex flex-wrap gap-2 items-center">
                        <Badge variant="outline" className="text-xs">
                          {CATEGORY_LABELS[s.category] ?? s.category}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          에피소드 {s.episode_count}개
                        </span>
                        {s.characters.length > 0 && (
                          <span className="text-xs text-purple-400">
                            캐릭터: {s.characters.map(c => c.name).join(", ")}
                          </span>
                        )}
                        <span className={`text-xs ${FACT_MODE_LABELS[s.fact_mode]?.color}`}>
                          {FACT_MODE_LABELS[s.fact_mode]?.label}
                        </span>
                      </div>
                    </div>
                    <button
                      className="text-xs text-muted-foreground hover:text-red-500 shrink-0 mt-0.5"
                      onClick={e => { e.stopPropagation(); handleDelete(s.id, s.name); }}
                    >
                      삭제
                    </button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
