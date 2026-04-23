"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";

interface SNSAccount {
  id: number;
  market: string;
  platform: string;
  account_name: string;
  account_id: string | null;
  is_active: boolean;
}

const MARKET_FLAGS: Record<string, string> = { kr: "🇰🇷", us: "🇺🇸", jp: "🇯🇵" };
const MARKET_NAMES: Record<string, string> = { kr: "한국", us: "북미", jp: "일본" };

const PLATFORM_ICONS: Record<string, string> = {
  instagram: "📸",
  youtube: "▶️",
  youtube_shorts: "📱",
  x: "🐦",
  linkedin: "💼",
  threads: "🧵",
  tiktok: "🎵",
  facebook: "📘",
  naver_blog: "🟢",
  newsletter: "📧",
  pinterest: "📌",
  reddit: "🤖",
  note_com: "📝",
};

const PLATFORMS_BY_MARKET: Record<string, string[]> = {
  kr: ["instagram", "youtube", "youtube_shorts", "threads", "x", "naver_blog", "facebook"],
  us: ["youtube", "linkedin", "instagram", "newsletter", "youtube_shorts", "reddit", "tiktok", "pinterest", "threads", "x"],
  jp: ["youtube", "instagram", "x", "tiktok", "note_com", "threads"],
};

export default function AccountsPage() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<SNSAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formMarket, setFormMarket] = useState("kr");
  const [formPlatform, setFormPlatform] = useState("");
  const [formName, setFormName] = useState("");
  const [saving, setSaving] = useState(false);

  const loadAccounts = async () => {
    try {
      const data = await api.accounts.list();
      setAccounts(data);
    } catch {
      router.push("/login");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { router.push("/login"); return; }
    loadAccounts();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const handleConnect = async () => {
    if (!formPlatform || !formName.trim()) return;
    setSaving(true);
    try {
      await api.accounts.connect({
        market: formMarket,
        platform: formPlatform,
        account_name: formName.trim(),
      });
      setShowForm(false);
      setFormName("");
      setFormPlatform("");
      await loadAccounts();
    } catch {
      alert("계정 연결 실패");
    } finally {
      setSaving(false);
    }
  };

  const handleDisconnect = async (id: number, name: string) => {
    if (!confirm(`${name} 계정을 연결 해제할까요?`)) return;
    try {
      await api.accounts.disconnect(id);
      await loadAccounts();
    } catch {
      alert("연결 해제 실패");
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center"><p className="text-muted-foreground">로딩 중...</p></div>;
  }

  const groupedByMarket = accounts.reduce((acc, a) => {
    if (!acc[a.market]) acc[a.market] = [];
    acc[a.market].push(a);
    return acc;
  }, {} as Record<string, SNSAccount[]>);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto flex items-center justify-between h-14 px-4">
          <button onClick={() => router.push("/dashboard")} className="text-lg font-bold hover:opacity-80">
            Automated Posting
          </button>
          <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard")}>
            대시보드
          </Button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 max-w-3xl">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-2xl font-bold">SNS 계정 관리</h2>
            <p className="text-muted-foreground text-sm mt-1">플랫폼별 계정 연결 · 시장별 분리</p>
          </div>
          <Button onClick={() => setShowForm(!showForm)}>
            {showForm ? "취소" : "계정 추가"}
          </Button>
        </div>

        {/* 계정 추가 폼 */}
        {showForm && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-lg">새 계정 연결</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>시장</Label>
                  <Select value={formMarket} onValueChange={(v) => { if (v) { setFormMarket(v); setFormPlatform(""); } }}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="kr">🇰🇷 한국</SelectItem>
                      <SelectItem value="us">🇺🇸 북미</SelectItem>
                      <SelectItem value="jp">🇯🇵 일본</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>플랫폼</Label>
                  <Select value={formPlatform} onValueChange={(v) => { if (v) setFormPlatform(v); }}>
                    <SelectTrigger><SelectValue placeholder="선택" /></SelectTrigger>
                    <SelectContent>
                      {(PLATFORMS_BY_MARKET[formMarket] || []).map((p) => (
                        <SelectItem key={p} value={p}>
                          {PLATFORM_ICONS[p] || ""} {p}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label>계정명 (핸들)</Label>
                <Input
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="예: @allai0011"
                />
              </div>
              <Button onClick={handleConnect} disabled={saving || !formPlatform || !formName.trim()}>
                {saving ? "연결 중..." : "연결하기"}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* 계정 목록 */}
        {accounts.length === 0 && !showForm ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-muted-foreground mb-4">연결된 SNS 계정이 없습니다</p>
              <Button onClick={() => setShowForm(true)}>첫 계정 연결하기</Button>
            </CardContent>
          </Card>
        ) : (
          Object.entries(groupedByMarket).map(([market, marketAccounts]) => (
            <Card key={market} className="mb-4">
              <CardHeader>
                <CardTitle className="text-lg">
                  {MARKET_FLAGS[market]} {MARKET_NAMES[market] || market}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {marketAccounts.map((account) => (
                    <div
                      key={account.id}
                      className="flex items-center justify-between p-4 rounded-lg border"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xl">
                          {PLATFORM_ICONS[account.platform] || "🔗"}
                        </span>
                        <div>
                          <div className="font-medium text-sm">{account.platform}</div>
                          <div className="text-xs text-muted-foreground">{account.account_name}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={account.is_active ? "default" : "secondary"}>
                          {account.is_active ? "연결됨" : "비활성"}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs text-muted-foreground hover:text-destructive"
                          onClick={() => handleDisconnect(account.id, account.account_name)}
                        >
                          해제
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
