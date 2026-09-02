"use client";

import { useCallback, useEffect, useState } from "react";
import { supportSnapshot, supportSnapshotText, toggleKillSwitch, type SupportSnapshot } from "@/lib/api";
import { Card, CardBody, CardTitle, ErrorState, Skeleton, SkeletonText } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { JobProgress, PIPELINE_STAGES, type JobStep } from "@/components/ui/JobProgress";
import { Icon } from "@/components/ui/Icon";
import { statusMeta, TONE_DOT, TONE_TEXT } from "@/lib/status";

function Row({ k, v, mono }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return (
    <div className="kv">
      <dt>{k}</dt>
      <dd className={mono ? "font-mono text-[12px]" : ""}>{v ?? "-"}</dd>
    </div>
  );
}

const PROVIDER_KO: Record<string, string> = {
  anthropic: "Anthropic (LLM)", tavily: "Tavily (검색)", google: "Google AI (이미지/영상)",
  elevenlabs: "ElevenLabs (음성)", ollama: "Ollama (로컬)",
};

export default function SupportSnapshotPage() {
  const [snap, setSnap] = useState<SupportSnapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [capture, setCapture] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setErr(null);
    supportSnapshot().then(setSnap).catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    document.body.classList.toggle("capture-mode", capture);
    return () => document.body.classList.remove("capture-mode");
  }, [capture]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(await supportSnapshotText());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      setErr(`복사 실패: ${e}`);
    }
  };

  const flip = async (flag: string, on: boolean) => {
    if (on && !confirm(`${flag} 을(를) 켤까요? 관련 작업이 즉시 중단됩니다.`)) return;
    setBusy(true);
    try {
      await toggleKillSwitch(flag, on);
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (err && !snap) return <ErrorState title="스냅샷을 불러오지 못했습니다" detail={err} onRetry={load} />;
  if (!snap)
    return (
      <div className="space-y-4">
        <Card lift>
          <CardBody>
            <div className="flex items-center gap-3">
              <Skeleton className="h-10 w-10 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-5 w-48" />
                <Skeleton className="h-3 w-72" />
              </div>
            </div>
          </CardBody>
        </Card>
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardBody>
                <Skeleton className="mb-3 h-4 w-24" />
                <SkeletonText lines={5} />
              </CardBody>
            </Card>
          ))}
        </div>
      </div>
    );

  const s = snap;
  const sys = s.system;
  const job = (s.current_jobs?.[0] as Record<string, unknown>) || {};
  const hasJob = s.current_jobs.length > 0;
  const route = s.model_routing?.last_route as Record<string, unknown> | null;
  const e = s.last_error as Record<string, unknown> | null;
  const cost = s.cost as Record<string, unknown>;
  const hm = statusMeta(s.overall_health);

  const providers =
    ((sys.cloud_providers as { providers?: Array<{ provider: string; status: string }> })?.providers ?? []);

  const sysRows: Array<[string, unknown]> = [
    ["Backend", sys.backend?.status],
    ["Database", sys.database?.status],
    ["Redis", sys.redis?.status],
    ["Workers / Scheduler", sys.workers?.status],
    ["Storage", sys.storage?.status],
    ["FFmpeg", sys.ffmpeg?.status],
    ["Ollama", sys.ollama?.status],
    ["로컬 모델", (sys.ollama as Record<string, unknown>)?.model_available ? "READY" : "NOT_CONFIGURED"],
    ...providers.map((p) => [PROVIDER_KO[p.provider] ?? p.provider, p.status] as [string, unknown]),
    ["게시 연동", (sys.publishers as Record<string, unknown>)?.status],
  ];

  const pipeline: JobStep[] = PIPELINE_STAGES.map((st) => {
    const p = s.pipeline?.find((x) => x.step.toLowerCase().includes(st.key));
    return { key: st.key, label: st.label, state: p?.state ?? "WAITING" };
  });

  return (
    <div className="space-y-4">
      {/* ---------------------------------------------------------- health hero */}
      <Card lift>
        <CardBody>
          <div className="flex flex-wrap items-center gap-3">
            <span className={`flex h-10 w-10 items-center justify-center rounded-full border ${
              hm.tone === "ok" ? "border-success/40" : "border-hairline-strong"
            } ${TONE_TEXT[hm.tone]}`}>
              <Icon name={hm.icon} size={20} />
            </span>
            <div>
              <h1 className="font-display text-[22px] font-semibold tracking-[-0.5px] text-ink">
                시스템 상태: <span className={TONE_TEXT[hm.tone]}>{hm.ko}</span>
              </h1>
              <p className="font-mono text-caption text-ink-tertiary">
                {s.product} · {s.version} · {s.environment} · {s.generated_at}
              </p>
            </div>
            <div className="ml-auto flex gap-2 capture-hide">
              <button className="btn btn-secondary" onClick={() => setCapture((v) => !v)}>
                <Icon name="eye" size={15} />
                {capture ? "캡처 모드 끄기" : "캡처 모드"}
              </button>
              <button className="btn btn-primary" onClick={copy}>
                <Icon name="copy" size={15} />
                {copied ? "복사됨" : "지원 정보 복사"}
              </button>
            </div>
          </div>
          <p className="mt-3 text-caption text-ink-subtle">
            이 화면을 캡처하거나 <b>[지원 정보 복사]</b>로 텍스트를 복사해 관리자에게 전달하세요.
            비밀키·토큰·비밀번호는 포함되지 않습니다.
          </p>
        </CardBody>
      </Card>

      {/* ---------------------------------------------------------- last error */}
      {e && (
        <Card>
          <CardBody>
            <CardTitle>마지막 오류</CardTitle>
            <div className="grid gap-4 md:grid-cols-[1fr_1fr]">
              <dl>
                <Row k="시각" v={String(e.timestamp ?? "-")} />
                <Row k="오류 코드" v={<span className="text-ink">{String(e.error_code)}</span>} mono />
                <Row k="클래스 / 서비스" v={`${e.error_class ?? "-"} / ${e.service ?? "-"}`} mono />
                <Row k="재시도 가능" v={String(e.retryable)} />
                <Row k="Trace ID" v={<span className="text-ink">{String(e.trace_id ?? "-")}</span>} mono />
              </dl>
              <div className="rounded-lg border border-hairline-strong bg-surface-2 p-3">
                <p className="text-caption font-medium text-ink-subtle">권장 조치</p>
                <p className="mt-1 text-body-sm text-ink">{String(e.suggested_action ?? "관리자에게 문의하세요.")}</p>
                {e.message ? (
                  <p className="mt-2 break-words font-mono text-[12px] text-ink-tertiary">{String(e.message)}</p>
                ) : null}
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {/* ---------------------------------------------------------- current job */}
      <Card>
        <CardBody>
          <CardTitle sub={hasJob ? String(job.topic ?? "") : undefined}>현재 작업 · 파이프라인</CardTitle>
          {!hasJob ? (
            <p className="py-4 text-body-sm text-ink-subtle">진행 중인 캠페인이 없습니다.</p>
          ) : (
            <div className="space-y-4">
              <dl className="grid grid-cols-2 gap-x-4 sm:grid-cols-3">
                <Row k="Campaign" v={String(job.campaign_id ?? "-")} mono />
                <Row k="모드" v={String(job.execution_mode ?? "-")} />
                <Row k="단계" v={String(job.current_stage ?? "-")} />
                <Row k="경과(초)" v={String(job.elapsed_s ?? "-")} />
              </dl>
              <div className="overflow-x-auto">
                <JobProgress steps={pipeline} />
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {/* system */}
        <Card>
          <CardBody>
            <CardTitle>시스템</CardTitle>
            <dl>
              {sysRows.map(([k, v]) => {
                const m = statusMeta(String(v ?? ""));
                return (
                  <div key={k} className="kv">
                    <dt>{k}</dt>
                    <dd className="flex items-center gap-1.5">
                      <span className={`h-2 w-2 rounded-full ${TONE_DOT[m.tone]}`} />
                      <span className={TONE_TEXT[m.tone]}>{String(v ?? "-")}</span>
                    </dd>
                  </div>
                );
              })}
            </dl>
          </CardBody>
        </Card>

        {/* model routing */}
        <Card>
          <CardBody>
            <CardTitle>모델 라우팅</CardTitle>
            <dl>
              <Row k="LOCAL_ONLY" v={String(s.model_routing.local_only)} />
              <Row k="Cloud Fallback" v={String(s.model_routing.cloud_fallback_enabled)} />
              {route ? (
                <>
                  <Row k="Agent" v={String(route.agent ?? "-")} />
                  <Row k="Task" v={String(route.task_type ?? "-")} />
                  <Row k="Provider / Model" v={`${route.provider} / ${route.model}`} mono />
                  <Row k="Tier" v={String(route.tier ?? "-")} />
                  <Row k="Fallback 사용" v={String(route.fallback_used)} />
                  <Row k="PromptComposer" v={String(route.prompt_composer_used)} />
                </>
              ) : (
                <Row k="최근 라우팅" v="없음" />
              )}
            </dl>
          </CardBody>
        </Card>

        {/* workers / queues */}
        <Card>
          <CardBody>
            <CardTitle>작업자 · 큐</CardTitle>
            <dl>
              {Object.entries(s.workers_queues)
                .filter(([k]) => k !== "queue_depths")
                .map(([k, v]) => (
                  <Row key={k} k={k} v={typeof v === "object" ? JSON.stringify(v) : String(v)} />
                ))}
            </dl>
          </CardBody>
        </Card>

        {/* governance / platform / cost */}
        <Card>
          <CardBody>
            <CardTitle>거버넌스 · 플랫폼 · 비용</CardTitle>
            <dl>
              <Row k="거버넌스 상태" v={String((s.governance as Record<string, unknown>)?.state ?? "-")} />
              <Row k="예상 비용" v={String(cost.estimated_usd ?? "UNKNOWN")} />
              <Row k="실제 비용" v={String(cost.actual_usd ?? "0")} />
              <Row k="예산" v={String(cost.budget_usd ?? "-")} />
            </dl>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {s.platform_selection.map((p) => (
                <span key={p.platform + p.content_type} className={`chip ${TONE_TEXT[statusMeta(p.mode).tone]}`}>
                  {p.platform}: {statusMeta(p.mode).ko}
                </span>
              ))}
            </div>
          </CardBody>
        </Card>

        {/* recent events */}
        <Card className="md:col-span-2">
          <CardBody>
            <CardTitle>최근 이벤트</CardTitle>
            {s.recent_events.length === 0 ? (
              <p className="py-3 text-body-sm text-ink-subtle">이벤트 없음.</p>
            ) : (
              <ul className="space-y-1 text-caption">
                {s.recent_events.map((ev, i) => (
                  <li key={i} className="flex justify-between gap-2">
                    <span className="font-mono text-ink-tertiary">{ev.at}</span>
                    <span className="text-ink-muted">{ev.event}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      {/* ---------------------------------------------------------- kill switches */}
      <Card className="capture-hide">
        <CardBody>
          <CardTitle>긴급 제어 (Kill Switch)</CardTitle>
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(s.kill_switches).map(([flag, on]) => {
              const toggleable = ["global_publish_pause", "global_paid_provider_pause", "safe_mode", "maintenance_mode"].includes(flag);
              return (
                <div key={flag} className="flex items-center justify-between rounded-md border border-hairline px-3 py-2">
                  <span className="text-body-sm text-ink-muted">
                    {flag} {on && <b className="text-ink">· ON</b>}
                  </span>
                  {toggleable && (
                    <button className="btn btn-secondary !py-1 !text-caption" disabled={busy} onClick={() => flip(flag.toUpperCase(), !on)}>
                      {on ? "해제" : "켜기"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </CardBody>
      </Card>

      {s.test && (
        <p className="text-caption text-ink-tertiary capture-hide">
          migration head: <span className="font-mono">{String(s.test.migration_head)}</span> · scope: {s.scope}
        </p>
      )}
      {err && <p className="text-caption text-brand-secure">{err}</p>}
    </div>
  );
}
