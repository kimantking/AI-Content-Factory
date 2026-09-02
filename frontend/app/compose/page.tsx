"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CostPreview,
  PlatformSelection,
  composeCampaign,
  platformContentTypes,
} from "@/lib/api";

const MODES = [
  ["CREATE_AND_LEARN", "학습 + 콘텐츠 만들기"],
  ["CREATE_ONLY", "콘텐츠 만들기"],
  ["LEARN_ONLY", "학습만 하기"],
  ["REFERENCE_ONLY", "참고자료만 저장"],
] as const;

const CYCLE = ["DISABLED", "GENERATE_ONLY", "GENERATE_AND_PUBLISH"] as const;
const CYCLE_LABEL: Record<string, string> = {
  DISABLED: "off", GENERATE_ONLY: "제작만", GENERATE_AND_PUBLISH: "제작+게시",
};

export default function ComposePage() {
  const [wsId, setWsId] = useState("");
  const [topic, setTopic] = useState("");
  const [urls, setUrls] = useState<string[]>([""]);
  const [mode, setMode] = useState<string>("CREATE_AND_LEARN");
  const [cts, setCts] = useState<Record<string, string[]>>({});
  const [presets, setPresets] = useState<string[]>([]);
  const [sel, setSel] = useState<PlatformSelection>({});
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [cost, setCost] = useState<CostPreview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setWsId(window.localStorage?.getItem("acf_workspace_id") ?? "");
    platformContentTypes().then((r) => {
      setCts(r.content_types);
      setPresets(r.presets);
    }).catch((e) => setErr(String(e)));
  }, []);

  const learnOnly = mode === "LEARN_ONLY" || mode === "REFERENCE_ONLY";

  const setMode3 = (p: string, ct: string, cur: string) => {
    const next = CYCLE[(CYCLE.indexOf(cur as typeof CYCLE[number]) + 1) % CYCLE.length];
    setSel((s) => ({ ...s, [p]: { ...(s[p] ?? {}), [ct]: next } }));
  };
  const modeOf = (p: string, ct: string) => sel[p]?.[ct] ?? "DISABLED";

  const applyPreset = (name: string) => {
    // just tag it; server expands builtin presets
    setSel({});
    setResult({ preset: name });
  };
  const allOn = () => {
    const s: PlatformSelection = {};
    Object.entries(cts).forEach(([p, list]) => {
      s[p] = {};
      list.forEach((ct) => (s[p][ct] = "GENERATE_AND_PUBLISH"));
    });
    setSel(s);
  };
  const allOff = () => setSel({});

  const generateCount = useMemo(
    () => Object.values(sel).flatMap((c) => Object.values(c)).filter((m) => m !== "DISABLED").length,
    [sel],
  );

  const submit = async () => {
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      const presetName = (result as { preset?: string } | null)?.preset;
      const body = {
        topic: topic.trim() || undefined,
        execution_mode: mode,
        reference_urls: urls.map((u) => u.trim()).filter(Boolean),
        workspace_id: wsId || undefined,
        ...(presetName ? { preset: presetName } : { platform_selection: sel }),
      };
      const r = await composeCampaign(body);
      setResult(r as unknown as Record<string, unknown>);
      setCost((r as { cost_preview?: CostPreview }).cost_preview ?? null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">캠페인 만들기</h1>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <label className="text-sm font-bold">오늘의 주제</label>
        <input
          className="mt-2 w-full rounded-lg border border-hairline px-3 py-2"
          placeholder="AI 때문에 바뀌는 직업 5가지"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        {learnOnly && (
          <p className="mt-1 text-xs text-ink-subtle">학습 전용 모드에서는 주제가 없어도 됩니다.</p>
        )}
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <div className="mb-2 text-sm font-bold">참고자료 (URL)</div>
        {urls.map((u, i) => (
          <input
            key={i}
            className="mb-2 w-full rounded-lg border border-hairline px-3 py-2 text-sm"
            placeholder="https://…"
            value={u}
            onChange={(e) => setUrls((a) => a.map((x, j) => (j === i ? e.target.value : x)))}
          />
        ))}
        <button className="text-sm text-primary underline" onClick={() => setUrls((a) => [...a, ""])}>
          + URL 추가
        </button>
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <div className="mb-2 text-sm font-bold">작업 모드</div>
        {MODES.map(([v, label]) => (
          <label key={v} className="mr-4 inline-flex items-center gap-1 text-sm">
            <input type="radio" name="mode" checked={mode === v} onChange={() => setMode(v)} />
            {label}
          </label>
        ))}
      </section>

      {!learnOnly && (
        <section className="rounded-lg border border-hairline bg-surface-1 p-5">
          <div className="mb-2 flex items-center gap-2 text-sm font-bold">
            게시 플랫폼
            <button className="ml-auto text-xs underline" onClick={allOn}>전체 선택</button>
            <button className="text-xs underline" onClick={allOff}>전체 해제</button>
          </div>
          <div className="mb-2 flex flex-wrap gap-1">
            {presets.map((p) => (
              <button key={p} className="rounded border border-hairline px-2 py-0.5 text-xs"
                onClick={() => applyPreset(p)}>프리셋: {p}</button>
            ))}
          </div>
          <div className="space-y-1">
            {Object.entries(cts).map(([p, list]) => (
              <div key={p} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="w-36 font-medium">{p}</span>
                {list.map((ct) => {
                  const m = modeOf(p, ct);
                  return (
                    <button
                      key={ct}
                      onClick={() => setMode3(p, ct, m)}
                      className={
                        "rounded border px-2 py-0.5 text-xs " +
                        (m === "GENERATE_AND_PUBLISH"
                          ? "border-hairline-strong bg-surface-2 text-success"
                          : m === "GENERATE_ONLY"
                            ? "border-hairline-strong bg-surface-2 text-brand-secure"
                            : "border-hairline text-ink-tertiary")
                      }
                    >
                      {ct} · {CYCLE_LABEL[m]}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-ink-subtle">선택한 플랫폼만 제작/게시됩니다 · 현재 {generateCount}개 형식 켜짐</p>
        </section>
      )}

      {err && <p className="rounded-lg bg-surface-2 p-3 text-sm text-brand-secure">{err}</p>}

      <button
        disabled={busy}
        onClick={submit}
        className="rounded-md bg-primary px-5 py-2.5 text-sm font-bold text-on-primary disabled:opacity-50"
      >
        {busy ? "처리 중…" : learnOnly ? "학습만 하기" : "콘텐츠 만들기"}
      </button>

      {result && !("preset" in result) && (
        <section className="rounded-lg border border-hairline bg-surface-1 p-5 text-sm">
          <div className="font-bold">결과</div>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs">
            {JSON.stringify(result, null, 2)}
          </pre>
          {cost && (
            <p className="mt-2 text-xs text-ink-subtle">
              예상 비용: {String(cost.total_est_usd)} · {cost.note}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
