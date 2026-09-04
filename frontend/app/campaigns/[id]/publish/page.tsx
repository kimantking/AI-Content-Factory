"use client";

import { use, useCallback, useEffect, useState } from "react";
import {
  PublishJobRow,
  approvePublishJob,
  createPublishJobs,
  getPublishingDashboard,
  runPublishJob,
} from "@/lib/api";

const BADGE: Record<string, string> = {
  PUBLISHED: "bg-surface-2 text-success",
  READY: "bg-surface-2 text-primary",
  SCHEDULED: "bg-surface-2 text-primary",
  QUEUED: "bg-surface-2 text-brand-secure",
  PROCESSING: "bg-surface-2 text-brand-secure",
  VERIFYING: "bg-surface-2 text-brand-secure",
  RETRY: "bg-surface-2 text-brand-secure",
  FAILED: "bg-surface-2 text-brand-secure",
  BLOCKED: "bg-surface-2 text-brand-secure",
  REAUTH_REQUIRED: "bg-surface-2 text-brand-secure",
  WAITING_APPROVAL: "bg-surface-2 text-brand-secure",
  WAITING_USER_ACTION: "bg-surface-3 text-ink-muted",
  WAITING_PLATFORM_ACTION: "bg-surface-2 text-brand-secure",
  NOT_SUPPORTED: "bg-surface-3 text-ink-subtle",
  DRAFT: "bg-surface-2 text-ink-subtle",
};
const STATUS_KO: Record<string, string> = {
  PUBLISHED: "게시 완료", READY: "게시 준비", SCHEDULED: "예약됨", QUEUED: "대기 중",
  PROCESSING: "처리 중", VERIFYING: "확인 중", RETRY: "재시도 대기", FAILED: "실패",
  BLOCKED: "차단됨", REAUTH_REQUIRED: "다시 로그인 필요", WAITING_APPROVAL: "승인 대기",
  WAITING_USER_ACTION: "사용자 확인 필요", WAITING_PLATFORM_ACTION: "SNS 처리 대기",
  NOT_SUPPORTED: "자동 게시 미지원", DRAFT: "초안",
};
const Badge = ({ s }: { s: string }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[s] ?? BADGE.DRAFT}`}>
    {STATUS_KO[s] ?? s}
  </span>
);

export default function PublishPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [jobs, setJobs] = useState<PublishJobRow[]>([]);
  const [rollup, setRollup] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [mode, setMode] = useState("MANUAL");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await getPublishingDashboard(id);
      setJobs(d.jobs);
      setRollup(d.rollup);
      setDryRun(d.dry_run);
      setMode(d.publish_mode);
    } catch (e) {
      setErr(String(e));
    }
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);

  async function onCreate() {
    setBusy(true);
    try {
      await createPublishJobs(id, { run_mode: mode });
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="space-y-6">
      <div className="flex items-center justify-between">
        <a href={`/campaigns/${id}/media`} className="text-sm text-primary underline">
          ← 영상 확인
        </a>
        <a href="/publishing" className="text-sm text-primary underline">
          SNS 계정 연결 →
        </a>
      </div>

      <div className="rounded-md border border-hairline bg-surface-1 p-4">
        <p className="text-sm font-semibold">게시 준비</p>
        <p className="mt-1 text-xs text-subtle">
          전체 상태: <b>{STATUS_KO[rollup] ?? (rollup || "-")}</b> · 게시 방식: {mode === "MANUAL" ? "직접 확인" : mode} ·{" "}
          {dryRun ? (
            <span className="font-bold text-brand-secure">테스트 모드 · 실제 SNS에는 게시되지 않습니다</span>
          ) : (
            <span className="text-success">실제 게시 모드</span>
          )}
        </p>
        <button
          type="button"
          onClick={onCreate}
          disabled={busy}
          className="mt-3 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-on-primary disabled:opacity-50"
        >
          SNS별 게시 준비하기
        </button>
      </div>

      {err && <p className="text-sm text-brand-secure">{err}</p>}

      <div className="space-y-2">
        {jobs.map((jb) => (
          <section key={jb.id} className="rounded-md border border-hairline bg-surface-1 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{jb.platform}</span>
              <Badge s={jb.status} />
              <span className="text-xs text-subtle">{jb.content_type}</span>
              {jb.dry_run && <span className="text-[11px] font-bold text-brand-secure">테스트</span>}
              {jb.dead_lettered && <span className="text-[11px] font-bold text-brand-secure">오류 보관함</span>}
              <span className="ml-auto text-xs text-subtle">
                {jb.scheduled_at ? `${jb.scheduled_at} (${jb.timezone})` : "바로 게시"}
              </span>
            </div>
            <p className="mt-1 truncate text-xs text-subtle">{jb.title}</p>
            {jb.remote_url && (
              <a href={jb.remote_url} className="text-xs text-primary underline" target="_blank" rel="noreferrer">
                {jb.remote_url}
              </a>
            )}
            {jb.last_error_type && (
              <p className="text-xs text-brand-secure">오류: {jb.last_error_type}</p>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              {jb.approval_status !== "APPROVED" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => act(() => approvePublishJob(jb.id))}
                  className="rounded border border-hairline px-3 py-1 text-xs"
                >
                  게시 승인하기
                </button>
              )}
              <button
                type="button"
                disabled={busy}
                onClick={() => act(() => runPublishJob(jb.id))}
                className="rounded border border-hairline px-3 py-1 text-xs"
              >
                {dryRun ? "테스트 실행" : "지금 게시하기"}
              </button>
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
