"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { statusMeta, TONE_DOT, TONE_TEXT } from "@/lib/status";
import { getOpsAlerts, supportSnapshot } from "@/lib/api";

type NavItem = { href: string; label: string; icon: IconName };
type NavGroup = { label?: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    items: [
      { href: "/app", label: "홈", icon: "home" },
      { href: "/create", label: "만들기", icon: "plus" },
      { href: "/library", label: "콘텐츠", icon: "library" },
      { href: "/governance", label: "검수", icon: "shield" },
    ],
  },
  {
    label: "운영",
    items: [
      { href: "/learn-studio", label: "AI 학습실", icon: "sparkles" },
      { href: "/references", label: "자료실", icon: "book" },
      { href: "/calendar", label: "캘린더", icon: "calendar" },
      { href: "/portfolio", label: "채널", icon: "layers" },
      { href: "/publishing", label: "게시", icon: "send" },
      { href: "/analytics", label: "분석", icon: "chart" },
      { href: "/autopilot", label: "오토파일럿", icon: "rocket" },
    ],
  },
  {
    label: "시스템",
    items: [
      { href: "/support", label: "AI 지원", icon: "life-buoy" },
      { href: "/settings/ai", label: "AI 연결", icon: "zap" },
      { href: "/settings/local-ai", label: "설정", icon: "settings" },
      { href: "/admin", label: "시스템", icon: "server" },
      { href: "/system", label: "상태", icon: "activity" },
    ],
  },
];

const MOBILE_PRIMARY: (NavItem & { cta?: boolean })[] = [
  { href: "/app", label: "홈", icon: "home" },
  { href: "/library", label: "콘텐츠", icon: "library" },
  { href: "/create", label: "만들기", icon: "plus", cta: true },
  { href: "/governance", label: "검수", icon: "shield" },
];
const MOBILE_MORE = NAV.flatMap((g) => g.items).filter(
  (i) => !["/app", "/library", "/create", "/governance"].includes(i.href),
);

function isActive(path: string, href: string) {
  return href === "/app" ? path === "/app" : path === href || path.startsWith(href + "/");
}

