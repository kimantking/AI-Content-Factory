import type { SupportSnapshot } from "@/lib/api";

/**
 * The 3D office is a *view* of real backend state - never a decoration.
 * Each of the 4 workstations aggregates the real pipeline steps that its agent
 * owns. No station shows a state the backend did not report.
 */

export type StationState = "IDLE" | "RUNNING" | "ATTN" | "FAILED" | "BLOCKED" | "DONE";

export type AgentId = "research" | "script" | "video" | "publish";

export type AgentMeta = {
  id: AgentId;
  name: string; // Korean, user-facing
  role: string; // Korean
  /** grid slot [col,row] in the 2x2 office */
  slot: [number, number];
};

export const AGENTS: AgentMeta[] = [
  { id: "research", name: "리서치 에이전트", role: "주제 조사 · 팩트체크", slot: [0, 0] },
  { id: "script", name: "대본 에이전트", role: "전략 · 훅 · 대본", slot: [1, 0] },
  { id: "video", name: "영상 에이전트", role: "미디어 · 렌더링", slot: [0, 1] },
  { id: "publish", name: "게시 에이전트", role: "거버넌스 · 게시", slot: [1, 1] },
];

/** pipeline step key fragments each station owns */
const OWNS: Record<AgentId, string[]> = {
  research: ["research", "fact"],
  script: ["strateg", "hook", "script", "qa", "persist"],
  video: ["media", "render", "video", "broll", "voice", "subtitle"],
  publish: ["governance", "publish", "rights", "disclosure"],
};

const RANK: Record<StationState, number> = { FAILED: 5, BLOCKED: 4, ATTN: 3, RUNNING: 2, DONE: 1, IDLE: 0 };

function stepToState(raw: string): StationState {
  const s = raw.toUpperCase();
  if (["FAILED", "ERROR"].includes(s)) return "FAILED";
  if (s === "BLOCKED") return "BLOCKED";
  if (["RETRY", "WARNING", "DEGRADED"].includes(s)) return "ATTN";
  if (["RUNNING", "IN_PROGRESS", "PENDING", "QUEUED", "WAITING"].includes(s)) {
    return s === "RUNNING" || s === "IN_PROGRESS" ? "RUNNING" : "IDLE";
  }
  if (["SUCCESS", "DONE", "COMPLETED"].includes(s)) return "DONE";
  return "IDLE";
}

export type OfficeModel = {
  stations: Record<AgentId, StationState>;
  job: {
    campaignId: string | null;
    topic: string | null;
    stage: string | null;
    mode: string | null;
    elapsedS: number | null;
    model: string | null;
    provider: string | null;
    costUsd: number | null;
  };
  hasJob: boolean;
};

export function deriveOffice(snap: SupportSnapshot | null): OfficeModel {
  const pipeline = snap?.pipeline ?? [];
  const job = (snap?.current_jobs?.[0] as Record<string, unknown>) ?? {};
  const route = (snap?.model_routing?.last_route ?? {}) as Record<string, unknown>;
  const hasJob = !!job && Object.keys(job).length > 0;

  const stations = {} as Record<AgentId, StationState>;
  for (const a of AGENTS) {
    const mine = pipeline.filter((p) => OWNS[a.id].some((k) => p.step.toLowerCase().includes(k)));
    if (mine.length === 0) {
      stations[a.id] = "IDLE";
      continue;
    }
    stations[a.id] = mine
      .map((p) => stepToState(p.state))
      .reduce((worst, s) => (RANK[s] > RANK[worst] ? s : worst), "IDLE" as StationState);
  }

  return {
    stations,
    hasJob,
    job: {
      campaignId: (job.campaign_id as string) ?? null,
      topic: (job.topic as string) ?? null,
      stage: (job.current_stage as string) ?? null,
      mode: (job.execution_mode as string) ?? null,
      elapsedS: typeof job.elapsed_s === "number" ? (job.elapsed_s as number) : null,
      model: (route.model as string) ?? null,
      provider: (route.provider as string) ?? null,
      costUsd:
        typeof (snap?.cost as Record<string, unknown>)?.actual_usd === "number"
          ? ((snap!.cost as Record<string, unknown>).actual_usd as number)
          : null,
    },
  };
}

/** state -> { ko label, hex accent } for both the 3D scene and the 2.5D fallback */
export const STATE_META: Record<StationState, { ko: string; hex: string; dim: boolean }> = {
  IDLE: { ko: "대기", hex: "#62666d", dim: true },
  RUNNING: { ko: "작업 중", hex: "#dc86ad", dim: false },
  ATTN: { ko: "주의", hex: "#c892cf", dim: false },
  FAILED: { ko: "오류", hex: "#d96f91", dim: false },
  BLOCKED: { ko: "차단됨", hex: "#b89db6", dim: false },
  DONE: { ko: "완료", hex: "#27a644", dim: false },
};
