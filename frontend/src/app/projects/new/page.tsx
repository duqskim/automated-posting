"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

interface MarketInfo {
  code: string;
  display_name: string;
  language: string;
  primary_platforms: string[];
  secondary_platforms: string[];
}

const MARKET_FLAGS: Record<string, string> = {
  kr: "🇰🇷",
  us: "🇺🇸",
  jp: "🇯🇵",
};

export default function NewProjectPage() {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [market, setMarket] = useState("kr");
  const [markets, setMarkets] = useState<MarketInfo[]>([]);
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [isUrgent, setIsUrgent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.markets.list().then(setMarkets).catch(() => {});
  }, []);

  useEffect(() => {
    const m = markets.find((m) => m.code === market);
    if (m) {
      setSelectedPlatforms([...m.primary_platforms, ...m.secondary_platforms]);
    }
  }, [market, markets]);

  const currentMarket = markets.find((m) => m.code === market);
  const allPlatforms = currentMarket
    ? [...currentMarket.primary_platforms, ...currentMarket.secondary_platforms]
    : [];

  const togglePlatform = (platform: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(platform)
        ? prev.filter((p) => p !== platform)
        : [...prev, platform]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setLoading(true);
    setError("");

    try {
      const project = await api.projects.create({
        topic: topic.trim(),
        market,
        target_platforms: selectedPlatforms,
        is_urgent: isUrgent,
      });
      router.push(`/projects/${project.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "프로젝트 생성 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto flex items-center h-14 px-4">
          <button onClick={() => router.push("/dashboard")} className="text-lg font-bold hover:opacity-80">
            Automated Posting
          </button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 max-w-2xl">
        <h2 className="text-2xl font-bold mb-2">새 프로젝트</h2>
        <p className="text-muted-foreground mb-8">
          주제를 입력하고 시장을 선택하세요
        </p>

        <form onSubmit={handleSubmit}>
          <Card className="mb-6">
            <CardContent className="pt-6 space-y-6">
              {/* Topic */}
              <div className="space-y-2">
                <Label htmlFor="topic">주제 *</Label>
                <Input
                  id="topic"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="예: ISA 계좌 절세 전략, Top AI tools for 2025..."
                  required
                  autoFocus
                />
              </div>

              {/* Market */}
              <div className="space-y-3">
                <Label>시장 선택 *</Label>
                <div className="grid grid-cols-3 gap-3">
                  {markets.map((m) => (
                    <button
                      key={m.code}
                      type="button"
                      onClick={() => setMarket(m.code)}
                      className={`p-4 rounded-lg border-2 text-center transition-all ${
                        market === m.code
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50"
                      }`}
                    >
                      <div className="text-2xl mb-1">
                        {MARKET_FLAGS[m.code]}
                      </div>
                      <div className="font-medium text-sm">
                        {m.display_name}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {m.language}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Platforms */}
              <div className="space-y-3">
                <Label>발행 플랫폼</Label>
                <div className="flex flex-wrap gap-2">
                  {allPlatforms.map((platform) => (
                    <Badge
                      key={platform}
                      variant={
                        selectedPlatforms.includes(platform)
                          ? "default"
                          : "outline"
                      }
                      className="cursor-pointer"
                      onClick={() => togglePlatform(platform)}
                    >
                      {platform}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Mode */}
              <div className="space-y-2">
                <Label>모드</Label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer text-sm">
                    <input
                      type="radio"
                      checked={!isUrgent}
                      onChange={() => setIsUrgent(false)}
                    />
                    일반 (리뷰 후 발행)
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer text-sm">
                    <input
                      type="radio"
                      checked={isUrgent}
                      onChange={() => setIsUrgent(true)}
                    />
                    긴급 (자동 발행)
                  </label>
                </div>
              </div>
            </CardContent>
          </Card>

          {error && (
            <p className="text-sm text-destructive mb-4">{error}</p>
          )}

          <div className="flex gap-3">
            <Button type="submit" disabled={loading || !topic.trim()}>
              {loading ? "생성 중..." : "파이프라인 시작"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push("/dashboard")}
            >
              취소
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
