"use client";

import { useCallback, useEffect, useState } from "react";
import {
  LocalAIStatus,
  ModelEntry,
  benchmarkModel,
  listAIModels,
  localAIPing,
  localAIStatus,
  modelPerformance,
} from "@/lib/api";

const BADGE: Record<string, string> = {
  CONNECTED: "bg-surface-2 text-success", DEGRADED: "bg-surface-2 text-brand-secure",
  NOT_RUNNING: "bg-surface-2 text-brand-secure", NO_MODEL: "bg-surface-2 text-brand-secure",
  DISABLED: "bg-surface-2 text-ink-subtle",
};

export default function LocalAISettings() {
  const [st, setSt] = useState<LocalAIStatus | null>(null);
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [perf, setPerf] = useState<Record<string, unknown>[]>([]);
  const [ping, setPing] = useState<Record<string, unknown> | null>(null);
  const [bench, setBench] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    localAIStatus().then(setSt).catch(() => undefined);
    listAIModels().then(setModels).catch(() => undefined);
    modelPerformance().then((r) => setPerf(r as Record<string, unknown>[])).catch(() => undefined);
  }, []);
  useEffect(load, [load]);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">로컬 AI</h1>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-bold">Ollama</h2>
          {st && <span className={`rounded px-2 py-0.5 text-xs ${BADGE[st.status] ?? ""}`}>{st.status}</span>}
          {st?.local_only && <span className="rounded bg-primary px-2 py-0.5 text-xs text-on-primary">LOCAL_ONLY</span>}
        </div>
        {st && (
          <div className="mt-2 text-xs text-ink-subtle">
            <div>endpoint: {st.base_url} · 기본 모델: {st.default_model} · 버전: {st.version ?? "—"}</div>
            <div>설치 모델: {st.models.join(", ") || "없음"}</div>
            <div>클라우드 폴백: {st.allow_cloud_fallback ? "허용" : "차단(LOCAL_ONLY)"}</div>
            {st.reason && <div className="text-brand-secure">{st.reason}</div>}
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <button className="input !w-auto !py-1" onClick={load}>연결 확인</button>
          <button className="input !w-auto !py-1"
            onClick={async () => { setBusy("ping"); setPing(await localAIPing().catch((e) => ({ ok: false, error: String(e) }))); setBusy(""); }}>
            {busy === "ping" ? "…" : "간단 추론 테스트"}
          </button>
          <button className="input !w-auto !py-1"
            onClick={async () => { setBusy("bench"); setBench(await benchmarkModel().catch((e) => ({ ok: false, error: String(e) }))); setBusy(""); load(); }}>
            {busy === "bench" ? "실행 중…" : "벤치마크"}
          </button>
        </div>
        {ping ? <p className="mt-2 text-xs">{ping.ok ? `OK: ${String(ping.sample)}` : `실패: ${String(ping.error)}`}</p> : null}
        {bench && Boolean(bench.ok) ? (
          <p className="mt-2 text-xs text-success">
            벤치마크 {String(bench.verified)} · schema {String(bench.schema_valid_rate)} · 정확도 {String(bench.accuracy)} · 평균 {String(bench.avg_latency_ms)}ms
          </p>
        ) : null}
        <p className="mt-2 text-[11px] text-ink-tertiary">모델(수 GB)은 승인 없이 자동 다운로드하지 않습니다.</p>
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <h2 className="mb-2 text-sm font-bold">모델 레지스트리</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-ink-subtle">
              <tr><th className="p-1">model</th><th className="p-1">종류</th><th className="p-1">상태</th>
                <th className="p-1">품질</th><th className="p-1">지연</th><th className="p-1">가격</th>
                <th className="p-1">$/1k in·out</th></tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.model_id} className="border-t border-hairline">
                  <td className="p-1 font-medium">{m.model_id}</td>
                  <td className="p-1">{m.kind}</td>
                  <td className="p-1">{m.enabled ? m.health : "DISABLED"}</td>
                  <td className="p-1">{m.quality_class}</td>
                  <td className="p-1">{m.latency_class}</td>
                  <td className="p-1">{m.pricing_state}</td>
                  <td className="p-1">{m.input_usd_per_1k} · {m.output_usd_per_1k}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {perf.length > 0 && (
        <section className="rounded-lg border border-hairline bg-surface-1 p-5">
          <h2 className="mb-2 text-sm font-bold">작업별 모델 성능 (실측)</h2>
          <table className="w-full text-xs">
            <thead className="text-left text-ink-subtle">
              <tr><th className="p-1">model</th><th className="p-1">task</th><th className="p-1">n</th>
                <th className="p-1">schema</th><th className="p-1">success</th><th className="p-1">강도</th></tr>
            </thead>
            <tbody>
              {perf.map((p, i) => (
                <tr key={i} className="border-t border-hairline">
                  <td className="p-1">{String(p.model_id)}</td>
                  <td className="p-1">{String(p.task_type)}</td>
                  <td className="p-1">{String(p.sample_size)}</td>
                  <td className="p-1">{String(p.schema_valid_rate)}</td>
                  <td className="p-1">{String(p.success_rate)}</td>
                  <td className="p-1">{String(p.strength)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
