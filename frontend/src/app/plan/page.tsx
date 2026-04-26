"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const PARTS = [
  {
    part: "Part 1 — Origins",
    era: "고대~삼국",
    episodes: [
      { ep: 1, title: "단군신화 — The Bear Who Became a Woman", drama: null },
      { ep: 2, title: "고조선 — Korea's First Kingdom (2333 BCE)", drama: null },
      { ep: 3, title: "고구려 — The Empire that Fought China", drama: null },
      { ep: 4, title: "백제 — The Kingdom that Civilized Japan", drama: null },
      { ep: 5, title: "신라 — The Women Warriors & Bone Ranks", drama: null },
      { ep: 6, title: "가야 — The Lost Kingdom", drama: null },
      { ep: 7, title: "삼국통일 — Why Silla Won (and the price it paid)", drama: null },
    ],
  },
  {
    part: "Part 2 — The Golden Age",
    era: "고려",
    episodes: [
      { ep: 8, title: "왕건 — The Merchant Who Became King", drama: "태조 왕건" },
      { ep: 9, title: "팔만대장경 — 80,000 Wooden Blocks vs. the Mongols", drama: null },
      { ep: 10, title: "몽골 침략 — 30 Years of Resistance", drama: null },
      { ep: 11, title: "공민왕 & 기황후 — The Queen Who Ruled the Yuan Empire", drama: "기황후" },
      { ep: 12, title: "고려 청자 — The Most Beautiful Pottery in the World", drama: null },
    ],
  },
  {
    part: "Part 3 — Joseon",
    era: "조선 전기",
    episodes: [
      { ep: 13, title: "이성계 — The Archer who Overthrew a Dynasty", drama: "육룡이 나르샤" },
      { ep: 14, title: "세종대왕 — The King who Invented an Alphabet", drama: null },
      { ep: 15, title: "장영실 — The Slave who Built Korea's First Clock", drama: null },
      { ep: 16, title: "조선의 여인들 — Women in Joseon: The Real Rules", drama: "대장금" },
      { ep: 17, title: "사화 — When Scholars Got Executed for Writing", drama: null },
      { ep: 18, title: "임진왜란 — The Turtle Ships vs. 200,000 Japanese Soldiers", drama: null },
      { ep: 19, title: "이순신 — The Admiral who Saved Korea (and died doing it)", drama: null },
    ],
  },
  {
    part: "Part 4 — Joseon (Late)",
    era: "조선 후기~말기",
    episodes: [
      { ep: 20, title: "광해군 — The King History Got Wrong", drama: "광해, 왕이 된 남자" },
      { ep: 21, title: "영조 & 사도세자 — A Father who Killed His Son", drama: "옷소매 붉은 끝동" },
      { ep: 22, title: "흥선대원군 — Korea's Last Strongman", drama: null },
      { ep: 23, title: "명성황후 — The Queen Murdered by Japan", drama: "명성황후" },
      { ep: 24, title: "구한말 — Korea at the Crossroads", drama: "미스터 션샤인" },
    ],
  },
  {
    part: "Part 5 — Modern Korea",
    era: "근현대",
    episodes: [
      { ep: 25, title: "3.1운동 — One Million People Said No", drama: null },
      { ep: 26, title: "독립운동가들 — The Fighters Nobody Talks About", drama: null },
      { ep: 27, title: "한국전쟁 — The War that Never Officially Ended", drama: null },
      { ep: 28, title: "한강의 기적 — From the Poorest to the Richest in 30 Years", drama: null },
      { ep: 29, title: "민주화 운동 — How Korea Built Its Democracy", drama: null },
      { ep: 30, title: "K-Wave의 기원 — Why Korean Culture Went Global", drama: null },
    ],
  },
];

