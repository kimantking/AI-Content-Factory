"use client";

import { useCallback, useEffect, useState } from "react";
import {
  MemoryRow,
  getLearningDashboard,
  getRecipes,
  learningDashboard as getReferenceLearningDashboard,
  memoryAction,
  runLearning,
  retryFailedReferences,
} from "@/lib/api";

const SBADGE: Record<string, string> = {
  STRONG: "bg-surface-2 text-success",
  MODERATE: "bg-surface-2 text-primary",
  WEAK: "bg-surface-2 text-brand-secure",
  EXPERIMENTAL: "bg-surface-2 text-ink-subtle",
  DEPRECATED: "bg-surface-2 text-brand-secure",
};
const MEMORY_STATUS_KO: Record<string, string> = {
  STRONG: "강하게 학습됨", MODERATE: "학습됨", WEAK: "근거 부족",
  EXPERIMENTAL: "시험 중", DEPRECATED: "사용 중지",
};
const Badge = ({ s }: { s: string }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SBADGE[s] ?? SBADGE.EXPERIMENTAL}`}>
    {MEMORY_STATUS_KO[s] ?? s}
  </span>
);

function MemCard({ m, onAct }: { m: MemoryRow; onAct: (id: string, a: string) => void }) {
  return (
    <div className="border-t border-hairline pt-2">
      <p className="text-sm">
        <Badge s={m.status} /> <span className="text-xs text-subtle">{m.type}</span>{" "}
        <span className="text-xs text-subtle">n={m.sample_size} · conf={m.confidence}</span>
      </p>
      <p className="mt-1 text-sm">{m.statement}</p>
      <div className="mt-1 flex gap-2">
        <button type="button" onClick={() => onAct(m.id, "pin")} className="rounded border border-hairline px-2 py-0.5 text-xs">
          항상 사용
        </button>
        <button type="button" onClick={() => onAct(m.id, "disable")} className="rounded border border-hairline px-2 py-0.5 text-xs">
          사용 중지
        </button>
      </div>
    </div>
  );
}

export default function LearningPage() {
  const [wsId, setWsId] = useState("");
  const [dash, setDash] = useState<Awaited<ReturnType<typeof getLearningDashboard>> | null>(null);
  const [referenceLearning, setReferenceLearning] = useState<Awaited<ReturnType<typeof getReferenceLearningDashboard>> | null>(null);
  const [recipes, setRecipes] = useState<Record<string, unknown>[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, r, learned] = await Promise.all([
        getLearningDashboard(), getRecipes(), getReferenceLearningDashboard(wsId || undefined),
      ]);
      setDash(d);
      setRecipes(r);
      setReferenceLearning(learned);
    } catch (e) {
      setErr(String(e));
    }
  }, [wsId]);
  useEffect(() => {
    setWsId(window.localStorage?.getItem("acf_workspace_id") ?? "");
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  async function onAct(id: string, a: string) {
    await memoryAction(id, a);
    load();
  }
  async function onRun() {
    setBusy(true);
    try {
      await runLearning();
      await load();
    } finally {
      setBusy(false);
    }
  }
  async function retryReferences() {
    setBusy(true); setErr(null);
    try { await retryFailedReferences(wsId || undefined); await load(); }
    catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  if (err) return <p className="text-brand-secure">{err}</p>;
  if (!dash) return <p className="text-subtle">불러오는 중…</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start gap-3">
        <div>
          <h1 className="text-lg font-bold">학습 결과 보기</h1>
          <p className="mt-1 text-sm text-ink-subtle">AI가 자료에서 찾아낸 제작 규칙과 기억을 확인합니다.</p>
        </div>
        <a href="/learn-studio" className="btn btn-primary ml-auto">새 자료 학습시키기</a>
      </div>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <h2 className="text-sm font-bold">자료 학습 상태</h2>
            <p className="mt-1 text-xs text-ink-subtle">URL로 넣은 자료를 읽고 분석한 결과입니다.</p>
          </div>
          <div className="ml-auto flex flex-wrap gap-2">
            <button className="btn btn-secondary" disabled={busy} onClick={retryReferences}>
              {busy ? "다시 읽는 중…" : "실패 자료 다시 읽기"}
            </button>
            <a href="/references" className="btn btn-secondary">읽은 자료 확인</a>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {[
            ["등록 자료", referenceLearning?.total_references ?? 0],
            ["학습 완료", referenceLearning?.ready_references ?? 0],
            ["학습 데이터", referenceLearning?.dataset_records ?? 0],
            ["제작 규칙", referenceLearning?.prompt_blueprints ?? 0],
            ["에이전트 스킬", referenceLearning?.learned_skills ?? 0],
            ["콘텐츠 레시피", referenceLearning?.creative_recipes ?? 0],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded bg-surface-2 p-3 text-center">
              <p className="text-xs text-ink-subtle">{label}</p>
              <p className="mt-1 text-lg font-bold">{value}개</p>
            </div>
          ))}
        </div>
        {(referenceLearning?.total_references ?? 0) === 0 ? (
          <p className="mt-3 rounded bg-surface-2 p-3 text-xs text-ink-subtle">
            아직 학습시킨 자료가 없습니다. `새 자료 학습시키기`에서 URL을 넣고 학습 시작을 눌러 주세요.
          </p>
        ) : (
          <p className="mt-3 text-xs text-ink-subtle">
            최근 자료 학습: {referenceLearning?.last_learning_run
              ? new Date(referenceLearning.last_learning_run).toLocaleString("ko-KR") : "기록 없음"}
          </p>
        )}
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <h2 className="text-sm font-bold">게시 성과 학습</h2>
        <p className="mt-1 text-xs text-ink-subtle">
          SNS에 게시한 콘텐츠의 조회수·수익 데이터를 분석합니다. 아직 게시한 콘텐츠가 없으면 아래 항목이 0으로 보이는 것이 정상입니다.
        </p>
      <button
        type="button"
        onClick={onRun}
        disabled={busy}
        className="mt-3 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:opacity-50"
      >
        게시 성과 다시 분석하기
      </button>
      {dash.last_run && (
        <p className="text-xs text-subtle">
          최근 분석 {dash.last_run.run_date} · 기록 {String(dash.last_run.summary.records ?? 0)}개 ·
          패턴 {String(dash.last_run.summary.patterns ?? 0)}개 · 완료한 실험 {String(dash.last_run.summary.experiments_completed ?? 0)}개
        </p>
      )}
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <h2 className="mb-2 text-sm font-bold">강함 ({dash.strong.length})</h2>
        {dash.strong.map((m) => (
          <MemCard key={m.id} m={m} onAct={onAct} />
        ))}
        {dash.strong.length === 0 && <p className="text-xs text-subtle">아직 강한 패턴 없음</p>}
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <h2 className="mb-2 text-sm font-bold">보통 ({dash.moderate.length})</h2>
        {dash.moderate.map((m) => (
          <MemCard key={m.id} m={m} onAct={onAct} />
        ))}
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <h2 className="mb-2 text-sm font-bold">실험·약함 ({dash.experimental.length})</h2>
        {dash.experimental.slice(0, 20).map((m) => (
          <MemCard key={m.id} m={m} onAct={onAct} />
        ))}
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <h2 className="mb-2 text-sm font-bold">콘텐츠 레시피 ({recipes.length})</h2>
        {recipes.map((r, i) => (
          <pre key={i} className="mt-1 whitespace-pre-wrap rounded bg-surface-2 p-2 text-xs">
            {JSON.stringify(r, null, 2)}
          </pre>
        ))}
      </section>
    </div>
  );
}
