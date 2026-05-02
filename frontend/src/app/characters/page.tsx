"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import AppShell from "@/components/AppShell";

interface Character {
  id: number;
  name: string;
  status: string;
  concept: string | null;
  personality: string | null;
  visual_description: string | null;
  reference_image_url: string | null;
  series_id: number | null;
  series_name: string | null;
  bible: Record<string, unknown> | null;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function CharacterCard({ char, seriesList, onAssign }: {
  char: Character;
  seriesList: { id: number; name: string }[];
  onAssign: (charId: number, seriesId: number | null) => Promise<void>;
}) {
  const [assigning, setAssigning] = useState(false);
  const [showAssign, setShowAssign] = useState(false);

  const handleAssign = async (seriesId: number | null) => {
    setAssigning(true);
    await onAssign(char.id, seriesId);
    setAssigning(false);
    setShowAssign(false);
  };

  const imgUrl = char.reference_image_url
    ? char.reference_image_url.startsWith("/api/")
      ? `${API_BASE}${char.reference_image_url}`
      : char.reference_image_url
    : null;

  return (
    <div className="border rounded-xl overflow-hidden bg-card">
      {/* 이미지 영역 */}
      <div className="aspect-square bg-muted/30 flex items-center justify-center relative">
        {imgUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imgUrl}
            alt={char.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="text-4xl opacity-30">◉</span>
        )}
        <div className="absolute top-2 right-2">
          <Badge
            variant={char.status === "active" ? "default" : "outline"}
            className="text-xs"
          >
            {char.status === "active" ? "완성" : "설계 중"}
          </Badge>
        </div>
      </div>

      {/* 정보 */}
      <div className="p-3 space-y-2">
        <div>
          <h3 className="font-semibold text-sm">{char.name || "이름 없음"}</h3>
          {char.concept && (
            <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">{char.concept}</p>
          )}
        </div>

        {/* 시리즈 연결 */}
        <div className="flex items-center justify-between">
          <div className="text-xs text-muted-foreground">
            {char.series_name ? (
              <Link href={`/series/${char.series_id}`} className="text-primary hover:underline">
                {char.series_name}
              </Link>
            ) : (
              <span className="italic">시리즈 없음</span>
            )}
          </div>
          <button
            onClick={() => setShowAssign(!showAssign)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            연결 변경
          </button>
        </div>

        {/* 시리즈 연결 패널 */}
        {showAssign && (
          <div className="border rounded p-2 space-y-1 bg-muted/20">
            <button
              onClick={() => handleAssign(null)}
              disabled={assigning}
              className="w-full text-left text-xs px-2 py-1 rounded hover:bg-muted/50 text-muted-foreground"
            >
              연결 해제
            </button>
            {seriesList.map(s => (
              <button
                key={s.id}
                onClick={() => handleAssign(s.id)}
                disabled={assigning}
                className={`w-full text-left text-xs px-2 py-1 rounded hover:bg-muted/50 ${
                  char.series_id === s.id ? "font-semibold text-primary" : ""
                }`}
              >
                {s.name}
              </button>
            ))}
          </div>
        )}

        {/* 스튜디오 링크 */}
        {char.series_id && (
          <Link
            href={`/series/${char.series_id}/character/${char.id}`}
            className="block text-center text-xs border rounded py-1.5 hover:bg-muted/30 transition-colors text-muted-foreground"
          >
            캐릭터 스튜디오 열기
          </Link>
        )}
      </div>
    </div>
  );
}

export default function CharactersPage() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [series, setSeries] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.characters.list(), api.series.list()])
      .then(([chars, srs]) => {
        setCharacters(chars);
        setSeries(srs);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleAssign = async (charId: number, seriesId: number | null) => {
    await api.characters.assignSeries(charId, seriesId);
    const updated = await api.characters.list();
    setCharacters(updated);
  };

  const active = characters.filter(c => c.status === "active").length;
  const draft = characters.filter(c => c.status !== "active").length;

  return (
    <AppShell>
      <div className="p-6 max-w-5xl mx-auto">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold">캐릭터 라이브러리</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {active}개 완성 · {draft}개 설계 중 — 모든 시리즈에서 재활용 가능
            </p>
          </div>
          <div className="text-sm text-muted-foreground">
            시리즈 내에서 캐릭터를 만들면 여기에 자동 추가됩니다
          </div>
        </div>

        {loading ? (
          <div className="text-center py-16 text-muted-foreground">로딩 중...</div>
        ) : characters.length === 0 ? (
          <div className="text-center py-16 border rounded-xl">
            <p className="text-4xl mb-4 opacity-30">◉</p>
            <p className="text-muted-foreground text-sm mb-4">아직 캐릭터가 없습니다.</p>
            <p className="text-muted-foreground text-xs mb-6">
              시리즈 페이지에서 캐릭터 스튜디오를 열어 첫 캐릭터를 만들어보세요.
            </p>
            <Link href="/series">
              <Button size="sm">시리즈로 이동</Button>
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {characters.map(char => (
              <CharacterCard
                key={char.id}
                char={char}
                seriesList={series}
                onAssign={handleAssign}
              />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
