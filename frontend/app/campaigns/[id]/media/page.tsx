"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import {
  MediaStatus,
  fileUrl,
  getMedia,
  regenerateScene,
  startMedia,
} from "@/lib/api";

const BADGE: Record<string, string> = {
  SUCCESS: "bg-surface-2 text-success",
  RUNNING: "bg-surface-2 text-brand-secure",
  RETRY: "bg-surface-2 text-brand-secure",
  FALLBACK: "bg-surface-2 text-primary",
  FAILED: "bg-surface-2 text-brand-secure",
  WAITING: "bg-surface-2 text-ink-subtle",
  PENDING: "bg-surface-2 text-ink-subtle",
  PLANNED: "bg-surface-2 text-primary",
  FIX_REQUIRED: "bg-surface-2 text-brand-secure",
};

function Badge({ s }: { s: string }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[s] ?? BADGE.WAITING}`}>
      {s}
    </span>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-hairline bg-surface-1 p-5">
      <h2 className="mb-3 text-sm font-bold">{title}</h2>
      {children}
    </section>
  );
}

export default function MediaPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<MediaStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const poll = useCallback(async () => {
    try {
      const d = await getMedia(id);
      setData(d);
      const running =
        d.media_status === "RUNNING" ||
        d.progress.some((p) => p.status === "RUNNING");
      if (running) timer.current = setTimeout(poll, 1500);
    } catch (e) {
      setErr(String(e));
    }
  }, [id]);

  useEffect(() => {
    poll();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [poll]);

  async function onStart() {
    setBusy(true);
    setErr(null);
    try {
      await startMedia(id, data?.media_status === "FAILED");
      setTimeout(poll, 800);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onRegen(sceneId: string) {
    const narration = window.prompt("새 내레이션 (비우면 유지):") ?? undefined;
    setBusy(true);
    try {
      await regenerateScene(id, sceneId, narration ? { narration } : {});
      setTimeout(poll, 500);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (err) return <p className="text-brand-secure">{err}</p>;
  if (!data) return <p className="text-subtle">불러오는 중…</p>;

  return (
    <main className="space-y-6">
      <div className="flex items-center justify-between">
        <a href={`/campaigns/${id}`} className="text-sm text-primary underline">
          ← 캠페인
        </a>
        <div className="text-right text-xs text-subtle">
          미디어 비용 ${data.cost_total.toFixed(4)} / 한도 ${data.media_budget}
        </div>
      </div>

      <button
        type="button"
        onClick={onStart}
        disabled={busy}
        className="w-full rounded-md bg-primary px-4 py-3 text-sm font-semibold text-on-primary disabled:opacity-50"
      >
        {busy
          ? "영상 제작 요청 중…"
          : data.media_status === "FAILED"
            ? "멈춘 단계부터 다시 시작"
            : data.media_status === "RUNNING"
              ? "영상 제작 진행 중"
              : "영상 제작 시작"}
      </button>

      {data.render.video && (
        <a
          href={`/campaigns/${id}/publish`}
          className="block rounded-md border border-hairline-strong px-4 py-2 text-center text-sm font-semibold text-ink"
        >
          완성된 영상을 SNS에 게시하기 →
        </a>
      )}

      <section className="grid grid-cols-3 gap-2 sm:grid-cols-5">
        {data.progress.map((p) => (
          <div key={p.name} className="rounded-lg border border-hairline bg-surface-1 p-2">
            <p className="truncate text-[11px] text-subtle">{p.name}</p>
            <Badge s={p.status} />
          </div>
        ))}
      </section>

      <Card title="제작 단계별 비용">
        <div className="flex flex-wrap gap-3 text-sm">
          {Object.entries(data.cost_by_kind).map(([k, v]) => (
            <span key={k} className="rounded bg-surface-2 px-2 py-1">
              {k}: ${v.toFixed(4)}
            </span>
          ))}
          {Object.keys(data.cost_by_kind).length === 0 && (
            <span className="text-subtle">아직 사용된 비용이 없습니다.</span>
          )}
        </div>
      </Card>

      <Card title={`장면별 제작 현황 (${data.scene_monitor.length}개)`}>
        <div className="space-y-2">
          {data.scene_monitor.map((sc) => (
            <div key={sc.scene_id} className="flex items-center gap-3 border-t border-hairline pt-2">
              {sc.still && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={fileUrl(sc.still) ?? ""} alt="" className="h-14 w-10 rounded object-cover" />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">
                  #{sc.order + 1} · {sc.visual_type} · {sc.camera_motion} · {sc.duration}s
                </p>
                <p className="truncate text-xs text-subtle">{sc.narration}</p>
              </div>
              <Badge s={sc.status} />
              <button
                type="button"
                onClick={() => onRegen(sc.scene_id)}
                disabled={busy}
                className="rounded border border-hairline px-2 py-1 text-xs disabled:opacity-40"
              >
                재생성
              </button>
            </div>
          ))}
        </div>
      </Card>

      {data.render.video && (
        <Card title={`최종 영상 · ${data.render.width}×${data.render.height} · ${data.render.duration}s`}>
          <video src={fileUrl(data.render.video) ?? ""} controls className="w-full rounded-lg" />
        </Card>
      )}

      {data.thumbnails.filter(Boolean).length > 0 && (
        <Card title="썸네일 후보">
          <div className="flex flex-wrap gap-2">
            {data.thumbnails.filter(Boolean).map((t, i) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={i} src={fileUrl(t) ?? ""} alt="" className="h-24 rounded" />
            ))}
          </div>
        </Card>
      )}

      <Card title="플랫폼별 미리보기">
        <div className="space-y-4">
          {data.previews.map((p) => (
            <div key={p.platform} className="border-t border-hairline pt-3">
              <p className="text-sm font-semibold">
                {p.label} <Badge s={p.status} />{" "}
                <span className="text-xs text-subtle">
                  {p.content_type} · {p.aspect_ratio}
                </span>
              </p>
              {p.hook && <p className="mt-1 text-sm">Hook · {p.hook}</p>}
              {p.video && (
                <video src={fileUrl(p.video) ?? ""} controls className="mt-2 w-full max-w-xs rounded-lg" />
              )}
              {p.images.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {p.images.map((im, i) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img key={i} src={fileUrl(im) ?? ""} alt="" className="h-28 rounded" />
                  ))}
                </div>
              )}
              {p.family === "TEXT" && p.script && (
                <pre className="mt-2 whitespace-pre-wrap rounded bg-surface-2 p-2 text-xs">{p.script}</pre>
              )}
              {p.hashtags.length > 0 && (
                <p className="mt-1 text-xs text-primary">{p.hashtags.join(" ")}</p>
              )}
            </div>
          ))}
        </div>
      </Card>
    </main>
  );
}
