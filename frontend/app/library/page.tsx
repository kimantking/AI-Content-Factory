"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { contentLibrary, deleteContent, libraryStats, type LibraryCard, type LibraryPage } from "@/lib/api";
import { PageHeader, Card, CardBody, EmptyState, ErrorState } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DataTable, Pagination, useUrlState, type Column } from "@/components/ui/DataTable";
import { Icon } from "@/components/ui/Icon";
import { platformKo, statusMeta } from "@/lib/status";

const PLATFORMS = [
  "youtube_shorts", "youtube_long", "tiktok", "instagram_reel", "instagram_carousel",
  "x", "threads", "linkedin", "naver_blog",
];
const GOV = ["OK", "REVIEW", "BLOCKED", "NOT_APPLICABLE"];
const PUB = ["PUBLISHED", "SCHEDULED", "DRAFT", "BLOCKED", "NOT_PUBLISHED"];
const SORTS: { id: string; label: string }[] = [
  { id: "newest", label: "최신순" },
  { id: "oldest", label: "오래된순" },
  { id: "views", label: "조회수" },
  { id: "revenue", label: "수익" },
  { id: "profit", label: "순이익" },
];

function money(c: LibraryCard) {
  if (c.revenue_actual != null) return `${c.revenue_actual.toLocaleString()} ${c.currency}`;
  if (c.revenue_estimated != null) return `약 ${c.revenue_estimated.toLocaleString()} ${c.currency}`;
  return "-";
}
function fmtDur(s: number | null) {
  if (!s) return "-";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export default function LibraryView() {
  return (
    <Suspense fallback={<div className="card-p text-body-sm text-ink-subtle">불러오는 중…</div>}>
      <LibraryInner />
    </Suspense>
  );
}

function LibraryInner() {
  const { get, setMany } = useUrlState();
  const [wsId, setWsId] = useState("");
  const [data, setData] = useState<LibraryPage | null>(null);
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const view = get("view", "gallery");
  const q = get("q");
  const platform = get("platform");
  const governance = get("governance");
  const publishState = get("publish");
  const sort = get("sort", "newest");
  const page = Number(get("page", "1")) || 1;

  useEffect(() => {
    try {
      setWsId(window.localStorage.getItem("acf_workspace_id") ?? "");
    } catch {
      /* ignore */
    }
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setErr(null);
    const p: Record<string, string> = { page: String(page), sort };
    if (wsId) p.workspace_id = wsId;
    if (q) p.q = q;
    if (platform) p.platform = platform;
    if (governance) p.governance = governance;
    if (publishState) p.publish_state = publishState;
    contentLibrary(p)
      .then(setData)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [wsId, q, platform, governance, publishState, sort, page]);

  useEffect(load, [load]);
  useEffect(() => {
    libraryStats(wsId || undefined).then(setStats).catch(() => undefined);
  }, [wsId]);

  const setFilter = (patch: Record<string, string | number | null>) => setMany({ ...patch, page: 1 });

  const remove = async (c: LibraryCard) => {
    if (!window.confirm(`“${c.topic || "제목 없음"}” 콘텐츠를 완전히 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`)) return;
    setDeletingId(c.campaign_id);
    setErr(null);
    try {
      await deleteContent(c.campaign_id);
      load();
      libraryStats(wsId || undefined).then(setStats).catch(() => undefined);
    } catch (e) {
      setErr(String(e));
    } finally {
      setDeletingId(null);
    }
  };

  const columns: Column<LibraryCard>[] = [
    {
      key: "topic",
      header: "제목",
      cell: (c) => (
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium text-ink">{c.topic || "(제목 없음)"}</span>
          {c.legacy && <span className="chip !px-1.5 !py-0 !text-[10px]">레거시</span>}
          {c.is_demo && <span className="chip !px-1.5 !py-0 !text-[10px]">데모</span>}
        </div>
      ),
    },
    { key: "platforms", header: "플랫폼", hideBelow: "md", cell: (c) => <span className="text-caption">{c.platforms.map(platformKo).join(", ") || "-"}</span> },
    { key: "created", header: "생성일", hideBelow: "sm", cell: (c) => <span className="text-caption">{c.created_at?.slice(0, 10) ?? "-"}</span> },
    { key: "gov", header: "검수", cell: (c) => <StatusBadge value={c.governance} size="sm" /> },
    { key: "pub", header: "게시", hideBelow: "sm", cell: (c) => <StatusBadge value={c.publish_state} size="sm" /> },
    { key: "views", header: "조회", align: "right", hideBelow: "md", cell: (c) => c.views?.toLocaleString() ?? "-" },
    { key: "revenue", header: "수익", align: "right", hideBelow: "lg", cell: (c) => money(c) },
    { key: "actions", header: "관리", align: "right", cell: (c) => (
      <button
        className="btn btn-secondary !px-2 !py-1 !text-caption"
        disabled={deletingId === c.campaign_id || c.status === "RUNNING"}
        onClick={(e) => { e.stopPropagation(); void remove(c); }}
      >
        {deletingId === c.campaign_id ? "삭제 중…" : "삭제"}
      </button>
    ) },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="콘텐츠 보관함"
        eyebrow="콘텐츠"
        description={
          stats
            ? `전체 ${stats.total_campaigns ?? 0}개 · 영상 ${stats.campaigns_with_video ?? 0}개 · 게시됨 ${stats.published_campaigns ?? 0}개`
            : "제작한 모든 콘텐츠를 한 곳에서 관리합니다."
        }
        actions={
          <div className="flex rounded-md border border-hairline p-0.5">
            {(["gallery", "table"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setMany({ view: v })}
                aria-pressed={view === v}
                className={`rounded px-2.5 py-1 text-caption ${
                  view === v ? "bg-surface-2 text-ink" : "text-ink-subtle"
                }`}
              >
                {v === "gallery" ? "갤러리" : "표"}
              </button>
            ))}
          </div>
        }
      />

      {/* filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Icon name="search" size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-tertiary" />
          <input
            defaultValue={q}
            onKeyDown={(e) => e.key === "Enter" && setFilter({ q: (e.target as HTMLInputElement).value })}
            placeholder="제목·대본 검색 후 Enter"
            aria-label="제목 대본 검색"
            className="input !w-[220px] !pl-8"
          />
        </div>
        <select aria-label="플랫폼 필터" className="input !w-auto" value={platform} onChange={(e) => setFilter({ platform: e.target.value })}>
          <option value="">플랫폼 전체</option>
          {PLATFORMS.map((p) => (
            <option key={p} value={p}>{platformKo(p)}</option>
          ))}
        </select>
        <select aria-label="검수 상태 필터" className="input !w-auto" value={governance} onChange={(e) => setFilter({ governance: e.target.value })}>
          <option value="">검수 전체</option>
          {GOV.map((g) => (
            <option key={g} value={g}>{statusMeta(g).ko}</option>
          ))}
        </select>
        <select aria-label="게시 상태 필터" className="input !w-auto" value={publishState} onChange={(e) => setFilter({ publish: e.target.value })}>
          <option value="">게시상태 전체</option>
          {PUB.map((g) => (
            <option key={g} value={g}>{statusMeta(g).ko}</option>
          ))}
        </select>
        <select aria-label="정렬 기준" className="input !ml-auto !w-auto" value={sort} onChange={(e) => setMany({ sort: e.target.value, page: 1 })}>
          {SORTS.map((s) => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
      </div>

      {err ? (
        <ErrorState detail={err} onRetry={load} />
      ) : loading && !data ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <div className="aspect-video animate-pulse bg-surface-2" />
              <CardBody>
                <div className="h-4 w-2/3 animate-pulse rounded bg-surface-2" />
              </CardBody>
            </Card>
          ))}
        </div>
      ) : data && data.items.length === 0 ? (
        <EmptyState
          icon="library"
          title={q || platform || governance || publishState ? "조건에 맞는 콘텐츠가 없습니다" : "아직 콘텐츠가 없습니다"}
          body={
            q || platform || governance || publishState
              ? "필터를 변경해 다시 시도해보세요."
              : "첫 콘텐츠를 만들어보세요. 제작이 끝나면 여기에서 관리할 수 있습니다."
          }
          action={
            <Link href="/create" className="btn btn-primary">
              <Icon name="plus" size={15} />
              콘텐츠 만들기
            </Link>
          }
        />
      ) : view === "table" ? (
        <DataTable
          columns={columns}
          rows={data?.items ?? []}
          getKey={(c) => c.campaign_id}
          onRowClick={(c) => (window.location.href = `/library/${c.campaign_id}`)}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data?.items.map((c) => (
            <div key={c.campaign_id} className="group relative">
              <Link href={`/library/${c.campaign_id}`}>
              <Card className="overflow-hidden transition-colors group-hover:border-hairline-strong">
                <div className="relative flex aspect-video items-center justify-center border-b border-hairline bg-surface-2 text-ink-tertiary">
                  {c.thumbnail_path ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={c.thumbnail_path} alt={c.topic || "콘텐츠 썸네일"} className="h-full w-full object-cover" />
                  ) : (
                    <span className="flex flex-col items-center gap-1 text-caption">
                      <Icon name="film" size={20} />
                      {c.has_video ? "영상 파일 없음" : "영상 없음"}
                    </span>
                  )}
                  {c.video_playable && (
                    <span className="absolute left-2 top-2 chip !bg-canvas/80 !py-0.5 !text-[10px]">
                      <Icon name="eye" size={11} /> 재생 가능
                    </span>
                  )}
                  {c.duration ? (
                    <span className="absolute bottom-2 right-2 rounded bg-canvas/80 px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">
                      {fmtDur(c.duration)}
                    </span>
                  ) : null}
                </div>
                <CardBody className="!p-3.5">
                  <p className="line-clamp-2 text-body-sm font-medium text-ink">{c.topic || "(제목 없음)"}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <StatusBadge value={c.governance} size="sm" />
                    <StatusBadge value={c.publish_state} size="sm" />
                  </div>
                  <p className="mt-2 truncate text-caption text-ink-tertiary">
                    {c.platforms.map(platformKo).join(", ") || "플랫폼 미생성"} · {c.created_at?.slice(0, 10) ?? "-"}
                  </p>
                  <p className="mt-0.5 text-caption text-ink-tertiary">
                    조회 {c.views?.toLocaleString() ?? "-"} · 수익 {money(c)}
                  </p>
                </CardBody>
              </Card>
              </Link>
              <button
                className="btn btn-secondary absolute right-2 top-2 z-10 !px-2.5 !py-1.5 !text-caption shadow-sm"
                disabled={deletingId === c.campaign_id || c.status === "RUNNING"}
                title={c.status === "RUNNING" ? "진행 중인 작업은 삭제할 수 없습니다" : "콘텐츠 삭제"}
                onClick={() => void remove(c)}
              >
                {deletingId === c.campaign_id ? "삭제 중…" : "삭제"}
              </button>
            </div>
          ))}
        </div>
      )}

      {data && (
        <Pagination page={data.page} pages={data.pages} onPage={(p) => setMany({ page: p })} />
      )}
    </div>
  );
}
