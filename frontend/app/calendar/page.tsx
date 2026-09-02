"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CalendarJob, publishCalendar } from "@/lib/api";

const STATUS: Record<string, string> = {
  PUBLISHED: "bg-success", SCHEDULED: "bg-primary", QUEUED: "bg-surface-2",
  READY: "bg-surface-3", BLOCKED: "bg-brand-secure", WAITING_APPROVAL: "bg-brand-secure",
};

export default function CalendarPage() {
  const [jobs, setJobs] = useState<CalendarJob[]>([]);
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    publishCalendar(90).then(setJobs).catch((e) => setErr(String(e)));
  }, []);

  const byDay = useMemo(() => {
    const m: Record<string, CalendarJob[]> = {};
    for (const j of jobs) {
      if (!j.scheduled_at) continue;
      const k = j.scheduled_at.slice(0, 10);
      (m[k] ??= []).push(j);
    }
    return m;
  }, [jobs]);

  const first = new Date(month);
  const startDow = first.getDay();
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells: (Date | null)[] = [
    ...Array(startDow).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1)),
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">캘린더</h1>
        <button className="rounded border px-2 py-1 text-sm"
          onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>◀</button>
        <span className="text-sm font-medium">{month.getFullYear()}년 {month.getMonth() + 1}월</span>
        <button className="rounded border px-2 py-1 text-sm"
          onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>▶</button>
        <span className="ml-auto text-xs text-ink-subtle">예약된 게시 {jobs.length}건</span>
      </div>
      {err && <p className="text-sm text-brand-secure">{err}</p>}

      <div className="grid grid-cols-7 gap-px rounded-lg border border-hairline bg-surface-3 text-xs">
        {["일", "월", "화", "수", "목", "금", "토"].map((d) => (
          <div key={d} className="bg-surface-2 p-2 text-center font-bold text-ink-subtle">{d}</div>
        ))}
        {cells.map((date, i) => {
          const key = date ? date.toISOString().slice(0, 10) : `e${i}`;
          const items = date ? byDay[key] ?? [] : [];
          return (
            <div key={key} className="min-h-24 bg-surface-1 p-1">
              {date && <div className="text-right text-[10px] text-ink-tertiary">{date.getDate()}</div>}
              <div className="space-y-0.5">
                {items.slice(0, 4).map((j) => (
                  <Link key={j.job_id} href={`/library/${j.campaign_id}`}
                    className="flex items-center gap-1 truncate rounded bg-surface-2 px-1 py-0.5 hover:bg-surface-2">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS[j.status] ?? "bg-surface-3"}`} />
                    <span className="truncate">{j.platform} · {j.title || j.campaign_id.slice(0, 6)}</span>
                  </Link>
                ))}
                {items.length > 4 && <div className="text-[10px] text-ink-tertiary">+{items.length - 4}</div>}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-ink-tertiary">
        상태 색: <span className="text-success">게시됨</span> ·
        <span className="text-primary"> 예약</span> · <span className="text-brand-secure">승인 대기</span> ·
        <span className="text-brand-secure"> 차단</span> (색과 함께 텍스트로도 표시)
      </p>
    </div>
  );
}
