"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  composeCampaign,
  contentLibrary,
  estimateCost,
  getAnalyticsOverview,
  getAutopilotStatus,
  getConfig,
  govReviewQueue,
  supportSnapshot,
  type AutopilotStatus,
  type GovCase,
  type LibraryCard,
  type SupportSnapshot,
} from "@/lib/api";
import { Card, CardBody, CardTitle, EmptyState, Metric, SkeletonText } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { JobProgress, PIPELINE_STAGES, type JobStep } from "@/components/ui/JobProgress";
import { Icon } from "@/components/ui/Icon";
import { OfficeStage } from "@/components/office/OfficeStage";

const FALLBACK_PLATFORMS = [
  "YouTube", "YouTube Shorts", "TikTok", "Instagram", "Facebook",
  "Threads", "X", "Pinterest", "LinkedIn", "Naver Blog", "Naver Clip",
];
const MODES = [
  { id: "FULL_AUTO", label: "완전 자동", hint: "리서치부터 게시 준비까지 자동" },
  { id: "GUIDED", label: "가이드", hint: "단계별로 확인하며 진행" },
  { id: "LEARN_ONLY", label: "학습 전용", hint: "제작 없이 자료 학습만" },
  { id: "DRAFT_ONLY", label: "초안까지", hint: "대본까지만, 미디어 제외" },
];
const QUALITY = [
  { id: "draft", label: "빠르게" },
  { id: "standard", label: "표준" },
  { id: "premium", label: "고품질" },
];
const GOAL_KO: Record<string, string> = {
  Views: "조회수", Followers: "팔로워", Revenue: "수익", Profit: "순이익", Brand: "브랜드", Balanced: "균형",
};
const PLATFORM_SELECTION: Record<string, [string, string]> = {
  YouTube: ["youtube_long", "LONG_VIDEO"],
  "YouTube Shorts": ["youtube_shorts", "SHORT_VIDEO"],
  TikTok: ["tiktok", "VIDEO"], Instagram: ["instagram_reel", "REELS"],
  Facebook: ["facebook_reel", "REELS"], Threads: ["threads", "THREAD"],
  X: ["x", "POST"], Pinterest: ["pinterest", "VIDEO_PIN"],
  LinkedIn: ["linkedin", "VIDEO"], "Naver Blog": ["naver_blog", "ARTICLE"],
  "Naver Clip": ["naver_clip", "CLIP"],
};

function buildPlatformSelection(platforms: string[], mode: string) {
  const out: Record<string, Record<string, string>> = {};
  const publishMode = mode === "GUIDED" || mode === "DRAFT_ONLY"
    ? "GENERATE_ONLY" : "GENERATE_AND_PUBLISH";
  for (const platform of platforms) {
    const mapped = PLATFORM_SELECTION[platform];
    if (mapped) out[mapped[0]] = { [mapped[1]]: publishMode };
  }
  return out;
}

function stageState(snap: SupportSnapshot | null, key: string): string {
  const p = snap?.pipeline?.find((s) => s.step.toLowerCase().includes(key));
  return p?.state ?? "WAITING";
}

