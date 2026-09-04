"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CostEstimate,
  LocalAIStatus,
  PlatformSelection,
  composeCampaign,
  estimateCost,
  localAIStatus,
  platformContentTypes,
} from "@/lib/api";

const MODES = [
  ["CREATE_AND_LEARN", "학습 + 만들기"], ["CREATE_ONLY", "콘텐츠 만들기"],
  ["LEARN_ONLY", "학습만 하기"], ["REFERENCE_ONLY", "자료만 저장"],
] as const;
const QUALITY = [["fast", "빠르게"], ["balanced", "균형"], ["high", "고품질"], ["max", "최고품질"]] as const;
const CYCLE = ["DISABLED", "GENERATE_AND_PUBLISH", "GENERATE_ONLY"] as const;
const CYCLE_KO: Record<string, string> = {
  DISABLED: "사용 안 함", GENERATE_AND_PUBLISH: "제작 + 게시", GENERATE_ONLY: "제작만",
};

export default function QuickCreate() {
  const [wsId, setWsId] = useState("");
  const [topic, setTopic] = useState("");
  const [urls, setUrls] = useState<string[]>([""]);
  const [mode, setMode] = useState("CREATE_AND_LEARN");
  const [quality, setQuality] = useState("balanced");
  const [cts, setCts] = useState<Record<string, string[]>>({});
  const [sel, setSel] = useState<PlatformSelection>({
    youtube_shorts: { SHORT_VIDEO: "GENERATE_AND_PUBLISH" },
    tiktok: { VIDEO: "GENERATE_AND_PUBLISH" },
    naver_blog: { ARTICLE: "GENERATE_ONLY" },
  });
  const [cost, setCost] = useState<CostEstimate | null>(null);
  const [local, setLocal] = useState<LocalAIStatus | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setWsId(window.localStorage?.getItem("acf_workspace_id") ?? "");
    platformContentTypes().then((r) => setCts(r.content_types)).catch(() => undefined);
    localAIStatus().then(setLocal).catch(() => undefined);
  }, []);

  const learnOnly = mode === "LEARN_ONLY" || mode === "REFERENCE_ONLY";
  const refCount = useMemo(() => urls.map((u) => u.trim()).filter(Boolean).length, [urls]);

  const recost = useCallback(() => {
    estimateCost({
      selection: sel, quality_preset: quality, execution_mode: mode, reference_count: refCount,
    }).then(setCost).catch(() => setCost(null));
  }, [sel, quality, mode, refCount]);
  useEffect(recost, [recost]);

  const cyc = (p: string, ct: string) => {
    const cur = sel[p]?.[ct] ?? "DISABLED";
    const nx = CYCLE[(CYCLE.indexOf(cur as typeof CYCLE[number]) + 1) % CYCLE.length];
    setSel((x) => ({ ...x, [p]: { ...(x[p] ?? {}), [ct]: nx } }));
  };

  const submit = async () => {
    const cleanTopic = topic.trim();
    const enabledPlatforms = Object.values(sel).some((types) =>
      Object.values(types).some((value) => value !== "DISABLED"),
    );
    if (!learnOnly && cleanTopic.length < 2) {
      setErr("콘텐츠 주제를 두 글자 이상 입력해 주세요.");
      return;
    }
    if (learnOnly && refCount === 0) {
      setErr("학습할 참고자료 URL을 하나 이상 입력해 주세요.");
      return;
    }
    if (!learnOnly && !enabledPlatforms) {
      setErr("콘텐츠를 만들 SNS를 하나 이상 선택해 주세요.");
      return;
    }
    setBusy(true); setErr(null); setResult(null);
    try {
      const r = await composeCampaign({
        topic: cleanTopic || undefined, execution_mode: mode,
        reference_urls: urls.map((u) => u.trim()).filter(Boolean),
        platform_selection: sel, workspace_id: wsId || undefined,
      });
      setResult(r as unknown as Record<string, unknown>);
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };

  const fmt = (v: number | null | string) =>
    v === "PRICING_UNKNOWN" || v == null ? "확인 불가(UNKNOWN)" : typeof v === "number" ? `$${v.toFixed(4)}` : String(v);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">오늘 무엇을 만들까요?</h1>

      <input className="w-full rounded-md border border-hairline px-4 py-3"
        placeholder="주제: AI 때문에 바뀌는 직업 5가지" value={topic} onChange={(e) => setTopic(e.target.value)} />

      <section className="rounded-lg border border-hairline bg-surface-1 p-4">
        <div className="mb-2 text-sm font-bold">참고자료</div>
        {urls.map((u, i) => (
          <input key={i} className="mb-1.5 w-full rounded border border-hairline px-3 py-1.5 text-sm"
            placeholder="https://…" value={u}
            onChange={(e) => setUrls((a) => a.map((x, j) => (j === i ? e.target.value : x)))} />
        ))}
        <button className="text-sm text-primary underline" onClick={() => setUrls((a) => [...a, ""])}>+ URL 추가</button>
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-4">
        <div className="mb-1 text-sm font-bold">작업</div>
        {MODES.map(([v, k]) => (
          <label key={v} className="mr-4 inline-flex items-center gap-1 text-sm">
            <input type="radio" name="m" checked={mode === v} onChange={() => setMode(v)} />{k}
          </label>
        ))}
      </section>

      {!learnOnly && (
        <section className="rounded-lg border border-hairline bg-surface-1 p-4">
          <div className="mb-2 text-sm font-bold">SNS (클릭하여 상태 변경)</div>
          <div className="space-y-1">
            {Object.entries(cts).map(([p, list]) => (
              <div key={p} className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="w-32 font-medium">{p}</span>
                {list.map((ct) => {
                  const m = sel[p]?.[ct] ?? "DISABLED";
                  return (
                    <button key={ct} onClick={() => cyc(p, ct)}
                      className={`rounded border px-1.5 py-0.5 ${m === "GENERATE_AND_PUBLISH"
                        ? "border-hairline-strong bg-surface-2 text-success"
                        : m === "GENERATE_ONLY" ? "border-hairline-strong bg-surface-2 text-brand-secure"
                          : "border-hairline text-ink-tertiary"}`}>
                      {ct} · {CYCLE_KO[m]}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-lg border border-hairline bg-surface-1 p-4">
        <div className="mb-1 text-sm font-bold">품질</div>
        {QUALITY.map(([v, k]) => (
          <label key={v} className="mr-4 inline-flex items-center gap-1 text-sm">
            <input type="radio" name="q" checked={quality === v} onChange={() => setQuality(v)} />{k}
          </label>
        ))}
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-4 text-sm">
        <div className="font-bold">예상 비용</div>
        {local && (
          <div className="mt-1 text-xs text-ink-subtle">
            로컬 AI: {local.status}{local.local_only ? " · LOCAL_ONLY" : ""} — 로컬 작업은 API 비용 ₩0 (컴퓨터 자원 사용)
          </div>
        )}
        {cost ? (
          <div className="mt-2 space-y-0.5 text-xs">
            {Object.entries(cost.categories).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span>{k}{v.local_processing ? " · LOCAL PROCESSING" : ""}</span>
                <span>{v.state === "UNKNOWN" ? "확인 불가(UNKNOWN)" : fmt(v.usd)}</span>
              </div>
            ))}
            <div className="mt-1 flex justify-between border-t border-hairline pt-1 font-bold">
              <span>확인된 합계</span>
              <span>${cost.total_known_usd.toFixed(4)} (~{cost.total_known_krw.toLocaleString()}원)
                {cost.has_unknown ? " + UNKNOWN 항목" : ""}</span>
            </div>
            <p className="mt-1 text-ink-tertiary">{cost.note}</p>
          </div>
        ) : <p className="mt-1 text-xs text-ink-tertiary">계산 중…</p>}
      </section>

      {err && <p className="rounded bg-surface-2 p-3 text-sm text-brand-secure">{err}</p>}

      <button disabled={busy || (!learnOnly && topic.trim().length < 2) || (learnOnly && refCount === 0)} onClick={submit}
        className="w-full rounded-md bg-primary px-5 py-3 text-sm font-bold text-on-primary disabled:opacity-50">
        {busy ? "처리 중…" : learnOnly ? "학습만 하기" : "콘텐츠 만들기"}
      </button>
      {!learnOnly && topic.trim().length < 2 && (
        <p className="text-center text-xs text-ink-subtle">위에 만들고 싶은 콘텐츠 주제를 먼저 입력해 주세요.</p>
      )}

      {result && (
        <section className="rounded-lg border border-hairline bg-surface-1 p-4 text-xs">
          <div className="font-bold text-sm">결과</div>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre>
          {result.campaign_id ? (
            <a className="text-primary underline" href={`/library/${String(result.campaign_id)}`}>콘텐츠 열기 →</a>
          ) : null}
        </section>
      )}
    </div>
  );
}
