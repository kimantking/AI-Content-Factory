"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icon, type IconName } from "./Icon";
import { contentLibrary, type LibraryCard } from "@/lib/api";

type Item = { id: string; label: string; hint?: string; icon: IconName; run: () => void };

const NAV_TARGETS: { href: string; label: string; icon: IconName }[] = [
  { href: "/app", label: "홈", icon: "home" },
  { href: "/create", label: "만들기", icon: "plus" },
  { href: "/library", label: "콘텐츠 보관함", icon: "library" },
  { href: "/governance", label: "검수 센터", icon: "shield" },
  { href: "/learn-studio", label: "AI 학습실", icon: "sparkles" },
  { href: "/references", label: "자료실", icon: "book" },
  { href: "/calendar", label: "캘린더", icon: "calendar" },
  { href: "/portfolio", label: "채널", icon: "layers" },
  { href: "/publishing", label: "게시", icon: "send" },
  { href: "/analytics", label: "분석", icon: "chart" },
  { href: "/autopilot", label: "오토파일럿", icon: "rocket" },
  { href: "/support", label: "AI 지원 스냅샷", icon: "life-buoy" },
  { href: "/settings/local-ai", label: "설정", icon: "settings" },
  { href: "/admin", label: "시스템", icon: "server" },
  { href: "/system", label: "상태", icon: "activity" },
];

export function CommandPalette({
  open,
  onClose,
  onNavigate,
}: {
  open: boolean;
  onClose: () => void;
  onNavigate: (href: string) => void;
}) {
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const [results, setResults] = useState<LibraryCard[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQ("");
      setCursor(0);
      setResults([]);
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  // debounced content search
  useEffect(() => {
    if (!open || q.trim().length < 2) {
      setResults([]);
      return;
    }
    const h = setTimeout(() => {
      contentLibrary({ q: q.trim(), page: "1" })
        .then((r) => setResults(r.items.slice(0, 6)))
        .catch(() => setResults([]));
    }, 220);
    return () => clearTimeout(h);
  }, [q, open]);

  const go = useCallback(
    (href: string) => {
      onClose();
      onNavigate(href);
    },
    [onClose, onNavigate],
  );

  const quickActions: Item[] = useMemo(
    () => [
      { id: "qa-create", label: "새 콘텐츠 만들기", icon: "plus", run: () => go("/create") },
      { id: "qa-learn", label: "AI 학습 시작", icon: "sparkles", run: () => go("/learn-studio") },
      { id: "qa-review", label: "검수 열기", icon: "shield", run: () => go("/governance") },
      { id: "qa-support", label: "AI 지원 스냅샷", icon: "life-buoy", run: () => go("/support") },
      { id: "qa-autopilot", label: "오토파일럿 관리", icon: "rocket", run: () => go("/autopilot") },
    ],
    [go],
  );

  const navItems: Item[] = useMemo(() => {
    const t = q.trim().toLowerCase();
    return NAV_TARGETS.filter((n) => !t || n.label.toLowerCase().includes(t)).map((n) => ({
      id: `nav-${n.href}`,
      label: n.label,
      hint: n.href,
      icon: n.icon,
      run: () => go(n.href),
    }));
  }, [q, go]);

  const contentItems: Item[] = useMemo(
    () =>
      results.map((c) => ({
        id: `c-${c.campaign_id}`,
        label: c.topic || "(제목 없음)",
        hint: c.platforms.join(", ") || "플랫폼 미생성",
        icon: "film" as IconName,
        run: () => go(`/library/${c.campaign_id}`),
      })),
    [results, go],
  );

  const groups = useMemo(() => {
    const t = q.trim().toLowerCase();
    const qa = t ? quickActions.filter((a) => a.label.toLowerCase().includes(t)) : quickActions;
    return [
      { title: "빠른 실행", items: qa },
      { title: "이동", items: navItems },
      ...(contentItems.length ? [{ title: "콘텐츠", items: contentItems }] : []),
    ].filter((g) => g.items.length);
  }, [q, quickActions, navItems, contentItems]);

  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);

  useEffect(() => {
    if (cursor >= flat.length) setCursor(Math.max(0, flat.length - 1));
  }, [flat.length, cursor]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[10vh]"
      role="dialog"
      aria-modal="true"
      aria-label="검색 및 빠른 실행"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
        else if (e.key === "ArrowDown") {
          e.preventDefault();
          setCursor((c) => Math.min(c + 1, flat.length - 1));
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          setCursor((c) => Math.max(c - 1, 0));
        } else if (e.key === "Enter") {
          e.preventDefault();
          flat[cursor]?.run();
        }
      }}
    >
      <div className="absolute inset-0 bg-black/55" onClick={onClose} />
      <div className="relative w-full max-w-[560px] overflow-hidden rounded-xl border border-hairline-strong bg-surface-1 shadow-2xl" style={{ overscrollBehavior: "contain" }}>
        <div className="flex items-center gap-2.5 border-b border-hairline px-4">
          <Icon name="search" size={16} className="text-ink-tertiary" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setCursor(0);
            }}
            placeholder="콘텐츠, 채널, 명령 검색"
            aria-label="콘텐츠, 채널, 명령 검색"
            autoComplete="off"
            className="w-full rounded bg-transparent py-3.5 text-body-sm text-ink outline-none placeholder:text-ink-tertiary focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-focus/50"
          />
          <kbd className="rounded border border-hairline px-1.5 py-0.5 font-mono text-[11px] text-ink-tertiary">ESC</kbd>
        </div>

        <div className="max-h-[52vh] overflow-y-auto p-2" style={{ overscrollBehavior: "contain" }}>
          {flat.length === 0 ? (
            <p className="px-3 py-6 text-center text-body-sm text-ink-subtle">일치하는 결과가 없습니다.</p>
          ) : (
            groups.map((g) => (
              <div key={g.title} className="mb-1.5">
                <p className="px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.5px] text-ink-tertiary">
                  {g.title}
                </p>
                <ul>
                  {g.items.map((it) => {
                    const idx = flat.indexOf(it);
                    const on = idx === cursor;
                    return (
                      <li key={it.id}>
                        <button
                          onMouseEnter={() => setCursor(idx)}
                          onClick={() => it.run()}
                          className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-body-sm ${
                            on ? "bg-surface-2 text-ink" : "text-ink-muted"
                          }`}
                        >
                          <Icon name={it.icon} size={16} className={on ? "text-primary" : "text-ink-subtle"} />
                          <span className="truncate">{it.label}</span>
                          {it.hint && (
                            <span className="ml-auto truncate font-mono text-[11px] text-ink-tertiary">{it.hint}</span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
