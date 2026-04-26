"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

const MARKETS = [
  { code: "global", flag: "🌍", name: "Global", lang: "English" },
  { code: "kr",     flag: "🇰🇷", name: "한국",  lang: "한국어" },
  { code: "us",     flag: "🇺🇸", name: "North America", lang: "English" },
  { code: "jp",     flag: "🇯🇵", name: "日本", lang: "日本語" },
];

const CATEGORIES = [
  { code: "history",  label: "역사", desc: "시대별 역사 스토리텔링" },
  { code: "finance",  label: "재테크", desc: "투자/경제 교육 콘텐츠" },
  { code: "drama",    label: "드라마 팩트체크", desc: "드라마 vs 실제 역사" },
  { code: "kids",     label: "어린이", desc: "어린이용 교육 콘텐츠" },
  { code: "science",  label: "과학", desc: "과학/테크 설명" },
  { code: "custom",   label: "커스텀", desc: "자유 형식" },
];

const VISUAL_STYLES = [
  { code: "cinematic",    label: "시네마틱", desc: "어둡고 극적인 영화 스타일" },
  { code: "modern",       label: "모던",    desc: "깔끔하고 현대적" },
  { code: "documentary",  label: "다큐",    desc: "사실적이고 저널리즘 스타일" },
  { code: "cartoon",      label: "카툰",    desc: "일러스트/애니메이션 스타일" },
  { code: "minimal",      label: "미니멀",  desc: "텍스트 중심, 단색 배경" },
];

const FACT_MODES = [
  { code: "strict",   label: "엄격 (역사/교육)", desc: "불확실한 내용도 모두 경고" },
  { code: "standard", label: "표준",             desc: "명백한 오류만 검출" },
  { code: "none",     label: "없음",             desc: "팩트체크 생략" },
];

const PLATFORM_OPTIONS = [
  "youtube", "youtube_shorts", "instagram", "tiktok",
  "x", "threads", "linkedin", "newsletter",
];

export default function NewSeriesPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [market, setMarket] = useState("global");
  const [category, setCategory] = useState("history");
  const [visualStyle, setVisualStyle] = useState("cinematic");
  const [factMode, setFactMode] = useState("strict");
  const [platforms, setPlatforms] = useState<string[]>(["youtube", "youtube_shorts"]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const togglePlatform = (p: string) =>
    setPlatforms(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    setError("");
    try {
      const langMap: Record<string, string> = { global: "en", kr: "ko", us: "en", jp: "ja" };
      const series = await api.series.create({
        name: name.trim(),
        description: description.trim() || undefined,
        market,
        language: langMap[market] ?? "en",
        category,
        visual_style: visualStyle,
        fact_mode: factMode,
        target_platforms: platforms,
      });
      router.push(`/series/${series.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "시리즈 생성 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto flex items-center h-14 px-4">
          <button onClick={() => router.push("/series")} className="text-lg font-bold hover:opacity-80">
            Automated Posting
          </button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 max-w-2xl">
        <h2 className="text-2xl font-bold mb-1">새 시리즈</h2>
        <p className="text-muted-foreground text-sm mb-8">
          연속 에피소드 시리즈의 기본 설정을 정합니다
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Card>
            <CardContent className="pt-6 space-y-6">

              {/* 이름 */}
              <div className="space-y-2">
                <Label htmlFor="name">시리즈 이름 *</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="예: Korea Untold, 한국사 외국인 편"
                  required autoFocus
                />
              </div>

              {/* 설명 */}
              <div className="space-y-2">
                <Label htmlFor="desc">설명 (선택)</Label>
                <textarea
                  id="desc"
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="시리즈 목적과 타겟 설명..."
                  rows={2}
                  className="w-full p-3 text-sm bg-background border border-input rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* 시장 */}
              <div className="space-y-3">
                <Label>시장 / 언어 *</Label>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {MARKETS.map(m => (
                    <button key={m.code} type="button" onClick={() => setMarket(m.code)}
                      className={`p-3 rounded-lg border-2 text-center transition-all ${
                        market === m.code
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50"
                      }`}
                    >
                      <div className="text-xl mb-0.5">{m.flag}</div>
                      <div className="text-xs font-medium">{m.name}</div>
                      <div className="text-xs text-muted-foreground">{m.lang}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* 카테고리 */}
              <div className="space-y-3">
                <Label>카테고리</Label>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {CATEGORIES.map(c => (
                    <button key={c.code} type="button" onClick={() => setCategory(c.code)}
                      className={`p-3 rounded-lg border-2 text-left transition-all ${
                        category === c.code
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50"
                      }`}
                    >
                      <div className="text-sm font-medium">{c.label}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{c.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* 비주얼 스타일 */}
              <div className="space-y-3">
                <Label>비주얼 스타일</Label>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {VISUAL_STYLES.map(v => (
                    <button key={v.code} type="button" onClick={() => setVisualStyle(v.code)}
                      className={`p-3 rounded-lg border-2 text-left transition-all ${
                        visualStyle === v.code
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50"
                      }`}
                    >
                      <div className="text-sm font-medium">{v.label}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{v.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* 팩트체크 모드 */}
              <div className="space-y-3">
                <Label>팩트체크 강도</Label>
                <div className="space-y-2">
                  {FACT_MODES.map(f => (
                    <label key={f.code}
                      className={`flex items-start gap-3 p-3 rounded-lg border-2 cursor-pointer transition-all ${
                        factMode === f.code
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50"
                      }`}
                    >
                      <input
                        type="radio"
                        checked={factMode === f.code}
                        onChange={() => setFactMode(f.code)}
                        className="mt-0.5"
                      />
                      <div>
                        <div className="text-sm font-medium">{f.label}</div>
                        <div className="text-xs text-muted-foreground">{f.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* 기본 플랫폼 */}
              <div className="space-y-3">
                <Label>기본 발행 플랫폼</Label>
                <div className="flex flex-wrap gap-2">
                  {PLATFORM_OPTIONS.map(p => (
                    <Badge
                      key={p}
                      variant={platforms.includes(p) ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => togglePlatform(p)}
                    >
                      {p}
                    </Badge>
                  ))}
                </div>
              </div>

            </CardContent>
          </Card>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex gap-3">
            <Button type="submit" disabled={loading || !name.trim()}>
              {loading ? "생성 중..." : "시리즈 만들기"}
            </Button>
            <Button type="button" variant="outline" onClick={() => router.push("/series")}>
              취소
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