const SHORTS_EXAMPLES = [
  { drama: "대장금", fact: "Was Jang Geum a real person? (실존 여부)" },
  { drama: "기황후", fact: "How powerful was Empress Ki really?" },
  { drama: "킹덤", fact: "Joseon's real disease outbreaks" },
  { drama: "미스터 션샤인", fact: "The real American-Korean soldiers" },
];

export default function PlanPage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* 헤더 */}
        <div className="mb-2">
          <Link href="/dashboard" className="text-xs text-muted-foreground hover:text-foreground">
            ← 대시보드
          </Link>
        </div>
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-bold">Korea Untold</h1>
            <Badge variant="outline">30 Episodes</Badge>
            <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/20">YouTube · English</Badge>
          </div>
          <p className="text-muted-foreground italic text-lg">The Real Story Behind the Drama</p>
          <div className="mt-3 flex flex-wrap gap-2 text-sm text-muted-foreground">
            <span>타겟: 해외 K드라마/K팝 팬 (10~35세)</span>
            <span>·</span>
            <span>언어: 영어 (한국어 자막 병행)</span>
            <span>·</span>
            <span>포맷: 역사 스토리 + K드라마 팩트체크</span>
          </div>
        </div>

        {/* 에피소드 목록 */}
        <div className="space-y-6">
          {PARTS.map((part) => (
            <Card key={part.part}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{part.part}</CardTitle>
                  <Badge variant="secondary" className="text-xs">{part.era}</Badge>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="divide-y divide-border">
                  {part.episodes.map((ep) => (
                    <div key={ep.ep} className="flex items-start gap-3 px-5 py-3">
                      <span className="text-xs font-mono text-muted-foreground w-8 shrink-0 mt-0.5">
                        EP{ep.ep}
                      </span>
                      <span className="text-sm flex-1">{ep.title}</span>
                      {ep.drama && (
                        <Badge variant="outline" className="text-xs shrink-0 border-orange-500/30 text-orange-500">
                          {ep.drama} 팩트체크
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Drama vs Reality Shorts */}
        <Card className="mt-6">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Drama vs Reality</CardTitle>
              <Badge className="bg-orange-500/10 text-orange-500 border-orange-500/20 text-xs">Shorts 별도 시리즈</Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              3분 Shorts — 드라마 장면 팩트체크 → 본편 유입
            </p>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {SHORTS_EXAMPLES.map((s, i) => (
                <div key={i} className="flex items-start gap-3 px-5 py-3">
                  <Badge variant="outline" className="text-xs shrink-0 border-orange-500/30 text-orange-500">
                    {s.drama}
                  </Badge>
                  <span className="text-sm">{s.fact}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* 제작 전략 */}
        <Card className="mt-6">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">제작 전략</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div>
              <div className="font-medium mb-1">타겟 오디언스</div>
              <div className="space-y-1 text-muted-foreground">
                <p>1차: K드라마 팬 (해외 여성 18-35세) — K드라마를 통해 역사가 궁금해진 층</p>
                <p>2차: 한국 문화 관심 외국인 (Reddit r/korea, r/kdrama)</p>
                <p>3차: 해외 교포 2세 — 자기 뿌리 찾기</p>
              </div>
            </div>
            <div>
              <div className="font-medium mb-1">캐릭터 아키타입</div>
              <p className="text-muted-foreground">
                Explorer + Jester 혼합 — 같이 탐험하는 동료이자 유머로 장벽을 낮추는 가이드.
                &quot;설명하는 사람&quot;이 아니라 &quot;같이 발견하는 사람&quot;.
              </p>
            </div>
            <div>
              <div className="font-medium mb-1">구현 단계</div>
              <div className="space-y-1 text-muted-foreground">
                <p>Phase 1 (즉시): global 마켓 활성화 → EP1 단군신화 테스트</p>
                <p>Phase 2 (1~2주): 시리즈 에피소드 DB + 일괄 생성 UI</p>
                <p>Phase 3 (3~4주): Drama vs Reality 전용 포맷 + 일관된 비주얼 스타일</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
