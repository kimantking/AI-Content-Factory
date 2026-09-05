"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { cancelCampaign, deleteCampaign, listCampaigns, type CampaignSummary } from "@/lib/api";
import { Card, CardBody, EmptyState, ErrorState, PageHeader } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/Icon";
import { StatusBadge } from "@/components/ui/StatusBadge";

const STEPS = ["create_campaign", "research", "fact_check", "strategize", "hook", "write_script", "qa_script", "persist"];
const STEP_KO: Record<string, string> = {
  create_campaign: "준비", research: "리서치", research_fix: "리서치 보강",
  fact_check: "팩트체크", strategize: "전략", hook: "훅",
  write_script: "대본", qa_script: "대본 검수", persist: "제작 준비",
};

function progress(job: CampaignSummary) {
  if (["SUCCESS", "COMPLETE", "DONE"].includes(job.status)) return 100;
  const idx = STEPS.indexOf(job.current_step ?? "");
  if (idx < 0) return job.status === "WAITING" ? 0 : 5;
  return Math.min(95, Math.round(((idx + (job.status === "RUNNING" ? 0.5 : 0)) / STEPS.length) * 100));
}

function JobCard({ job, busy, onCancel, onDelete }: {
  job: CampaignSummary; busy: boolean;
  onCancel: (job: CampaignSummary) => void; onDelete: (job: CampaignSummary) => void;
}) {
  const pct = progress(job);
  const active = job.status === "RUNNING" || job.status === "WAITING";
  return (
    <Card className={active ? "border-primary/30" : ""}>
      <CardBody className="space-y-3">
        <div className="flex items-start gap-3">
          <span className={`mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-full ${active ? "bg-primary/10 text-primary" : "bg-surface-2 text-ink-subtle"}`}>
            <Icon name={active ? "activity" : job.status === "FAILED" ? "alert" : "check"} size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-ink">{job.topic || "제목 없는 작업"}</p>
            <p className="mt-0.5 text-caption text-ink-subtle">
              {STEP_KO[job.current_step ?? ""] ?? job.current_step ?? "대기"} · {job.created_at?.slice(0, 16).replace("T", " ")}
            </p>
          </div>
          <StatusBadge value={job.status} size="sm" />
        </div>
        <div>
          <div className="mb-1 flex justify-between text-caption">
            <span className={active ? "text-primary" : "text-ink-subtle"}>{active ? "실제 작업 처리 중" : "전체 단계 진행률"}</span>
            <strong className="font-mono text-ink">{pct}%</strong>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-3">
            <div className={`h-full rounded-full bg-primary transition-all ${active ? "animate-pulse" : ""}`} style={{ width: `${pct}%` }} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Link href={`/campaigns/${job.id}`} className="btn btn-secondary col-span-2 justify-center">
            진행 화면 다시 열기 <Icon name="arrow-right" size={15} />
          </Link>
          {active && <button className="btn btn-secondary justify-center" disabled={busy} onClick={() => onCancel(job)}>
            {busy ? "처리 중…" : "작업 중지"}
          </button>}
          <button className={`btn btn-secondary justify-center text-danger ${active ? "" : "col-span-2"}`} disabled={busy} onClick={() => onDelete(job)}>
            {busy ? "처리 중…" : "완전히 삭제"}
          </button>
        </div>
      </CardBody>
    </Card>
  );
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<CampaignSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const load = useCallback(() => {
    listCampaigns(50).then((rows) => { setJobs(rows); setError(null); }).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [load]);
  const active = useMemo(() => jobs.filter((j) => j.status === "RUNNING" || j.status === "WAITING"), [jobs]);
  const visible = showAll ? jobs : active;
  const stop = async (job: CampaignSummary) => {
    if (!window.confirm(`“${job.topic}” 작업을 중지할까요?\n만들어진 중간 결과는 남아 있습니다.`)) return;
    setBusyId(job.id); setError(null);
    try { await cancelCampaign(job.id); await load(); } catch (e) { setError(String(e)); }
    finally { setBusyId(null); }
  };
  const remove = async (job: CampaignSummary) => {
    if (!window.confirm(`“${job.topic}” 작업과 생성 파일을 완전히 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`)) return;
    setBusyId(job.id); setError(null);
    try { await deleteCampaign(job.id); await load(); } catch (e) { setError(String(e)); }
    finally { setBusyId(null); }
  };

  return (
    <div className="space-y-5">
      <PageHeader title="진행 중인 작업" eyebrow="작업 관리" description={`현재 ${active.length}건 처리 중 · 5초마다 자동 갱신`} actions={
        <button className="btn btn-secondary" onClick={() => setShowAll((v) => !v)}>{showAll ? "진행 중만 보기" : "최근 작업 전체"}</button>
      } />
      {error ? <ErrorState detail={error} onRetry={load} /> : loading ? (
        <p className="py-12 text-center text-body-sm text-ink-subtle">작업을 불러오는 중…</p>
      ) : visible.length === 0 ? (
        <EmptyState icon="activity" title={showAll ? "최근 작업이 없습니다" : "진행 중인 작업이 없습니다"} body="새 콘텐츠를 만들거나 최근 작업 전체를 확인하세요." action={<Link href="/create" className="btn btn-primary">콘텐츠 만들기</Link>} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{visible.map((job) => <JobCard key={job.id} job={job} busy={busyId === job.id} onCancel={stop} onDelete={remove} />)}</div>
      )}
    </div>
  );
}
