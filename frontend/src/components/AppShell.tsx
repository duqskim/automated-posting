"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

interface User { id: number; email: string; name: string; }

const NAV = [
  { href: "/dashboard",  label: "대시보드",  icon: "▦" },
  { href: "/series",     label: "시리즈",    icon: "▶" },
  { href: "/characters", label: "캐릭터",    icon: "◉" },
  { href: "/accounts",   label: "SNS 계정",  icon: "⚙" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { router.replace("/login"); return; }
    api.auth.me()
      .then(setUser)
      .catch(() => { localStorage.removeItem("token"); router.replace("/login"); });
  }, [router]);

  const logout = () => {
    localStorage.removeItem("token");
    router.push("/login");
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* 모바일 오버레이 */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* 사이드바 */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-30 flex flex-col w-56 border-r bg-background
        transition-transform duration-200
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
      `}>
        {/* 브랜드 */}
        <div className="flex items-center gap-2 h-14 px-5 border-b">
          <span className="font-bold text-base tracking-tight">Automated Posting</span>
        </div>

        {/* 네비게이션 */}
        <nav className="flex-1 py-3 overflow-y-auto">
          {NAV.map(({ href, label, icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setSidebarOpen(false)}
                className={`
                  flex items-center gap-3 px-5 py-2.5 text-sm font-medium transition-colors
                  ${active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/30"}
                `}
              >
                <span className="text-base w-5 text-center leading-none">{icon}</span>
                {label}
              </Link>
            );
          })}
        </nav>

        {/* 유저 */}
        <div className="border-t p-4 space-y-1">
          {user && (
            <p className="text-xs text-muted-foreground truncate px-1">{user.email}</p>
          )}
          <button
            onClick={logout}
            className="w-full text-left text-xs text-muted-foreground hover:text-red-500 transition-colors px-1 py-1"
          >
            로그아웃
          </button>
        </div>
      </aside>

      {/* 메인 */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* 모바일 헤더 */}
        <div className="flex items-center h-14 px-4 border-b lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="mr-3 text-muted-foreground hover:text-foreground"
          >
            ☰
          </button>
          <span className="font-bold text-sm">Automated Posting</span>
        </div>

        {/* 콘텐츠 */}
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
