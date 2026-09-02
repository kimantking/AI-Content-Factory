"use client";

import { useCallback, useEffect, useState } from "react";
import {
  MemoryRow,
  getLearningDashboard,
  getRecipes,
  memoryAction,
  runLearning,
} from "@/lib/api";

const SBADGE: Record<string, string> = {
  STRONG: "bg-surface-2 text-success",
  MODERATE: "bg-surface-2 text-primary",
  WEAK: "bg-surface-2 text-brand-secure",
  EXPERIMENTAL: "bg-surface-2 text-ink-subtle",
  DEPRECATED: "bg-surface-2 text-brand-secure",
};
const Badge = ({ s }: { s: string }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SBADGE[s] ?? SBADGE.EXPERIMENTAL}`}>{s}</span>
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
          Pin
        </button>
        <button type="button" onClick={() => onAct(m.id, "disable")} className="rounded border border-hairline px-2 py-0.5 text-xs">
          Disable
        </button>
      </div>
    </div>
  );
}

export default function LearningPage() {
  const [dash, setDash] = useState<Awaited<ReturnType<typeof getLearningDashboard>> | null>(null);
  const [recipes, setRecipes] = useState<Record<string, unknown>[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, r] = await Promise.all([getLearningDashboard(), getRecipes()]);
      setDash(d);
      setRecipes(r);
    } catch (e) {
      setErr(String(e));
    }
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

  if (err) return <p className="text-brand-secure">{err}</p>;
  if (!dash) return <p className="text-subtle">불러오는 중…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">학습 · 메모리</h1>
        <a href="/analytics" className="text-sm text-primary underline">
          ← Analytics
        </a>
      </div>

      <button
        type="button"
        onClick={onRun}
        disabled={busy}
        className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:opacity-50"
      >
        Daily Learning 실행
      </button>
      {dash.last_run && (
        <p className="text-xs text-subtle">
          last run {dash.last_run.run_date} · {JSON.stringify(dash.last_run.summary)}
        </p>
      )}

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
