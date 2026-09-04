"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { getCampaign, getMedia, type CampaignDetail, type MediaStatus } from "@/lib/api";
import { PageHeader, Card, CardBody, CardTitle, ErrorState, Metric, Skeleton, SkeletonText } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { JobProgress, type JobStep } from "@/components/ui/JobProgress";
import { Icon } from "@/components/ui/Icon";

const STEP_KO: Record<string, string> = {
  create_campaign: "캠페인 생성", research: "리서치", fact_check: "팩트체크", research_fix: "리서치 보완",
  strategize: "전략", hook: "훅", write_script: "대본", qa_script: "대본 QA", persist: "저장",
  "media:queued": "영상 제작 준비",
};

function elapsed(iso: string) {
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}분 ${s % 60}초` : `${s}초`;
}

export default function CampaignPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<CampaignDetail | null>(null);
  const [media, setMedia] = useState<MediaStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const d = await getCampaign(id);
        if (!alive) return;
        setData(d);
        getMedia(id).then((m) => alive && setMedia(m)).catch(() => undefined);
        if (d.status === "RUNNING" || d.status === "WAITING") {
          timer.current = setTimeout(tick, 1500);
        }
      } catch (e) {
        if (alive) setErr(String(e));
      }
    }
    tick();
    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [id]);

  if (err) return <ErrorState detail={err} />;
  if (!data)
    return (
      <div className="space-y-5">
        <Skeleton className="h-8 w-64" />
        <Card lift>
          <CardBody>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <SkeletonText lines={3} />
          </CardBody>
        </Card>
      </div>
    );

  const mediaActive = data.current_step?.startsWith("media:") ?? false;
  const textPipelineComplete = mediaActive || data.status === "SUCCESS";
  const scriptSteps: JobStep[] = data.steps
    .filter((s) => s.name !== "create_campaign")
    .map((s) => ({
      key: s.name,
      label: STEP_KO[s.name] ?? s.name,
      state: textPipelineComplete ? "SUCCESS" : s.status,
    }));
  const mediaState = mediaActive
    ? (media?.media_status || "RUNNING")
    : data.status === "SUCCESS"
      ? (media?.media_status || "WAITING")
      : "WAITING";
  const stages: JobStep[] = [
    ...scriptSteps,
    { key: "media", label: "미디어", state: mediaState },
    { key: "render", label: "렌더링", state: media?.render?.video ? "SUCCESS" : mediaState === "SUCCESS" ? "RUNNING" : "WAITING" },
    { key: "governance", label: "거버넌스", state: "WAITING" },
    { key: "publish", label: "게시", state: "WAITING" },
  ];

  const runningAgent =
    data.agent_runs.find((r) => r.status === "RUNNING") ?? data.agent_runs[data.agent_runs.length - 1];
  const doneScenes = media?.scene_monitor?.filter((s) => s.status === "SUCCESS" || s.status === "DONE").length ?? 0;
  const totalScenes = media?.scene_monitor?.length ?? 0;
  const nat = data.script?.naturalness as
    | { ai_slop_before?: number; ai_slop_after?: number; burstiness?: number }
    | undefined;

  return (
    <div className="space-y-5">
      <PageHeader
        title={data.topic}
        eyebrow="현재 작업"
        description={`${data.audience_goal} · ${data.platforms.join(", ")}`}
        actions={<StatusBadge value={data.status} />}
      />

      {/* live metrics */}
      <Card lift>
        <CardBody>
          <div className="grid grid-cols-2 gap-y-4 sm:grid-cols-4 lg:grid-cols-6">
            <Metric size="sm" label="현재 단계" value={STEP_KO[data.current_step ?? ""] ?? data.current_step ?? "-"} />
            <Metric size="sm" label="현재 에이전트" value={runningAgent?.agent_name ?? "-"} />
            <Metric size="sm" label="모델" value={runningAgent?.model ?? "-"} />
            <Metric size="sm" label="Provider" value={runningAgent?.provider ?? "-"} />
            <Metric size="sm" label="장면 진행" value={totalScenes ? `${doneScenes} / ${totalScenes}` : "-"} />
            <Metric size="sm" label="경과" value={elapsed(data.created_at)} />
          </div>
          <div className="mt-3 flex items-center gap-4 border-t border-hairline pt-3 text-caption text-ink-subtle">
            <span>
              비용 <span className="font-mono text-ink-muted">${data.cost_usd.toFixed(4)}</span> / 한도 $
              {data.budget.campaign}
            </span>
            {media && <span>미디어 비용 <span className="font-mono text-ink-muted">${media.cost_total?.toFixed(4)}</span></span>}
          </div>
        </CardBody>
      </Card>

      {/* pipeline */}
      <Card>
        <CardBody>
          <CardTitle>파이프라인</CardTitle>
          <div className="overflow-x-auto">
            <JobProgress steps={stages} />
          </div>
        </CardBody>
      </Card>

      {data.error_message && <ErrorState title="파이프라인 오류" detail={data.error_message} recovering />}

      {data.status === "SUCCESS" && (
        <div className="flex flex-wrap gap-2">
          <Link href={`/campaigns/${data.id}/media`} className="btn btn-primary">
            미디어 제작
            <Icon name="arrow-right" size={15} />
          </Link>
          <Link href={`/campaigns/${data.id}/studio`} className="btn btn-secondary">
            <Icon name="film" size={15} />
            영상 스튜디오
          </Link>
          <Link href={`/library/${data.id}`} className="btn btn-ghost">
            보관함에서 보기
          </Link>
        </div>
      )}

      {/* scenes */}
      {totalScenes > 0 && (
        <Card>
          <CardBody>
            <CardTitle sub={`${doneScenes} / ${totalScenes} 완료`}>장면</CardTitle>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {media!.scene_monitor.map((sc) => (
                <div key={sc.scene_id} className="rounded-md border border-hairline p-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-caption text-ink-tertiary">#{sc.order}</span>
                    <StatusBadge value={sc.status} size="sm" />
                  </div>
                  <p className="mt-1 line-clamp-2 text-caption text-ink-muted">{sc.narration}</p>
                  <p className="mt-1 text-[11px] text-ink-tertiary">
                    {sc.visual_type} · {sc.camera_motion} · {sc.duration}s
                  </p>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* success detail */}
      {data.status === "SUCCESS" && (
        <>
          {data.script && (
            <Card>
              <CardBody>
                <CardTitle sub={`${data.script.word_count} words · QA ${data.script.qa_passed ? "PASS" : "FAIL"}`}>
                  마스터 대본
                </CardTitle>
                {nat && (
                  <p className="mb-2 text-caption text-ink-tertiary">
                    AI slop {nat.ai_slop_before} → {nat.ai_slop_after} (목표 ≤ 20) · burstiness {nat.burstiness} · CTA{" "}
                    {data.script.cta_type}
                  </p>
                )}
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border border-hairline bg-surface-2 p-3 text-body-sm text-ink-muted">
                  {data.script.body}
                </pre>
              </CardBody>
            </Card>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardBody>
                <CardTitle sub={`fact score ${data.fact_score ?? "-"}`}>검증된 사실</CardTitle>
                <ul className="space-y-2">
                  {data.verified_facts.map((f, i) => (
                    <li key={i} className="text-body-sm">
                      <StatusBadge
                        value={f.status === "VERIFIED" ? "SUCCESS" : f.status === "PARTIALLY_VERIFIED" ? "RUNNING" : "FAILED"}
                        size="sm"
                      />{" "}
                      <span className="text-ink-muted">{f.fact}</span>
                      <span className="text-ink-tertiary"> — {f.reason}</span>
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>

            <Card>
              <CardBody>
                <CardTitle sub={`${data.sources.length}건`}>출처</CardTitle>
                <ul className="space-y-1.5 text-body-sm">
                  {data.sources.map((s) => (
                    <li key={s.id}>
                      <a className="text-primary hover:underline" href={s.url} target="_blank" rel="noreferrer">
                        {s.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardBody>
              <CardTitle>에이전트 로그</CardTitle>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-caption">
                  <thead className="text-ink-subtle">
                    <tr className="border-b border-hairline">
                      <th className="py-1.5 pr-2">에이전트</th>
                      <th className="py-1.5 pr-2">Provider</th>
                      <th className="py-1.5 pr-2 text-right">토큰(in/out)</th>
                      <th className="py-1.5 pr-2 text-right">비용</th>
                      <th className="py-1.5">상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.agent_runs.map((r, i) => (
                      <tr key={i} className="border-b border-hairline last:border-0">
                        <td className="py-1.5 pr-2 text-ink-muted">{r.agent_name}</td>
                        <td className="py-1.5 pr-2 text-ink-tertiary">{r.provider ?? "-"}</td>
                        <td className="py-1.5 pr-2 text-right font-mono tabular-nums">
                          {r.input_tokens}/{r.output_tokens}
                        </td>
                        <td className="py-1.5 pr-2 text-right font-mono tabular-nums">${r.estimated_cost.toFixed(4)}</td>
                        <td className="py-1.5">
                          <StatusBadge value={r.status} size="sm" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}
