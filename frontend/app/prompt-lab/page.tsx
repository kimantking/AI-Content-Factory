"use client";

import { useCallback, useEffect, useState } from "react";
import {
  LearnedSkillRow,
  PromptBlueprintRow,
  getBlueprint,
  listBlueprints,
  listSkills,
  promoteBlueprint,
  rollbackBlueprint,
  testBlueprint,
} from "@/lib/api";

const NEXT: Record<string, string> = {
  OBSERVED: "EXPERIMENTAL", EXPERIMENTAL: "CANDIDATE", CANDIDATE: "VALIDATED",
  VALIDATED: "PROMOTED",
};
const BADGE: Record<string, string> = {
  OBSERVED: "bg-surface-2 text-ink-subtle", EXPERIMENTAL: "bg-surface-2 text-primary",
  CANDIDATE: "bg-surface-2 text-brand-secure", VALIDATED: "bg-surface-2 text-primary",
  PROMOTED: "bg-surface-2 text-success", DEPRECATED: "bg-surface-2 text-ink-tertiary",
  REJECTED: "bg-surface-2 text-brand-secure",
};

export default function PromptLabPage() {
  const [wsId, setWsId] = useState("");
  const [bps, setBps] = useState<PromptBlueprintRow[]>([]);
  const [skills, setSkills] = useState<LearnedSkillRow[]>([]);
  const [sel, setSel] = useState<(PromptBlueprintRow & { evidence: Record<string, unknown>[] }) | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    const w = wsId || undefined;
    listBlueprints(w).then(setBps).catch((e) => setErr(String(e)));
    listSkills(w).then(setSkills).catch(() => undefined);
  }, [wsId]);

  useEffect(() => {
    setWsId(window.localStorage?.getItem("acf_workspace_id") ?? "");
  }, []);
  useEffect(load, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try {
      await fn();
      load();
      if (sel) getBlueprint(sel.id).then(setSel);
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">프롬프트 실험실</h1>
      {err && <p className="text-sm text-brand-secure">{err}</p>}

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <h2 className="mb-2 text-sm font-bold">학습된 스킬 ({skills.length})</h2>
        <ul className="space-y-1 text-sm">
          {skills.slice(0, 30).map((s) => (
            <li key={s.id}>
              <span className={"rounded px-1 text-xs " + (BADGE[s.status] ?? "")}>{s.status}</span>{" "}
              <b>{s.agent_type}</b> · {s.rule}{" "}
              <span className="text-xs text-ink-tertiary">(n={s.sample_size}, conf {s.confidence.toFixed(2)})</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-hairline bg-surface-1 p-5">
        <h2 className="mb-2 text-sm font-bold">제작 규칙 ({bps.length})</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-ink-subtle">
              <tr><th className="p-1">에이전트</th><th className="p-1">목적</th><th className="p-1">상태</th>
                <th className="p-1">n</th><th className="p-1">conf</th><th className="p-1">div</th><th className="p-1"></th></tr>
            </thead>
            <tbody>
              {bps.map((b) => (
                <tr key={b.id} className="border-t border-hairline">
                  <td className="p-1">{b.agent_type}</td>
                  <td className="p-1 text-xs">{b.purpose}</td>
                  <td className="p-1"><span className={"rounded px-1 text-xs " + (BADGE[b.status] ?? "")}>{b.status}</span></td>
                  <td className="p-1">{b.sample_size}</td>
                  <td className="p-1">{b.confidence.toFixed(2)}</td>
                  <td className="p-1">{b.source_diversity.toFixed(2)}</td>
                  <td className="p-1 space-x-1 text-xs">
                    <button className="underline" onClick={() => act(async () => {
                      const r = await testBlueprint(b.id, {});
                      setPreview((r as { preview_prompt: string }).preview_prompt);
                      const d = await getBlueprint(b.id);
                      setSel(d);
                    })}>미리보기·테스트</button>
                    {NEXT[b.status] && (
                      <button className="underline" onClick={() => act(() => promoteBlueprint(b.id, NEXT[b.status]))}>
                        → {NEXT[b.status]}
                      </button>
                    )}
                    <button className="underline" onClick={() => act(() => rollbackBlueprint(b.id))}>되돌리기</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {sel && (
        <section className="rounded-lg border border-hairline bg-surface-1 p-5 text-sm">
          <div className="flex items-center">
            <h2 className="text-sm font-bold">{sel.agent_type} — {sel.purpose}</h2>
            <button className="ml-auto text-xs underline" onClick={() => { setSel(null); setPreview(null); }}>닫기</button>
          </div>
          <div className="mt-2 text-xs">
            <b>지침</b>: <ul className="ml-4 list-disc">{sel.instructions.map((i, k) => <li key={k}>{i}</li>)}</ul>
            <b>제약</b>: <ul className="ml-4 list-disc">{sel.constraints.map((i, k) => <li key={k}>{i}</li>)}</ul>
            <b>Evidence ({sel.evidence.length})</b>:
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(sel.evidence, null, 2)}</pre>
          </div>
          {preview && (
            <>
              <div className="mt-3 text-xs font-bold">구성 미리보기</div>
              <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap text-xs">{preview}</pre>
            </>
          )}
        </section>
      )}
    </div>
  );
}
