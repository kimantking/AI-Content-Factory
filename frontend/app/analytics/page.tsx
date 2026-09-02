"use client";

import { useEffect, useState } from "react";
import {
  getAnalyticsCapabilities,
  getAnalyticsOverview,
  getNaturalnessAnalytics,
  getRankings,
  getRevenueDashboard,
} from "@/lib/api";
import { platformKo } from "@/lib/status";

const METRIC_KO: Record<string, string> = {
  views: "조회수", impressions: "노출", reach: "도달", watch_time_seconds: "시청시간(초)",
  avg_view_percentage: "평균 시청률", likes: "좋아요", comments: "댓글", shares: "공유",
  saves: "저장", followers_gained: "팔로워 증가", subscribers_gained: "구독 증가",
  estimated_revenue: "예상 수익",
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-hairline bg-surface-1 p-5">
      <h2 className="mb-3 text-sm font-bold">{title}</h2>
      {children}
    </section>
  );
}

const fmt = (v: unknown) =>
  v === null || v === undefined ? <span className="text-ink-tertiary">—</span> : String(v);

export default function AnalyticsPage() {
  const [ov, setOv] = useState<Awaited<ReturnType<typeof getAnalyticsOverview>> | null>(null);
  const [caps, setCaps] = useState<Awaited<ReturnType<typeof getAnalyticsCapabilities>>>([]);
  const [ranks, setRanks] = useState<Record<string, unknown>[]>([]);
  const [nat, setNat] = useState<Record<string, unknown>[]>([]);
  const [rev, setRev] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      getAnalyticsOverview(),
      getAnalyticsCapabilities(),
      getRankings("score"),
      getNaturalnessAnalytics(),
      getRevenueDashboard(),
    ])
      .then(([o, c, r, n, rv]) => {
        setOv(o);
        setCaps(c);
        setRanks(r);
        setNat(n.rows);
        setRev(rv);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <p className="text-brand-secure">{err}</p>;
  if (!ov) return <p className="text-subtle">불러오는 중…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">분석</h1>
        <a href="/learning" className="text-sm text-primary underline">
          학습 · 메모리 →
        </a>
      </div>

      <Card title="개요  ( — 는 연결된 플랫폼에서 제공되지 않는 지표 )">
        <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          {Object.entries(ov.metrics).map(([k, v]) => (
            <div key={k} className="rounded-lg bg-surface-2 p-2">
              <p className="text-[11px] text-subtle">{METRIC_KO[k] ?? k}</p>
              <p className="font-semibold">{fmt(v)}</p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-subtle">
          수익 {fmt(ov.revenue.total)} · 비용 {fmt(ov.cost.total)} · 순이익{" "}
          {fmt(ov.net_profit)} · 마진 {fmt(ov.margin)}
        </p>
      </Card>

      <Card title="플랫폼별 지표 제공 여부">
        <table className="w-full text-left text-xs">
          <thead className="text-subtle">
            <tr>
              <th className="py-1">플랫폼</th>
              <th>수익 지표</th>
              <th>지연</th>
              <th>제공 지표</th>
            </tr>
          </thead>
          <tbody>
            {caps.map((c) => (
              <tr key={c.platform} className="border-t border-hairline align-top">
                <td className="py-1 font-medium">{platformKo(c.platform)}</td>
                <td>{c.revenue_support ? "제공" : "—"}</td>
                <td>{c.analytics_delay}</td>
                <td className="text-ink-subtle">
                  {Object.entries(c.metrics)
                    .filter(([, s]) => s === "AVAILABLE")
                    .map(([m]) => m)
                    .join(", ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="콘텐츠 성과 순위">
        <ol className="space-y-1 text-sm">
          {ranks.map((r, i) => (
            <li key={i}>
              <span className="text-subtle">#{i + 1}</span> {platformKo(String(r.platform))} ·{" "}
              점수 <b>{String(r.score)}</b> · 상대 {fmt(r.relative_score)}{" "}
              {r.is_outlier ? <span className="text-brand-secure">[이상치]</span> : null}
              {r.has_anomaly ? <span className="text-brand-secure">[변동 감지]</span> : null}
            </li>
          ))}
        </ol>
      </Card>

      <Card title="자연스러움 대비 성과 (상관관계 참고용)">
        <table className="w-full text-left text-xs">
          <thead className="text-subtle">
            <tr>
              <th className="py-1">플랫폼</th>
              <th>AI slop</th>
              <th>AI 영상 비율</th>
              <th>장면 변동</th>
              <th>성과</th>
            </tr>
          </thead>
          <tbody>
            {nat.slice(0, 30).map((r, i) => (
              <tr key={i} className="border-t border-hairline">
                <td className="py-1">{String(r.platform)}</td>
                <td>{fmt(r.ai_slop_score)}</td>
                <td>{fmt(r.ai_video_ratio)}</td>
                <td>{fmt(r.scene_duration_variance)}</td>
                <td>{fmt(r.performance_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {rev && (
        <Card title="수익 · 비용 · 순이익 상세">
          <pre className="whitespace-pre-wrap rounded bg-surface-2 p-3 text-xs">
            {JSON.stringify(rev, null, 2)}
          </pre>
        </Card>
      )}
    </div>
  );
}
