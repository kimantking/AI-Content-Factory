"use client";

import { useCallback, useEffect, useState } from "react";
import { ReferenceRow, getReference, listReferences } from "@/lib/api";

const STATUS: Record<string, string> = {
  READY: "bg-surface-2 text-success", EXTRACTED: "bg-surface-2 text-primary",
  BLOCKED: "bg-surface-2 text-brand-secure", DUPLICATE: "bg-surface-2 text-ink-subtle",
  LOW_VALUE: "bg-surface-2 text-brand-secure", FETCH_FAILED: "bg-surface-2 text-brand-secure",
};

export default function ReferenceLibraryPage() {
  const [wsId, setWsId] = useState("");
  const [rows, setRows] = useState<ReferenceRow[]>([]);
  const [detail, setDetail] = useState<(ReferenceRow & { analyses: Record<string, unknown> }) | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    listReferences(wsId || undefined).then(setRows).catch((e) => setErr(String(e)));
  }, [wsId]);

  useEffect(() => {
    setWsId(window.localStorage?.getItem("acf_workspace_id") ?? "");
  }, []);
  useEffect(load, [load]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">자료실</h1>
      {err && <p className="text-sm text-brand-secure">{err}</p>}
      <div className="overflow-x-auto rounded-lg border border-hairline bg-surface-1">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-xs text-ink-subtle">
            <tr>
              <th className="p-2">Title / URL</th><th className="p-2">유형</th>
              <th className="p-2">목적</th><th className="p-2">상태</th>
              <th className="p-2">품질</th><th className="p-2">권리</th><th className="p-2">Inj</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="cursor-pointer border-t border-hairline hover:bg-surface-2"
                onClick={() => getReference(r.id).then(setDetail).catch((e) => setErr(String(e)))}>
                <td className="p-2">
                  <div className="font-medium">{r.title || "(제목 없음)"}</div>
                  <div className="text-xs text-ink-tertiary">{r.canonical_url}</div>
                </td>
                <td className="p-2 text-xs">{r.source_type}<br />{r.support_level}</td>
                <td className="p-2 text-xs">{r.resolved_purpose || r.purpose}</td>
                <td className="p-2"><span className={"rounded px-1.5 py-0.5 text-xs " + (STATUS[r.status] ?? "bg-surface-2")}>{r.status}</span></td>
                <td className="p-2 text-xs">{r.quality_score.toFixed(2)} · w{r.learning_weight.toFixed(2)}</td>
                <td className="p-2 text-xs">{r.rights_status}</td>
                <td className="p-2 text-xs">{r.injection_flag ? "⚠️" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detail && (
        <section className="rounded-lg border border-hairline bg-surface-1 p-5">
          <div className="flex items-center">
            <h2 className="text-sm font-bold">{detail.title}</h2>
            <button className="ml-auto text-xs underline" onClick={() => setDetail(null)}>닫기</button>
          </div>
          {detail.injection_flag && (
            <p className="mt-1 text-xs text-brand-secure">
              프롬프트 인젝션 탐지: {JSON.stringify(detail.injection_detail)} — 지시로 실행되지 않고 데이터로만 취급됨
            </p>
          )}
          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap text-xs">
            {JSON.stringify(detail.analyses, null, 2)}
          </pre>
        </section>
      )}
    </div>
  );
}
