"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getCampaign,
  govReviewQueue,
  listGovCases,
  listRights,
  policyStatus,
  reviewGovCase,
  type CampaignDetail,
  type GovCase,
  type PolicyStatusRow,
  type RightsRow,
} from "@/lib/api";
import { PageHeader, Card, CardBody, CardTitle, EmptyState, ErrorState, Metric, SkeletonText } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Icon } from "@/components/ui/Icon";
import { platformKo, statusMeta } from "@/lib/status";

export default function ReviewCenter() {
  const [wsId, setWsId] = useState("");
  const [queue, setQueue] = useState<GovCase[] | null>(null);
  const [recent, setRecent] = useState<GovCase[]>([]);
  const [policy, setPolicy] = useState<PolicyStatusRow[]>([]);
  const [sel, setSel] = useState<GovCase | null>(null);
  const [campaign, setCampaign] = useState<CampaignDetail | null>(null);
  const [rights, setRights] = useState<RightsRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    try {
      setWsId(window.localStorage.getItem("acf_workspace_id") ?? "");
    } catch {
      /* ignore */
    }
  }, []);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [q, c, p] = await Promise.all([
        govReviewQueue(wsId || undefined),
        listGovCases(wsId || undefined),
        policyStatus(),
      ]);
      setQueue(q);
      setRecent(c);
      setPolicy(p);
      setSel((cur) => cur ?? q[0] ?? null);
    } catch (e) {
      setErr(String(e));
      setQueue([]);
    }
  }, [wsId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!sel) {
      setCampaign(null);
      setRights([]);
      return;
    }
    setCampaign(null);
    getCampaign(sel.campaign_id).then(setCampaign).catch(() => setCampaign(null));
    listRights(sel.campaign_id).then(setRights).catch(() => setRights([]));
  }, [sel]);

  const decide = async (approve: boolean) => {
    if (!sel) return;
    setBusy(true);
    try {
      await reviewGovCase(sel.id, approve, note);
      setToast(approve ? "승인 처리했습니다." : "수정 요청을 보냈습니다.");
      setNote("");
      setSel(null);
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
      setTimeout(() => setToast(null), 2500);
    }
  };

  const counts = recent.reduce<Record<string, number>>((a, c) => {
    a[c.state] = (a[c.state] ?? 0) + 1;
    return a;
  }, {});
  const d = (sel?.detail ?? {}) as Record<string, unknown>;

  return (
    <div className="space-y-5">
      <PageHeader
        title="검수 센터"
        eyebrow="검수"
        description="게시 전 권리·정책·독창성·AI 표기·주장 근거를 확인하고 승인합니다."
        actions={
          <button className="btn btn-secondary" onClick={load}>
            <Icon name="refresh" size={15} />
            새로고침
          </button>
        }
      />

      {toast && (
        <div role="status" aria-live="polite" className="rounded-md border border-hairline bg-surface-2 px-3 py-2 text-body-sm text-success">
          {toast}
        </div>
      )}
      {err && (
        <div role="alert" aria-live="polite">
          <ErrorState detail={err} onRetry={load} />
        </div>
      )}

      {/* summary - only when there is anything to summarise */}
      {recent.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {["PASS", "PASS_WITH_REQUIREMENTS", "FIX_REQUIRED", "HUMAN_REVIEW", "BLOCKED"].map((s) => (
            <Card key={s}>
              <CardBody className="!p-3.5">
                <Metric size="sm" label={statusMeta(s).ko} value={counts[s] ?? 0} />
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        {/* queue list */}
        <Card className="lg:sticky lg:top-[76px] lg:self-start">
          <CardBody className="!p-3">
            <CardTitle sub={queue ? `${queue.length}건` : undefined}>검토 대기</CardTitle>
            {queue === null ? (
              <SkeletonText lines={4} />
            ) : queue.length === 0 ? (
              <p className="py-6 text-center text-body-sm text-ink-subtle">검토가 필요한 항목이 없습니다.</p>
            ) : (
              <ul className="space-y-1">
                {queue.map((c) => (
                  <li key={c.id}>
                    <button
                      onClick={() => setSel(c)}
                      className={`w-full rounded-md border px-3 py-2 text-left ${
                        sel?.id === c.id ? "border-primary bg-primary/10" : "border-hairline hover:bg-surface-2"
                      }`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-caption text-ink-muted">{c.case_type}</span>
                        {c.hard_block && <Icon name="lock" size={12} className="text-ink" />}
                      </span>
                      <span className="mt-1 flex items-center gap-1.5">
                        <StatusBadge value={c.state} size="sm" />
                        <span className="text-caption text-ink-tertiary">{statusMeta(c.severity).ko}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        {/* detail */}
        <div className="space-y-4">
          {!sel ? (
            <EmptyState icon="shield" title="검토할 항목을 선택하세요" body="왼쪽 목록에서 항목을 고르면 상세 정보가 표시됩니다." />
          ) : (
            <>
              {/* preview */}
              <Card>
                <CardBody>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="t-eyebrow">{sel.case_type}</p>
                      <h2 className="mt-0.5 font-display text-[20px] font-semibold tracking-[-0.4px] text-ink">
                        {campaign?.topic ?? sel.campaign_id.slice(0, 8)}
                      </h2>
                      <p className="mt-1 font-mono text-caption text-ink-tertiary">캠페인 {sel.campaign_id.slice(0, 8)}</p>
                    </div>
                    <StatusBadge value={sel.state} />
                  </div>

                  <div className="mt-4 rounded-lg border border-hairline bg-surface-2 p-4">
                    {campaign === null ? (
                      <SkeletonText lines={3} />
                    ) : campaign?.script?.body ? (
                      <p className="line-clamp-6 whitespace-pre-wrap text-body-sm text-ink-muted">{campaign.script.body}</p>
                    ) : (
                      <p className="text-body-sm text-ink-subtle">연결된 대본 미리보기가 없습니다.</p>
                    )}
                  </div>
                </CardBody>
              </Card>

              {/* inspector */}
              <div className="grid gap-4 md:grid-cols-2">
                <Card>
                  <CardBody>
                    <CardTitle>거버넌스 판정</CardTitle>
                    <dl>
                      <div className="kv"><dt>사유 코드</dt><dd className="font-mono text-[12px]">{sel.reason_codes.join(", ") || "-"}</dd></div>
                      <div className="kv"><dt>심각도</dt><dd>{statusMeta(sel.severity).ko}</dd></div>
                      <div className="kv"><dt>강제 차단</dt><dd>{sel.hard_block ? "예 (재정의 불가)" : "아니오"}</dd></div>
                      <div className="kv"><dt>결정</dt><dd>{sel.decision || "-"}</dd></div>
                    </dl>
                  </CardBody>
                </Card>

                <Card>
                  <CardBody>
                    <CardTitle sub={`${rights.length}건`}>권리 · 라이선스</CardTitle>
                    {rights.length === 0 ? (
                      <p className="py-3 text-body-sm text-ink-subtle">등록된 권리 정보가 없습니다.</p>
                    ) : (
                      <ul className="space-y-2 text-body-sm">
                        {rights.slice(0, 5).map((r) => (
                          <li key={r.id} className="flex items-center justify-between gap-2">
                            <span className="truncate text-ink-muted">{r.source_type} · {r.license_type}</span>
                            <StatusBadge value={r.rights_status === "CLEARED" ? "OK" : r.rights_status} size="sm" />
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardBody>
                </Card>

                <Card>
                  <CardBody>
                    <CardTitle>AI 표기 · 주장</CardTitle>
                    <dl>
                      <div className="kv"><dt>AI 생성 표기</dt><dd>{String(d.ai_disclosure ?? d.disclosure ?? "확인 필요")}</dd></div>
                      <div className="kv"><dt>주장 근거</dt><dd>{String(d.claims_status ?? d.claims ?? "-")}</dd></div>
                      <div className="kv"><dt>독창성</dt><dd>{String(d.originality ?? d.originality_score ?? "-")}</dd></div>
                    </dl>
                  </CardBody>
                </Card>

                <Card>
                  <CardBody>
                    <CardTitle>비용 · 경고</CardTitle>
                    <dl>
                      <div className="kv"><dt>예상 비용</dt><dd>{campaign ? `$${campaign.cost_usd.toFixed(4)}` : "-"}</dd></div>
                      <div className="kv"><dt>플랫폼</dt><dd>{campaign?.platforms.join(", ") || "-"}</dd></div>
                    </dl>
                    {Array.isArray(d.warnings) && (d.warnings as unknown[]).length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {(d.warnings as string[]).map((w, i) => (
                          <li key={i} className="flex items-start gap-1.5 text-caption text-brand-secure">
                            <Icon name="alert" size={12} className="mt-0.5 flex-shrink-0" />
                            {w}
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardBody>
                </Card>
              </div>

              {/* actions - approve is deliberately separated from any publish action */}
              <Card>
                <CardBody>
                  <label htmlFor="review-note" className="text-caption font-medium text-ink-subtle">
                    검토 의견 (선택)
                  </label>
                  <textarea
                    id="review-note"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={2}
                    placeholder="수정이 필요한 부분이나 승인 근거를 남기세요."
                    className="input mt-1.5 resize-none"
                  />
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button className="btn btn-secondary" disabled={busy} onClick={() => decide(false)}>
                      <Icon name="edit" size={15} />
                      수정 요청
                    </button>
                    <button className="btn btn-ghost" disabled={busy} onClick={() => setSel(null)}>
                      <Icon name="pause" size={15} />
                      보류
                    </button>
                    <div className="ml-auto flex items-center gap-2">
                      {sel.hard_block ? (
                        <span className="chip text-ink">
                          <Icon name="lock" size={12} />
                          재정의 불가 (승인 불가)
                        </span>
                      ) : (
                        <button className="btn btn-primary" disabled={busy} onClick={() => decide(true)}>
                          <Icon name="check" size={15} />
                          승인
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="mt-2 text-caption text-ink-tertiary">
                    승인은 게시를 실행하지 않습니다. 게시는 게시 센터에서 별도로 진행합니다.
                  </p>
                </CardBody>
              </Card>
            </>
          )}

          {/* platform publish rules - secondary */}
          <Card>
            <CardBody>
              <CardTitle sub="플랫폼별 게시 정책 규칙 수">플랫폼 정책</CardTitle>
              <div className="flex flex-wrap gap-1.5">
                {policy.map((p) => (
                  <span
                    key={p.platform}
                    className={`chip ${p.stale ? "text-brand-secure" : "text-ink-muted"}`}
                  >
                    {platformKo(p.platform)} · 규칙 {p.rules}개
                    {p.stale ? " · 갱신 필요" : ""}
                    {p.unknown_rules > 0 ? ` · 미확인 ${p.unknown_rules}` : ""}
                  </span>
                ))}
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
