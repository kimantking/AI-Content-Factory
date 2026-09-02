"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { addPlatformToContent, contentDetail, contentVideoUrl } from "@/lib/api";

const TABS = ["overview", "preview", "script", "platform_versions", "media",
  "references", "learning", "governance", "publishing", "analytics", "revenue", "history"] as const;
const TAB_KO: Record<string, string> = {
  overview: "개요", preview: "미리보기", script: "대본", platform_versions: "플랫폼 버전",
  media: "미디어", references: "참고자료", learning: "학습 근거", governance: "검수",
  publishing: "게시", analytics: "분석", revenue: "수익", history: "변경 이력",
};

export default function ContentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<Record<string, any> | null>(null);
  const [tab, setTab] = useState<string>("overview");
  const [err, setErr] = useState<string | null>(null);
  const [addPlat, setAddPlat] = useState("instagram_reel");
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    contentDetail(id).then(setD).catch((e) => setErr(String(e)));
  }, [id]);
  useEffect(load, [load]);

  if (err) return <main className="p-6 text-sm text-brand-secure">{err}</main>;
  if (!d) return <main className="p-6 text-sm text-ink-subtle">불러오는 중…</main>;

  const ov = d.overview;
  const section = d[tab];

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <div>
        <h1 className="text-xl font-bold">{ov.topic}</h1>
        <div className="mt-1 flex flex-wrap gap-1 text-[11px]">
          {ov.legacy && <span className="rounded bg-surface-2 px-1 text-ink-subtle">LEGACY</span>}
          {ov.is_demo && <span className="rounded bg-surface-2 px-1 text-primary">DEMO / 테스트</span>}
          <span className="rounded bg-surface-2 px-1">{ov.status}</span>
          <span className="rounded bg-surface-2 px-1">검수 {ov.governance}</span>
          <span className="rounded bg-surface-2 px-1">게시 {ov.publish_state}</span>
        </div>
      </div>

      <nav className="flex flex-wrap gap-1 border-b border-hairline text-xs">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-2 py-1 ${tab === t ? "border-b-2 border-hairline-strong font-bold" : "text-ink-subtle"}`}>
            {TAB_KO[t]}
          </button>
        ))}
      </nav>

      {tab === "preview" && section.video_playable ? (
        <div className="space-y-2">
          <video controls className="w-full rounded-lg bg-black" src={contentVideoUrl(id)} />
          <div className="text-xs text-ink-subtle">
            {section.width}×{section.height} · {section.duration}s · {section.fps ?? "?"}fps ·
            {section.size_bytes ? ` ${(section.size_bytes / 1e6).toFixed(1)}MB` : ""} · v{section.version ?? 1}
          </div>
        </div>
      ) : tab === "preview" ? (
        <p className="text-sm text-ink-subtle">재생 가능한 영상 파일이 없습니다.{section.video_path ? " (경로만 존재)" : ""}</p>
      ) : tab === "platform_versions" ? (
        <ul className="space-y-1 text-sm">
          {section.map((p: any, i: number) => (
            <li key={i} className="rounded border border-hairline p-2">
              <b>{p.platform}</b> {p.generated ? `· ${p.content_type} · ${p.status}` : `· ${p.note}`}
              {p.governance_decision && <span className="ml-2 text-xs text-ink-subtle">검수 {p.governance_decision}</span>}
            </li>
          ))}
          <li className="rounded border border-dashed border-hairline p-2 text-xs">
            플랫폼 추가:{" "}
            <select className="input !w-auto !py-1" value={addPlat} onChange={(e) => setAddPlat(e.target.value)}>
              {["instagram_reel", "tiktok", "x", "threads", "linkedin", "naver_blog"].map((p) => <option key={p}>{p}</option>)}
            </select>{" "}
            <button className="rounded bg-primary px-2 py-0.5 text-on-primary"
              onClick={async () => {
                try {
                  const r = await addPlatformToContent(id, addPlat);
                  setMsg(`추가됨: ${r.added} (기존 ${r.unchanged.join(", ")} 재생성 없음)`);
                  load();
                } catch (e) { setMsg(String(e)); }
              }}>추가</button>
            {msg && <span className="ml-2 text-success">{msg}</span>}
          </li>
        </ul>
      ) : (
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg border border-hairline bg-surface-1 p-3 text-xs">
          {JSON.stringify(section, null, 2)}
        </pre>
      )}
    </main>
  );
}
