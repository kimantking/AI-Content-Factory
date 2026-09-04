"use client";

import { use, useCallback, useEffect, useState } from "react";
import { CreativePlan, MediaStatus, VideoQA, getMedia } from "@/lib/api";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-hairline bg-surface-1 p-5">
      <h2 className="mb-3 text-sm font-bold">{title}</h2>
      {children}
    </section>
  );
}

const RISK: Record<string, string> = {
  LOW: "text-success",
  MEDIUM: "text-brand-secure",
  HIGH: "text-brand-secure",
};
const CHECK: Record<string, string> = {
  OK: "text-success",
  WARN: "text-brand-secure",
  FAIL: "text-brand-secure",
  UNKNOWN: "text-ink-tertiary",
  SKIPPED: "text-ink-tertiary",
  OFF_TARGET: "text-brand-secure",
  TRUE_PEAK_OVER: "text-brand-secure",
};

function Bar({ v }: { v: number }) {
  const pct = Math.round(v * 100);
  const col = pct >= 62 ? "bg-success" : pct >= 45 ? "bg-brand-secure" : "bg-brand-secure";
  return (
    <div className="h-2 w-full rounded bg-surface-2">
      <div className={`h-2 rounded ${col}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function StudioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [m, setM] = useState<MediaStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setM(await getMedia(id));
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, [id]);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  const cp: CreativePlan | null = m?.creative_plan ?? null;
  const vqa: VideoQA | null = m?.video_qa ?? null;
  const totalDur = (m?.scene_monitor ?? []).reduce((a, s) => a + (s.duration || 0), 0) || 1;

  return (
    <main className="space-y-6">
      <div className="flex items-baseline gap-3">
        <h1 className="text-lg font-bold">영상 스튜디오</h1>
        <a href={`/campaigns/${id}/media`} className="text-xs text-primary underline">
          ← 영상 제작 과정
        </a>
        <button className="ml-auto rounded-lg border px-3 py-1 text-xs" onClick={load}>
          새로고침
        </button>
      </div>
      {err && <p className="rounded-lg bg-surface-2 p-3 text-xs text-brand-secure">{err}</p>}
      {!cp && !err && (
        <p className="text-xs text-subtle">
          아직 영상 제작 계획이 없습니다. 먼저 영상 제작 과정을 실행해 주세요.
        </p>
      )}

      {cp && (
        <>
          <Card title={`Creative Plan · ${cp.platform} · profile ${cp.profile} · pace ${cp.pace_profile}`}>
            <div className="mb-3 flex flex-wrap gap-1 text-xs">
              {cp.story_arc.map((b, i) => (
                <span key={i} className="rounded bg-surface-2 px-2 py-0.5 font-mono">
                  {b.beat}
                  <span className="text-ink-tertiary"> [{b.scene_orders.join(",")}]</span>
                </span>
              ))}
            </div>
            <div className="text-xs text-ink-subtle">
              emotional arc: {cp.emotional_arc.join(" → ")}
            </div>
            {cp.warnings?.length > 0 && (
              <ul className="mt-3 list-disc pl-5 text-xs text-brand-secure">
                {cp.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="유지율 맵 (설계 신호 · 예측 곡선 아님)">
            <div className="relative h-10 w-full rounded bg-surface-2">
              {cp.retention_strategy.checkpoints.map((c, i) => (
                <div
                  key={i}
                  title={`${c.label}: ${c.reason_to_stay} (${c.risk})`}
                  className="absolute top-0 flex h-10 -translate-x-1/2 flex-col items-center justify-center"
                  style={{ left: `${Math.min(98, (c.t / totalDur) * 100)}%` }}
                >
                  <span className={`text-[10px] font-bold ${RISK[c.risk] ?? ""}`}>●</span>
                  <span className="text-[9px] text-ink-subtle">{c.label}</span>
                </div>
              ))}
              {cp.high_impact_scenes.map((so, i) => {
                const before = (m?.scene_monitor ?? [])
                  .filter((s) => s.order < so)
                  .reduce((a, s) => a + s.duration, 0);
                return (
                  <div
                    key={`hi${i}`}
                    className="absolute bottom-0 h-1 bg-primary"
                    style={{ left: `${(before / totalDur) * 100}%`, width: "3%" }}
                    title={`high-impact scene ${so}`}
                  />
                );
              })}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-subtle">
              <span>first-second: {cp.retention_strategy.first_second_strength.toFixed(2)}</span>
              <span>early payoff: {cp.retention_strategy.early_payoff ? "yes" : "no"}</span>
              <span>open loops: {cp.retention_strategy.open_loops}</span>
              <span>boredom risk: {(cp.boredom_risk * 100).toFixed(0)}%</span>
              <span>pattern interrupts: {cp.retention_strategy.pattern_interrupts.join(", ") || "—"}</span>
            </div>
          </Card>

          <Card title="장면 연출">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-ink-tertiary">
                    <th className="py-1 pr-2">#</th>
                    <th className="py-1 pr-2">beat</th>
                    <th className="py-1 pr-2">emotion</th>
                    <th className="py-1 pr-2">shot</th>
                    <th className="py-1 pr-2">motion</th>
                    <th className="py-1 pr-2">focus</th>
                    <th className="py-1 pr-2">kinetic</th>
                    <th className="py-1 pr-2">load</th>
                    <th className="py-1">evidence?</th>
                  </tr>
                </thead>
                <tbody>
                  {cp.scene_directions.map((d) => (
                    <tr key={d.scene_order} className="border-b border-hairline last:border-0">
                      <td className="py-1 pr-2">{d.scene_order}</td>
                      <td className="py-1 pr-2 font-mono">{d.story_beat}</td>
                      <td className="py-1 pr-2">{d.emotion_intent}</td>
                      <td className="py-1 pr-2">{d.shot_size}/{d.shot_purpose}</td>
                      <td className="py-1 pr-2">{d.cinematic_motion} ({d.motion_energy})</td>
                      <td className="py-1 pr-2">{d.primary_focus}</td>
                      <td className="py-1 pr-2">{d.kinetic_caption === "NONE" ? "—" : d.kinetic_caption}</td>
                      <td className="py-1 pr-2">{d.cognitive_load.toFixed(2)}</td>
                      <td className="py-1">{d.visual_evidence ? "✓" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="적용된 스킬">
            <div className="flex flex-wrap gap-1 text-xs">
              {Object.entries(cp.skills).map(([sid, v]) => (
                <span
                  key={sid}
                  className={`rounded px-2 py-0.5 font-mono ${
                    v === "required"
                      ? "bg-surface-2 text-success"
                      : v === "optional"
                        ? "bg-surface-2 text-brand-secure"
                        : "bg-surface-2 text-ink-subtle"
                  }`}
                >
                  {sid}
                </span>
              ))}
            </div>
          </Card>
        </>
      )}

      {vqa && !vqa.error && (
        <Card title={`Video Quality Score V2 — ${(vqa.overall_100 ?? vqa.overall * 100).toFixed(0)}/100 ${vqa.passed ? "· PASS" : "· REVIEW"}`}>
          <div className="grid gap-x-6 gap-y-1 md:grid-cols-2">
            {Object.entries(vqa.dimensions).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 text-xs">
                <span className="w-36 text-ink-subtle">{k}</span>
                <Bar v={v} />
                <span className="w-8 text-right tabular-nums">{Math.round(v * 100)}</span>
              </div>
            ))}
          </div>
          {vqa.creative_qa && (
            <div className="mt-4 text-xs">
              <div className="mb-1 font-semibold">
                Creative QA {vqa.creative_qa.passed ? "PASS" : "REVIEW"} ({vqa.creative_qa.score.toFixed(2)})
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                {Object.entries(vqa.creative_qa.checks).map(([k, s]) => (
                  <span key={k} className={CHECK[s] ?? ""}>
                    {k}:{s}
                  </span>
                ))}
              </div>
            </div>
          )}
          {vqa.technical_qa && (
            <div className="mt-4 text-xs">
              <div className="mb-1 font-semibold">Technical QA — {vqa.technical_qa.verdict}</div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                {Object.entries(vqa.technical_qa.passes).map(([k, p]) => (
                  <span key={k} className={CHECK[p.status] ?? ""}>
                    {k}:{p.status}
                  </span>
                ))}
              </div>
            </div>
          )}
          {vqa.repair_plan && vqa.repair_plan.length > 0 && (
            <div className="mt-4 text-xs">
              <div className="mb-1 font-semibold text-brand-secure">복구 계획</div>
              <ul className="list-disc pl-5">
                {vqa.repair_plan.map((r, i) => (
                  <li key={i}>
                    scene {r.scene_order}: {r.flag} → {r.strategy}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}
    </main>
  );
}