export default function Home() {
  const router = useRouter();

  // composer
  const [topic, setTopic] = useState("");
  const [wsId, setWsId] = useState("");
  const [platforms, setPlatforms] = useState<string[]>(["YouTube"]);
  const [goal, setGoal] = useState("Balanced");
  const [mode, setMode] = useState("FULL_AUTO");
  const [quality, setQuality] = useState("standard");
  const [refUrl, setRefUrl] = useState("");
  const [refs, setRefs] = useState<string[]>([]);
  const [advanced, setAdvanced] = useState(false);
  const [opts, setOpts] = useState<{ platforms: string[]; goals: string[] }>({
    platforms: FALLBACK_PLATFORMS,
    goals: Object.keys(GOAL_KO),
  });
  const [modeLabel, setModeLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [estUsd, setEstUsd] = useState<number | null>(null);
  const [estUnknown, setEstUnknown] = useState(false);

  // dashboard data
  const [snap, setSnap] = useState<SupportSnapshot | null>(null);
  const [queue, setQueue] = useState<GovCase[] | null>(null);
  const [recent, setRecent] = useState<LibraryCard[] | null>(null);
  const [ana, setAna] = useState<Awaited<ReturnType<typeof getAnalyticsOverview>> | null>(null);
  const [auto, setAuto] = useState<AutopilotStatus | null>(null);

  useEffect(() => {
    setWsId(window.localStorage?.getItem("acf_workspace_id") ?? "");
    getConfig()
      .then((c) => {
        setOpts({ platforms: c.platforms, goals: c.goals });
        setModeLabel(`${c.mode}${c.mock_mode ? " · MOCK MODE" : ""}`);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let alive = true;
    const load = () => {
      if (document.visibilityState === "hidden") return;
      supportSnapshot().then((d) => alive && setSnap(d)).catch(() => alive && setSnap(null));
      govReviewQueue().then((d) => alive && setQueue(d)).catch(() => alive && setQueue([]));
      contentLibrary({ page: "1", sort: "newest" }).then((d) => alive && setRecent(d.items.slice(0, 5))).catch(() => alive && setRecent([]));
      getAnalyticsOverview().then((d) => alive && setAna(d)).catch(() => undefined);
      getAutopilotStatus().then((d) => alive && setAuto(d)).catch(() => undefined);
    };
    load();
    const t = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  // cost preview (read-only)
  useEffect(() => {
    if (platforms.length === 0) {
      setEstUsd(null);
      return;
    }
    const sel = buildPlatformSelection(platforms, mode);
    const h = setTimeout(() => {
      setEstUsd(null);
      const timeout = new Promise<never>((_, rej) => setTimeout(() => rej(new Error("timeout")), 8000));
      Promise.race([
        estimateCost({ selection: sel, quality_preset: quality, execution_mode: mode, reference_count: refs.length }),
        timeout,
      ])
        .then((c) => {
          setEstUsd((c as Awaited<ReturnType<typeof estimateCost>>).total_known_usd ?? 0);
          setEstUnknown(!!(c as Awaited<ReturnType<typeof estimateCost>>).has_unknown);
        })
        .catch(() => {
          setEstUsd(-1); // sentinel: show "확인 불가"
          setEstUnknown(false);
        });
    }, 300);
    return () => clearTimeout(h);
  }, [platforms, quality, mode, refs.length]);

  function togglePlatform(p: string) {
    setPlatforms((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]));
  }
  function addRef() {
    const u = refUrl.trim();
    if (!u) return;
    if (!/^https?:\/\//i.test(u)) {
      setErr("참고자료는 http(s) 주소여야 합니다.");
      return;
    }
    setRefs((r) => Array.from(new Set([...r, u])));
    setRefUrl("");
    setErr(null);
  }

  async function start() {
    if (mode !== "LEARN_ONLY" && topic.trim().length < 2) {
      setErr("콘텐츠 주제를 두 글자 이상 입력해 주세요.");
      return;
    }
    if (mode === "LEARN_ONLY" && refs.length === 0) {
      setErr("학습할 참고자료 URL을 하나 이상 추가해 주세요.");
      return;
    }
    if (mode !== "LEARN_ONLY" && platforms.length === 0) {
      setErr("콘텐츠를 만들 SNS를 하나 이상 선택해 주세요.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await composeCampaign({
        topic: topic.trim() || undefined,
        execution_mode: mode === "LEARN_ONLY" ? "LEARN_ONLY"
          : mode === "DRAFT_ONLY" ? "CREATE_ONLY" : "CREATE_AND_LEARN",
        reference_urls: refs.length ? refs : undefined,
        audience_goal: goal.toUpperCase(),
        platform_selection: buildPlatformSelection(platforms, mode),
        workspace_id: wsId || undefined,
      });
      if (r.campaign_id) {
        router.push(`/campaigns/${r.campaign_id}`);
        return;
      }
      setErr("학습 작업을 시작했습니다. AI 학습실에서 진행 상황을 확인하세요.");
      setBusy(false);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  }

  const pipeline: JobStep[] = useMemo(
    () => PIPELINE_STAGES.map((s) => ({ key: s.key, label: s.label, state: stageState(snap, s.key) })),
    [snap],
  );
  const job = (snap?.current_jobs?.[0] as Record<string, unknown>) || null;
  const hasJob = !!job && Object.keys(job).length > 0;

  const money = (c: LibraryCard) =>
    c.revenue_actual != null
      ? `${c.revenue_actual.toLocaleString()} ${c.currency}`
      : c.revenue_estimated != null
        ? `약 ${c.revenue_estimated.toLocaleString()} ${c.currency}`
        : "-";

  return (
    <div className="space-y-8">
      {/* ---------------------------------------------- Quick Create Composer */}
      <section aria-labelledby="composer-h">
        <div className="mb-5 border-b border-hairline pb-5">
          <div className="mb-3 flex items-center justify-between font-mono text-[11px] uppercase tracking-[0.18em] text-ink-tertiary">
            <span>Creative operations / 001</span>
            <span>{modeLabel || "STUDIO ONLINE"}</span>
          </div>
          <div className="flex items-end justify-between gap-6">
            <h1 id="composer-h" className="font-display text-[clamp(42px,7vw,104px)] font-bold uppercase leading-[0.82] tracking-[-0.065em] text-ink">
              Content<br /><span className="text-primary">Factory®</span>
            </h1>
            <p className="hidden max-w-[310px] pb-1 text-right text-body leading-snug text-ink-subtle md:block">
              리서치부터 영상·게시·학습까지.<br />오늘의 제작 지시를 입력하세요.
            </p>
          </div>
        </div>

        <div className="panel overflow-hidden">
          <div className="flex items-start gap-3 border-b border-hairline p-4 sm:p-5">
            <span className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
              <Icon name="sparkles" size={15} />
            </span>
            <div className="min-w-0 flex-1">
              <label htmlFor="topic" className="font-mono text-caption font-medium uppercase tracking-[0.12em] text-ink-subtle">
                Creative brief
              </label>
              <input
                id="topic"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && start()}
                placeholder="어떤 콘텐츠를 제작할까요?"
                autoComplete="off"
                className="mt-2 w-full rounded-sm bg-transparent font-display text-[22px] font-medium tracking-[-0.04em] text-ink outline-none placeholder:text-ink-tertiary focus-visible:ring-2 focus-visible:ring-primary-focus/50 sm:text-[30px]"
              />
            </div>
          </div>

          <div className="grid gap-5 p-4 sm:p-5 md:grid-cols-2">
            <div>
              <p className="text-caption font-medium text-ink-subtle">플랫폼</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {opts.platforms.map((p) => {
                  const on = platforms.includes(p);
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => togglePlatform(p)}
                      aria-pressed={on}
                      className={`rounded-md border px-2.5 py-1 text-caption transition-colors ${
                        on
                          ? "border-primary bg-primary/10 text-ink"
                          : "border-hairline text-ink-subtle hover:border-hairline-strong"
                      }`}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <p className="text-caption font-medium text-ink-subtle">목표</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {opts.goals.map((g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => setGoal(g)}
                    aria-pressed={goal === g}
                    className={`rounded-md border px-2.5 py-1 text-caption transition-colors ${
                      goal === g
                        ? "border-primary bg-primary/10 text-ink"
                        : "border-hairline text-ink-subtle hover:border-hairline-strong"
                    }`}
                  >
                    {GOAL_KO[g] ?? g}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {advanced && (
            <div className="grid gap-5 border-t border-hairline p-4 sm:p-5 md:grid-cols-2">
              <div>
                <p className="text-caption font-medium text-ink-subtle">작업 모드</p>
                <div className="mt-2 space-y-1.5">
                  {MODES.map((m) => (
                    <label
                      key={m.id}
                      className={`flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2 ${
                        mode === m.id ? "border-primary bg-primary/10" : "border-hairline"
                      }`}
                    >
                      <input
                        type="radio"
                        name="mode"
                        checked={mode === m.id}
                        onChange={() => setMode(m.id)}
                        className="mt-1 accent-[rgb(var(--primary))]"
                      />
                      <span>
                        <span className="block text-body-sm text-ink">{m.label}</span>
                        <span className="block text-caption text-ink-tertiary">{m.hint}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <p className="text-caption font-medium text-ink-subtle">품질</p>
                  <div className="mt-2 flex gap-1.5">
                    {QUALITY.map((q) => (
                      <button
                        key={q.id}
                        type="button"
                        onClick={() => setQuality(q.id)}
                        aria-pressed={quality === q.id}
                        className={`rounded-md border px-3 py-1.5 text-caption ${
                          quality === q.id ? "border-primary bg-primary/10 text-ink" : "border-hairline text-ink-subtle"
                        }`}
                      >
                        {q.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label htmlFor="ref-url" className="text-caption font-medium text-ink-subtle">
                    참고자료 (URL)
                  </label>
                  <div className="mt-2 flex gap-1.5">
                    <input
                      id="ref-url"
                      value={refUrl}
                      onChange={(e) => setRefUrl(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addRef())}
                      placeholder="https://…"
                      type="url"
                      inputMode="url"
                      autoComplete="off"
                      className="input"
                    />
                    <button type="button" className="btn btn-secondary" onClick={addRef}>
                      추가
                    </button>
                  </div>
                  {refs.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {refs.map((u) => (
                        <li key={u} className="flex items-center gap-2 text-caption text-ink-subtle">
                          <Icon name="external" size={12} />
                          <span className="truncate">{u}</span>
                          <button
                            className="ml-auto text-ink-tertiary hover:text-ink"
                            onClick={() => setRefs((r) => r.filter((x) => x !== u))}
                            aria-label="참고자료 제거"
                          >
                            <Icon name="x" size={12} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 border-t border-hairline bg-white/[0.02] p-4 sm:p-5">
            <button
              type="button"
              onClick={() => setAdvanced((v) => !v)}
              className="btn btn-ghost !px-2 text-caption"
              aria-expanded={advanced}
            >
              <Icon name={advanced ? "chevron-down" : "chevron-right"} size={14} />
              세부 설정
            </button>

            <div className="ml-auto flex items-center gap-4">
              <div className="text-right">
                <p className="text-caption text-ink-tertiary">예상 비용</p>
                <p className="font-display text-body-sm font-semibold tabular-nums text-ink">
                  {estUsd == null ? "계산 중…" : estUsd < 0 ? "확인 불가" : `$${estUsd.toFixed(2)}`}
                  {estUnknown && <span className="ml-1 text-caption font-normal text-brand-secure">일부 미상</span>}
                </p>
              </div>
              <button type="button" onClick={start} disabled={busy} className="btn btn-primary">
                {busy ? "시작하는 중" : "콘텐츠 만들기"}
                {!busy && <Icon name="arrow-right" size={15} />}
              </button>
            </div>
          </div>

          {err && (
            <p className="border-t border-hairline px-4 py-3 text-body-sm text-brand-secure sm:px-5">{err}</p>
          )}
        </div>
      </section>

      {/* ---------------------------------------------- 4 operational KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {(() => {
          const spent = Number(snap?.cost?.actual_usd ?? 0);
          const budget = Number(snap?.cost?.budget_usd ?? 0);
          const running = snap?.current_jobs?.length ?? 0;
          const stage = String((snap?.current_jobs?.[0] as Record<string, unknown>)?.current_stage ?? "");
          const tiles: { label: string; value: string; hint: string; pct?: number }[] = [
            {
              label: "오늘 AI 비용",
              value: `$${spent.toFixed(2)}`,
              hint: budget > 0 ? `예산 $${budget.toFixed(0)} 중` : "예산 미설정",
              pct: budget > 0 ? Math.min(100, (spent / budget) * 100) : undefined,
            },
            {
              label: "현재 처리 중",
              value: `${running}건`,
              hint: running > 0 ? (stage || "진행 중") : "대기 중인 작업 없음",
            },
            {
              label: "검수 대기",
              value: `${queue?.length ?? 0}건`,
              hint: (queue?.length ?? 0) > 0 ? "확인이 필요합니다" : "모두 처리됨",
            },
            {
              label: "오늘 순이익",
              value: ana ? `$${(ana.net_profit ?? 0).toFixed(2)}` : "-",
              hint: ana?.margin != null ? `마진 ${Math.round((ana.margin ?? 0) * 100)}%` : "수익 데이터 없음",
            },
          ];
          return tiles.map((t, i) => (
            <div key={t.label} className={i === 0 ? "card-hero" : "card"}>
              <div className="min-h-[154px] p-5">
                <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-subtle">0{i + 1} / {t.label}</p>
                <p className="mt-7 font-display text-[36px] font-semibold leading-none tracking-[-0.05em] text-ink tabular-nums">
                  {snap === null && t.label !== "오늘 순이익" ? <span className="text-ink-tertiary">…</span> : t.value}
                </p>
                {t.pct != null && (
                  <span className="mt-2.5 block h-1 w-full overflow-hidden rounded-full bg-surface-3">
                    <span
                      className="block h-full rounded-full bg-primary"
                      style={{ width: `${t.pct}%` }}
                    />
                  </span>
                )}
                <p className="mt-1.5 text-caption text-ink-tertiary">{t.hint}</p>
              </div>
            </div>
          ));
        })()}
      </div>

      {/* -------------------------------------------- 3D operations studio (full-bleed) */}
      <div className="-mt-1">
        <OfficeStage snap={snap} />
      </div>

      {/* ---------------------------------------------- priority information */}
      <div className="-mt-6 grid gap-4 lg:grid-cols-3">
        {/* current job - spans 2 */}
        <Card className="lg:col-span-2">
          <CardBody>
            <CardTitle sub={hasJob ? String(job?.topic ?? "") : undefined}>현재 작업</CardTitle>
            {snap === null ? (
              <SkeletonText lines={2} />
            ) : hasJob ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
                  <Metric size="sm" label="단계" value={String(job?.current_stage ?? "-")} />
                  <Metric size="sm" label="모드" value={String(job?.execution_mode ?? "-")} />
                  <Metric size="sm" label="경과(초)" value={String(job?.elapsed_s ?? "-")} />
                  <Metric size="sm" label="비용" value={`$${Number(snap.cost?.actual_usd ?? 0).toFixed(3)}`} />
                </div>
                <div className="overflow-x-auto">
                  <JobProgress steps={pipeline} />
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 py-4 text-body-sm text-ink-subtle">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-2 text-ink-tertiary">
                  <Icon name="activity" size={15} />
                </span>
                진행 중인 작업이 없습니다. 위에서 주제를 입력해 새 콘텐츠 제작을 시작하세요.
              </div>
            )}
          </CardBody>
        </Card>

        {/* review queue */}
        <Card>
          <CardBody>
            <CardTitle sub={queue ? `${queue.length}건` : undefined}>검수 대기</CardTitle>
            {queue === null ? (
              <SkeletonText lines={3} />
            ) : queue.length === 0 ? (
              <p className="py-6 text-center text-body-sm text-ink-subtle">검수 대기 중인 콘텐츠가 없습니다.</p>
            ) : (
              <ul className="space-y-2">
                {queue.slice(0, 5).map((c) => (
                  <li key={c.id} className="flex items-center gap-2 text-body-sm">
                    <StatusBadge value={c.state} size="sm" />
                    <span className="truncate text-ink-muted">{c.case_type}</span>
                  </li>
                ))}
                <li>
                  <Link href="/governance" className="text-caption text-primary hover:underline">
                    검수 센터 열기 →
                  </Link>
                </li>
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* recent content */}
        <Card className="lg:col-span-2">
          <CardBody>
            <CardTitle sub={<Link href="/library" className="text-primary hover:underline">전체 보기</Link>}>
              최근 콘텐츠
            </CardTitle>
            {recent === null ? (
              <SkeletonText lines={4} />
            ) : recent.length === 0 ? (
              <EmptyState
                icon="library"
                title="아직 콘텐츠가 없습니다"
                body="첫 콘텐츠를 만들면 여기에서 관리할 수 있습니다."
                action={
                  <Link href="/create" className="btn btn-secondary">
                    <Icon name="plus" size={15} />
                    콘텐츠 만들기
                  </Link>
                }
              />
            ) : (
              <ul className="divide-y divide-hairline">
                {recent.map((c) => (
                  <li key={c.campaign_id}>
                    <Link
                      href={`/library/${c.campaign_id}`}
                      className="flex items-center gap-3 py-2.5 hover:opacity-80"
                    >
                      <span className="flex h-9 w-14 flex-shrink-0 items-center justify-center rounded border border-hairline bg-surface-2 text-ink-tertiary">
                        <Icon name="film" size={14} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-body-sm text-ink">{c.topic || "(제목 없음)"}</span>
                        <span className="block truncate text-caption text-ink-tertiary">
                          {c.platforms.join(", ") || "플랫폼 미생성"} · {c.created_at?.slice(0, 10) ?? "-"}
                        </span>
                      </span>
                      <StatusBadge value={c.governance} size="sm" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        {/* today performance + budget + autopilot */}
        <div className="space-y-4">
          <Card>
            <CardBody>
              <CardTitle sub={<Link href="/analytics" className="text-primary hover:underline">분석</Link>}>
                오늘의 성과
              </CardTitle>
              {ana === null ? (
                <SkeletonText lines={2} />
              ) : (
                <div className="grid grid-cols-2 gap-y-3">
                  <Metric size="sm" label="조회수" value={(ana.metrics?.views ?? 0).toLocaleString()} />
                  <Metric size="sm" label="시청시간" value={(ana.metrics?.watch_time_seconds ?? 0).toLocaleString()} />
                  <Metric size="sm" label="총 수익" value={`$${(ana.revenue?.total ?? 0).toFixed(2)}`} />
                  <Metric size="sm" label="총 비용" value={`$${(ana.cost?.total ?? 0).toFixed(2)}`} />
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardBody>
              <CardTitle sub={auto ? auto.mode : undefined}>오토파일럿</CardTitle>
              {auto === null ? (
                <SkeletonText lines={2} />
              ) : (
                <div className="space-y-2">
                  <div className="grid grid-cols-3 gap-y-2">
                    <Metric size="sm" label="후보" value={auto.candidates} />
                    <Metric size="sm" label="제작 중" value={auto.producing} />
                    <Metric size="sm" label="예약" value={auto.scheduled} />
                  </div>
                  <p className="text-caption text-ink-tertiary">
                    오늘 예산 ${auto.today_budget?.spent?.toFixed(2)} / ${auto.today_budget?.daily?.toFixed(2)}
                  </p>
                  <Link href="/autopilot" className="text-caption text-primary hover:underline">
                    오토파일럿 관리 →
                  </Link>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