export default function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname() || "/";
  const router = useRouter();
  const isLanding = path === "/";
  const [collapsed, setCollapsed] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [health, setHealth] = useState<string>("UNKNOWN");
  const [alertCount, setAlertCount] = useState(0);

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem("acf-sidebar") === "collapsed");
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    setMoreOpen(false);
  }, [path]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    let alive = true;
    const withTimeout = <T,>(p: Promise<T>, ms = 7000) =>
      Promise.race([p, new Promise<T>((_, r) => setTimeout(() => r(new Error("timeout")), ms))]);
    const tick = () => {
      if (document.visibilityState === "hidden" || window.location.pathname === "/") return;
      withTimeout(supportSnapshot())
        .then((s) => alive && setHealth(s.overall_health))
        .catch(() => undefined);
      withTimeout(getOpsAlerts())
        .then((a) => alive && setAlertCount(Array.isArray(a) ? a.length : 0))
        .catch(() => undefined);
    };
    tick();
    const t = setInterval(tick, 120000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const toggleCollapse = useCallback(() => {
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem("acf-sidebar", next ? "collapsed" : "expanded");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const hm = statusMeta(health);

  // marketing landing renders bare (its own light layout, no dashboard chrome)
  if (isLanding) return <>{children}</>;

  return (
    <div className="flex min-h-screen bg-canvas">
      <a
        href="#workspace"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-caption focus:text-on-primary"
      >
        본문으로 건너뛰기
      </a>

      {/* ---------------------------------------------------- desktop sidebar */}
      <aside
        data-chrome
        className={`sticky top-0 hidden h-screen flex-col border-r border-hairline/70 bg-canvas/55 backdrop-blur-2xl md:flex ${
          collapsed ? "w-[60px]" : "w-[236px]"
        } transition-[width] duration-150`}
      >
        <div className={`flex h-14 items-center border-b border-hairline ${collapsed ? "justify-center px-0" : "px-4"}`}>
          {collapsed ? (
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-on-primary">
              <Icon name="zap" size={16} />
            </span>
          ) : (
            <Link href="/app" className="flex items-center gap-2 font-display text-body-sm font-semibold tracking-[-0.3px]">
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-on-primary">
                <Icon name="zap" size={16} />
              </span>
              <span className="tracking-[-0.04em]">CONTENT® STUDIO</span>
            </Link>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="주요 메뉴">
          {NAV.map((group, gi) => (
            <div key={gi} className={gi > 0 ? "mt-4" : ""}>
              {group.label && !collapsed && (
                <p className="px-2.5 pb-1.5 text-[11px] font-medium uppercase tracking-[0.5px] text-ink-tertiary">
                  {group.label}
                </p>
              )}
              {group.label && !collapsed ? null : gi > 0 && collapsed ? (
                <div className="mx-2 mb-2 border-t border-hairline" />
              ) : null}
              <ul className="space-y-0.5">
                {group.items.map((it) => {
                  const active = isActive(path, it.href);
                  return (
                    <li key={it.href}>
                      <Link
                        href={it.href}
                        title={collapsed ? it.label : undefined}
                        aria-current={active ? "page" : undefined}
                        className={`group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-body-sm transition-colors ${
                          collapsed ? "justify-center" : ""
                        } ${
                          active
                            ? "bg-surface-2 font-medium text-ink"
                            : "text-ink-subtle hover:bg-surface-1 hover:text-ink-muted"
                        }`}
                      >
                        <Icon name={it.icon} size={17} className={active ? "text-primary" : ""} />
                        {!collapsed && <span className="truncate">{it.label}</span>}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className={`border-t border-hairline p-2 ${collapsed ? "flex flex-col items-center gap-1" : ""}`}>
          <ThemeToggle compact={collapsed} />
          <button
            onClick={toggleCollapse}
            className="btn btn-ghost !px-2"
            aria-label={collapsed ? "사이드바 펼치기" : "사이드바 접기"}
            title={collapsed ? "사이드바 펼치기" : "사이드바 접기"}
          >
            <Icon name="panel-left" size={16} />
            {!collapsed && <span className="text-caption">접기</span>}
          </button>
        </div>
      </aside>

      {/* ------------------------------------------------------ main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header
          data-chrome
          className="sticky top-0 z-30 flex h-14 items-center gap-2 bg-gradient-to-b from-canvas/90 to-canvas/0 px-3 backdrop-blur-sm sm:px-4"
        >
          <span className="font-display text-body-sm font-semibold tracking-[-0.3px] md:hidden">
            CONTENT® STUDIO
          </span>

          <button
            onClick={() => setPaletteOpen(true)}
            className="hidden min-w-[220px] items-center gap-2 rounded-md border border-hairline bg-surface-1 px-2.5 py-1.5 text-body-sm text-ink-tertiary hover:border-hairline-strong sm:flex md:w-[320px]"
            aria-label="검색 및 빠른 실행 열기"
          >
            <Icon name="search" size={15} />
            <span>콘텐츠, 채널, 명령 검색</span>
            <kbd className="ml-auto rounded border border-hairline px-1.5 py-0.5 font-mono text-[11px] text-ink-tertiary">
              ⌘K
            </kbd>
          </button>

          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={() => setPaletteOpen(true)}
              className="btn btn-ghost !px-2 sm:hidden"
              aria-label="검색"
            >
              <Icon name="search" size={17} />
            </button>

            <Link href="/create" className="btn btn-primary hidden sm:inline-flex">
              <Icon name="plus" size={15} />
              빠른 만들기
            </Link>

            <Link
              href="/support"
              className="btn btn-ghost !px-2"
              title={`시스템 상태: ${hm.ko}`}
              aria-label={`시스템 상태 ${hm.ko}, AI 지원 열기`}
            >
              <span className={`h-2 w-2 rounded-full ${TONE_DOT[hm.tone]}`} />
              <span className={`hidden text-caption lg:inline ${TONE_TEXT[hm.tone]}`}>{hm.ko}</span>
            </Link>

            <Link href="/system" className="btn btn-ghost relative !px-2" aria-label={`알림 ${alertCount}건`}>
              <Icon name="bell" size={17} />
              {alertCount > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 font-mono text-[10px] text-on-primary">
                  {alertCount > 9 ? "9+" : alertCount}
                </span>
              )}
            </Link>

            <span
              className="ml-1 hidden h-7 w-7 items-center justify-center rounded-full bg-surface-2 font-mono text-[11px] text-ink-muted sm:flex"
              title="관리자"
            >
              관
            </span>
          </div>
        </header>

        <main id="workspace" className="mx-auto w-full max-w-workspace flex-1 px-4 pb-24 pt-6 sm:px-6 md:pb-10">
          {children}
        </main>
      </div>

      {/* ---------------------------------------------------- mobile bottom nav */}
      <nav
        data-chrome
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-hairline bg-canvas md:hidden"
        aria-label="하단 메뉴"
      >
        {MOBILE_PRIMARY.map((it) => {
          const active = isActive(path, it.href);
          return (
            <Link
              key={it.href}
              href={it.href}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-[54px] flex-col items-center justify-center gap-1 text-[10px] ${
                active ? "text-ink" : "text-ink-subtle"
              }`}
            >
              {it.cta ? (
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-on-primary">
                  <Icon name={it.icon} size={18} />
                </span>
              ) : (
                <Icon name={it.icon} size={20} className={active ? "text-primary" : ""} />
              )}
              {it.label}
            </Link>
          );
        })}
        <button
          onClick={() => setMoreOpen(true)}
          className="flex min-h-[54px] flex-col items-center justify-center gap-1 text-[10px] text-ink-subtle"
        >
          <Icon name="more" size={20} />
          더보기
        </button>
      </nav>

      {moreOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="전체 메뉴">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMoreOpen(false)} />
          <div
            className="absolute inset-x-0 bottom-0 rounded-t-xl border-t border-hairline bg-canvas p-4 pb-8"
            style={{ overscrollBehavior: "contain" }}
          >
            <div className="mx-auto mb-4 h-1 w-9 rounded-full bg-hairline-strong" />
            <div className="grid grid-cols-2 gap-2">
              {MOBILE_MORE.map((it) => (
                <Link
                  key={it.href}
                  href={it.href}
                  className="flex items-center gap-2.5 rounded-md border border-hairline px-3 py-3 text-body-sm text-ink-muted"
                >
                  <Icon name={it.icon} size={17} className="text-ink-subtle" />
                  {it.label}
                </Link>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-hairline pt-3">
              <ThemeToggle />
              <Link href="/create" className="btn btn-primary" onClick={() => setMoreOpen(false)}>
                <Icon name="plus" size={15} />
                콘텐츠 만들기
              </Link>
            </div>
          </div>
        </div>
      )}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onNavigate={(href) => router.push(href)} />
    </div>
  );
}
