"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AutopilotCandidate,
  AutopilotStatus,
  autopilotEmergencyStop,
  autopilotResumeStop,
  autopilotScan,
  getAutopilotCandidates,
  getAutopilotStatus,
  getWhyThisTopic,
  rejectCandidate,
} from "@/lib/api";

const num = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : Math.round(v);

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-hairline bg-surface-1 p-5">
      <h2 className="mb-3 text-sm font-bold">{title}</h2>
      {children}
    </section>
  );
}

export default function AutopilotPage() {
  const [status, setStatus] = useState<AutopilotStatus | null>(null);
  const [cands, setCands] = useState<AutopilotCandidate[]>([]);
  const [why, setWhy] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([getAutopilotStatus(), getAutopilotCandidates()]);
      setStatus(s);
      setCands(c);
    } catch (e) {
      setErr(String(e));
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (err) return <p className="text-brand-secure">{err}</p>;
  if (!status) return <p className="text-subtle">불러오는 중…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">오토파일럿</h1>
        <button
          type="button"
          onClick={() => act(status.emergency_stop ? autopilotResumeStop : autopilotEmergencyStop)}
          className={`rounded-lg px-3 py-1.5 text-xs font-bold text-on-primary ${
            status.emergency_stop ? "bg-success" : "bg-brand-secure"
          }`}
        >
          {status.emergency_stop ? "긴급중지 해제" : "긴급 중지"}
        </button>
      </div>

      <Card title="상태">
        <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div className="rounded bg-surface-2 p-2">
            <p className="text-[11px] text-subtle">모드</p>
            <p className="font-semibold">{status.mode}</p>
          </div>
          <div className="rounded bg-surface-2 p-2">
            <p className="text-[11px] text-subtle">오늘 예산</p>
            <p className="font-semibold">
              ${status.today_budget.spent.toFixed(2)} / ${status.today_budget.daily}
            </p>
          </div>
          <div className="rounded bg-surface-2 p-2">
            <p className="text-[11px] text-subtle">트렌드 예비</p>
            <p className="font-semibold">${status.today_budget.trend_reserve.toFixed(2)}</p>
          </div>
          <div className="rounded bg-surface-2 p-2">
            <p className="text-[11px] text-subtle">후보</p>
            <p className="font-semibold">{status.candidates}</p>
          </div>
          <div className="rounded bg-surface-2 p-2">
            <p className="text-[11px] text-subtle">유망</p>
            <p className="font-semibold">{status.strong_opportunities}</p>
          </div>
          <div className="rounded bg-surface-2 p-2">
            <p className="text-[11px] text-subtle">선정</p>
            <p className="font-semibold">{status.selected}</p>
          </div>
          <div className="rounded bg-surface-2 p-2">
            <p className="text-[11px] text-subtle">제작 중</p>
            <p className="font-semibold">{status.producing}</p>
          </div>
          <div className="rounded bg-surface-2 p-2">
            <p className="text-[11px] text-subtle">예약</p>
            <p className="font-semibold">{status.scheduled}</p>
          </div>
        </div>
        {status.last_run && (
          <p className="mt-2 text-xs text-subtle">
            최근 실행: {status.last_run.status} · {status.last_run.stage}{" "}
            {status.last_run.pause_reason ? `· ${status.last_run.pause_reason}` : ""}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {["SHADOW", "SUGGEST_ONLY", "SEMI_AUTO", "FULL_AUTO"].map((m) => (
            <button
              key={m}
              type="button"
              disabled={busy}
              onClick={() => act(() => autopilotScan(m))}
              className="rounded border border-hairline px-3 py-1 text-xs disabled:opacity-40"
            >
              {( {SHADOW:"관찰",SUGGEST_ONLY:"추천만",SEMI_AUTO:"반자동",FULL_AUTO:"완전 자동"} as Record<string,string>)[m] ?? m} 검색
            </button>
          ))}
        </div>
      </Card>

      <Card title={`기회 후보 (${cands.length})`}>
        <div className="space-y-2">
          {cands.map((c) => (
            <div key={c.id} className="border-t border-hairline pt-2">
              <p className="text-sm">
                <b>{num(c.opportunity_score)}</b>{" "}
                <span className="text-xs text-subtle">
                  {c.status} · {c.portfolio_type ?? "-"} · {c.trend_type} · {c.dedup_status} · risk {c.risk_level}
                </span>
              </p>
              <p className="text-sm">
                {c.topic} <span className="text-subtle">— {c.angle}</span>
              </p>
              <p className="text-[11px] text-subtle">
                trend {num(c.trend_score)} · vel {num(c.velocity_score)} · hist {num(c.historical_score)} ·
                aud {num(c.audience_fit_score)} · rev {num(c.revenue_score)} · comp {num(c.competition_score)} ·
                orig {num(c.originality_score)} · fact {num(c.fact_availability_score)} ·
                natural {num(c.natural_content_score)} · est ${c.estimated_cost.toFixed(2)}
              </p>
              <p className="text-[11px] text-primary">
                {Object.entries(c.platform_scores || {})
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 5)
                  .map(([p, v]) => `${p} ${Math.round(v)}`)
                  .join(" · ")}
              </p>
              <div className="mt-1 flex gap-2">
                <button
                  type="button"
                  onClick={() => act(async () => setWhy(await getWhyThisTopic(c.id)))}
                  className="rounded border border-hairline px-2 py-0.5 text-xs"
                >
                  왜 추천?
                </button>
                <button
                  type="button"
                  onClick={() => act(() => rejectCandidate(c.id, "ONCE", "Not Interested"))}
                  className="rounded border border-hairline px-2 py-0.5 text-xs"
                >
                  Reject
                </button>
                <button
                  type="button"
                  onClick={() => act(() => rejectCandidate(c.id, "PERMANENT", "Brand Mismatch"))}
                  className="rounded border border-hairline px-2 py-0.5 text-xs"
                >
                  Block
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {why && (
        <Card title="왜 이 주제인가">
          <pre className="whitespace-pre-wrap rounded bg-surface-2 p-3 text-xs">
            {JSON.stringify(why, null, 2)}
          </pre>
        </Card>
      )}
    </div>
  );
}
