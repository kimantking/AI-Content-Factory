"use client";

import { useCallback, useEffect, useState } from "react";
import { LearningDashboard, LearningGaps, addReferences, learningDashboard, learningGaps } from "@/lib/api";
import { PageHeader, Card, CardBody, CardTitle, Metric } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Icon } from "@/components/ui/Icon";

const PURPOSE: { id: string; ko: string }[] = [
  { id: "AUTO", ko: "자동 판별" },
  { id: "FACT_SOURCE", ko: "사실 근거" },
  { id: "KNOWLEDGE", ko: "지식" },
  { id: "STYLE_REFERENCE", ko: "스타일 참고" },
  { id: "VIDEO_REFERENCE", ko: "영상 참고" },
  { id: "COMPETITOR_REFERENCE", ko: "경쟁 콘텐츠" },
  { id: "TECHNICAL_REFERENCE", ko: "기술 자료" },
];
const DATASET_KO: Record<string, string> = {
  VIDEO_DATASET: "영상 데이터셋",
  HOOK_DATASET: "훅 데이터셋",
  THUMBNAIL_DATASET: "썸네일 데이터셋",
  EDITING_DATASET: "편집 데이터셋",
  WRITING_DATASET: "대본 데이터셋",
  FACT_DATASET: "사실 데이터셋",
};
const FLOW = ["자료 수집", "자료 분석", "패턴 발견", "스킬 생성", "제작 규칙", "에이전트 적용"];

export default function LearnStudioPage() {
  const [wsId, setWsId] = useState("");
  const [urls, setUrls] = useState("");
  const scope = "WORKSPACE";
  const [purpose, setPurpose] = useState("AUTO");
  const [dash, setDash] = useState<LearningDashboard | null>(null);
  const [gaps, setGaps] = useState<LearningGaps | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(() => {
    const w = wsId || undefined;
    learningDashboard(w).then(setDash).catch((e) => setErr(String(e)));
    learningGaps(w).then(setGaps).catch(() => undefined);
  }, [wsId]);

  useEffect(() => {
    setWsId(window.localStorage?.getItem("acf_workspace_id") ?? "");
  }, []);
  useEffect(refresh, [refresh]);

  const run = async () => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const list = urls.split(/\s+/).map((u) => u.trim()).filter(Boolean);
      const r = await addReferences({ urls: list, execution_mode: "LEARN_ONLY", scope, purpose, workspace_id: wsId || undefined });
      const res = r.result as { counters?: Record<string, number>; datasets?: number; blueprints?: number; skills?: number };
      setMsg(
        `학습 완료 · 준비 ${res.counters?.ready ?? 0} / 차단 ${res.counters?.blocked ?? 0} / 중복 ${res.counters?.duplicates ?? 0} · 데이터 항목 ${res.datasets ?? 0} · 제작 규칙 ${res.blueprints ?? 0} · 스킬 ${res.skills ?? 0}`,
      );
      setUrls("");
      refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="AI 학습실"
        eyebrow="학습"
        description="모든 에이전트가 자료를 함께 학습하고, 게시할 때는 채널 주제에 맞는 콘텐츠만 사용합니다."
        actions={
          <button className="btn btn-secondary" onClick={refresh}>
            <Icon name="refresh" size={15} />
            새로고침
          </button>
        }
      />

      {/* reference input */}
      <div className="panel overflow-hidden">
        <div className="p-4 sm:p-5">
          <label htmlFor="ref-urls" className="text-caption font-medium text-ink-subtle">
            학습할 자료 (URL, 한 줄에 하나씩)
          </label>
          <textarea
            id="ref-urls"
            className="input mt-1.5 h-24 resize-none"
            placeholder="https://…"
            value={urls}
            onChange={(e) => setUrls(e.target.value)}
          />
          <div className="mt-3 space-y-2.5">
            <div>
              <p className="text-caption text-ink-subtle">학습 목적</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {PURPOSE.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setPurpose(p.id)}
                    aria-pressed={purpose === p.id}
                    className={`rounded-md border px-2.5 py-1 text-caption ${
                      purpose === p.id ? "border-primary bg-primary/10 text-ink" : "border-hairline text-ink-subtle"
                    }`}
                  >
                    {p.ko}
                  </button>
                ))}
              </div>
            </div>
            <p className="text-caption text-ink-subtle">
              저장 범위: 작업공간 전체 · 이 자료는 모든 에이전트와 채널이 함께 학습합니다.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 border-t border-hairline bg-white/[0.02] p-4 sm:px-5">
          <button disabled={busy} onClick={run} className="btn btn-primary">
            {busy ? "학습 중…" : "학습 시작"}
            {!busy && <Icon name="arrow-right" size={15} />}
          </button>
          {msg && <p className="text-caption text-success">{msg}</p>}
          {err && <p className="text-caption text-brand-secure">{err}</p>}
        </div>
      </div>

      {/* learning flow */}
      <Card>
        <CardBody>
          <CardTitle>학습 흐름</CardTitle>
          <ol className="flex flex-wrap items-center gap-x-2 gap-y-2 text-body-sm">
            {FLOW.map((step, i) => (
              <li key={step} className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full border border-hairline text-caption text-ink-tertiary">
                  {i + 1}
                </span>
                <span className="text-ink-muted">{step}</span>
                {i < FLOW.length - 1 && <Icon name="chevron-right" size={14} className="text-ink-tertiary" />}
              </li>
            ))}
          </ol>
        </CardBody>
      </Card>

      {/* 4 headline stats + secondary */}
      {dash && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "참고자료", value: dash.total_references, hint: `준비 ${dash.ready_references}개` },
              { label: "데이터 항목", value: dash.dataset_records, hint: `영상 ${dash.video_references} · 대본 ${dash.writing_references}` },
              { label: "학습된 스킬", value: dash.learned_skills, hint: `레시피 ${dash.creative_recipes}개` },
              { label: "제작 규칙", value: dash.prompt_blueprints, hint: `컬렉션 ${dash.collections}개` },
            ].map((s) => (
              <Card key={s.label}>
                <CardBody className="!p-4">
                  <Metric label={s.label} value={s.value} hint={s.hint} />
                </CardBody>
              </Card>
            ))}
          </div>
          <Card>
            <CardBody>
              <dl>
                <div className="kv"><dt>학습 비용</dt><dd>${Number(dash.learning_cost_usd ?? 0).toFixed(2)}</dd></div>
                <div className="kv"><dt>최근 학습</dt><dd>{dash.last_learning_run?.slice(0, 16) ?? "없음"}</dd></div>
              </dl>
            </CardBody>
          </Card>
        </>
      )}

      {/* gaps */}
      {gaps && gaps.recommendations.length > 0 && (
        <Card>
          <CardBody>
            <CardTitle>더 배우면 좋은 자료</CardTitle>
            <ul className="space-y-2 text-body-sm">
              {gaps.recommendations.map((r, i) => (
                <li key={i} className="flex items-start gap-2">
                  <StatusBadge value={r.priority} size="sm" />
                  <span className="text-ink-muted">
                    {r.reason} — {DATASET_KO[r.recommended_dataset] ?? r.recommended_dataset}{" "}
                    <span className="text-ink-tertiary">({r.have}/{r.target})</span>
                  </span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
