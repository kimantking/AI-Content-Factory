export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type AgentChatMessage = { role: "user" | "assistant"; content: string };

export async function chatWithAgent(
  agentId: string,
  message: string,
  history: AgentChatMessage[],
  campaignContext?: Record<string, unknown>,
) {
  const r = await fetch(`${API_BASE}/api/agents/${agentId}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message, history, campaign_context: campaignContext }),
  });
  if (!r.ok) throw new Error(`agent chat failed: ${r.status}`);
  return r.json() as Promise<{ reply: string; provider: string; model: string; mock: boolean }>;
}

export type StepStatus = { name: string; status: string };

export type CampaignDetail = {
  id: string;
  topic: string;
  status: string;
  current_step: string | null;
  audience_goal: string;
  fact_score: number | null;
  created_at: string;
  platforms: string[];
  knowledge_pack: Record<string, unknown> | null;
  error_message: string | null;
  steps: StepStatus[];
  sources: { id: string; url: string; title: string; snippet: string }[];
  verified_facts: {
    fact: string;
    status: string;
    confidence: number;
    source_ids: string[];
    reason: string;
  }[];
  strategy: Record<string, unknown> | null;
  hooks: { text: string; style: string; score: number; rank: number }[];
  script: {
    body: string;
    draft_body: string | null;
    word_count: number;
    qa_passed: boolean;
    qa_report: Record<string, unknown>;
    cta_type: string | null;
    ai_slop_score: number | null;
    naturalness: Record<string, unknown>;
  } | null;
  agent_runs: {
    agent_name: string;
    status: string;
    provider: string | null;
    model: string | null;
    input_tokens: number;
    output_tokens: number;
    estimated_cost: number;
    error_type: string | null;
    error_message: string | null;
  }[];
  cost_usd: number;
  budget: Record<string, number>;
};

export type CampaignSummary = Pick<
  CampaignDetail,
  "id" | "topic" | "status" | "current_step" | "audience_goal" | "fact_score" | "created_at"
>;

export async function getConfig() {
  const r = await fetch(`${API_BASE}/api/config`, { cache: "no-store" });
  if (!r.ok) throw new Error("config failed");
  return r.json();
}

export async function createCampaign(body: {
  topic: string;
  audience_goal: string;
  platforms: string[];
}): Promise<{ id: string }> {
  const r = await fetch(`${API_BASE}/api/campaigns`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`create failed: ${r.status}`);
  return r.json();
}

export async function getCampaign(id: string): Promise<CampaignDetail> {
  const r = await fetch(`${API_BASE}/api/campaigns/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`load failed: ${r.status}`);
  return r.json();
}

export async function listCampaigns(limit = 50): Promise<CampaignSummary[]> {
  const r = await fetch(`${API_BASE}/api/campaigns?limit=${limit}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`campaign list failed: ${r.status}`);
  return r.json();
}

export async function cancelCampaign(id: string): Promise<{ ok: boolean; status: string }> {
  const r = await fetch(`${API_BASE}/api/campaigns/${id}/cancel`, { method: "POST" });
  if (!r.ok) throw new Error(`작업 중지 실패 (${r.status})`);
  return r.json();
}

export async function deleteCampaign(id: string): Promise<{ ok: boolean; deleted_records: number }> {
  const r = await fetch(`${API_BASE}/api/campaigns/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`작업 삭제 실패 (${r.status})`);
  return r.json();
}

export type MediaStatus = {
  campaign_id: string;
  media_status: string;
  current_step: string;
  progress: { name: string; status: string }[];
  scene_monitor: {
    scene_id: string;
    order: number;
    narration: string;
    duration: number;
    visual_type: string;
    camera_motion: string;
    status: string;
    provider: string | null;
    still: string | null;
  }[];
  cost_by_kind: Record<string, number>;
  cost_total: number;
  media_budget: number;
  render: {
    video: string | null;
    duration: number | null;
    width: number | null;
    height: number | null;
  };
  thumbnails: (string | null)[];
  previews: {
    platform: string;
    label: string;
    family: string;
    status: string;
    content_type: string;
    aspect_ratio: string;
    hook: string;
    caption: string;
    cta: string;
    hashtags: string[];
    script: string;
    video: string | null;
    images: string[];
  }[];
  creative_plan: CreativePlan | null;
  video_qa: VideoQA | null;
};

export type CreativePlan = {
  platform: string;
  content_type: string;
  profile: string;
  pace_profile: string;
  emotional_arc: string[];
  story_arc: { beat: string; scene_orders: number[]; emotion_from: string; emotion_to: string; purpose: string }[];
  scene_directions: {
    scene_order: number; story_beat: string; emotion_intent: string;
    shot_size: string; shot_purpose: string; motion_energy: string;
    cinematic_motion: string; primary_focus: string; edit_intent: string;
    cognitive_load: number; information_density: number; kinetic_caption: string;
    visual_evidence: boolean; notes: string[];
  }[];
  editing_language: Record<string, unknown>;
  shot_language: Record<string, unknown>;
  retention_strategy: {
    first_second_strength: number; early_payoff: boolean; open_loops: number;
    checkpoints: { label: string; t: number; scene_order: number; reason_to_stay: string; risk: string }[];
    pattern_interrupts: number[];
  };
  high_impact_scenes: number[];
  budget_distribution: Record<string, number>;
  boredom_risk: number;
  skills: Record<string, string>;
  warnings: string[];
};

export type VideoQA = {
  overall: number;
  overall_100?: number;
  passed: boolean;
  dimensions: Record<string, number>;
  weak: string[];
  boredom_risk: number;
  first_second_strength: number;
  early_payoff: boolean;
  continuity_score?: number;
  bad_scenes: { scene_order: number; flags: string[]; strategies: string[] }[];
  repair_plan?: { scene_order: number; flag: string; strategy: string }[];
  creative_qa?: { passed: boolean; score: number; checks: Record<string, string>; notes: string[] };
  cut_rhythm?: Record<string, unknown>;
  technical_qa?: { verdict: string; passes: Record<string, { status: string; [k: string]: unknown }>; notes: string[] };
  notes: string[];
  error?: string;
};

export async function startMedia(id: string, resume = false): Promise<unknown> {
  const r = await fetch(`${API_BASE}/api/campaigns/${id}/media`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ resume }),
  });
  if (!r.ok) throw new Error(`start media failed: ${r.status}`);
  return r.json();
}

export async function getMedia(id: string): Promise<MediaStatus> {
  const r = await fetch(`${API_BASE}/api/campaigns/${id}/media`, { cache: "no-store" });
  if (!r.ok) throw new Error(`media load failed: ${r.status}`);
  return r.json();
}

export async function regenerateScene(
  id: string,
  sceneId: string,
  body: { narration?: string; camera_motion?: string },
): Promise<unknown> {
  const r = await fetch(`${API_BASE}/api/campaigns/${id}/scenes/${sceneId}/regenerate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`regenerate failed: ${r.status}`);
  return r.json();
}

export function fileUrl(path: string | null): string | null {
  return path ? `${API_BASE}${path}` : null;
}

// ---- Phase 2: publishing ----

export type PlatformCapabilityRow = {
  platform: string;
  official_api: string;
  publishing_status: string;
  implementation_status: string;
  app_review_required: boolean;
  account_requirement: string;
  known_limits: string;
  last_verified_at: string;
};

export type AccountRow = {
  id: string;
  platform: string;
  account_name: string | null;
  connection_status: string;
  publishing_status: string;
  app_review_required: boolean;
  account_requirement: string;
  integration_status: string;
  scopes_ok: boolean;
  token_expires_at: string | null;
};

export type PublishJobRow = {
  id: string;
  platform: string;
  content_type: string;
  status: string;
  run_mode: string;
  approval_status: string;
  dry_run: boolean;
  scheduled_at: string | null;
  timezone: string;
  attempt_count: number;
  remote_post_id: string | null;
  remote_url: string | null;
  last_error_type: string | null;
  dead_lettered: boolean;
  title: string;
  caption: string;
};

const HTTP_ERROR_KO: Record<string, string> = {
  "topic is required unless execution_mode is LEARN_ONLY / REFERENCE_ONLY": "콘텐츠 주제를 입력해 주세요.",
  "urls required": "학습할 참고자료 URL을 하나 이상 입력해 주세요.",
  "X-Workspace-Id header required": "작업공간을 먼저 선택해 주세요.",
};

// Keep the shared fetch helper compatible with the endpoint-specific return types below.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const j = async (r: Response): Promise<any> => {
  const data = await r.json().catch(() => null) as Record<string, unknown> | null;
  if (!r.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : "";
    throw new Error(HTTP_ERROR_KO[detail] ?? (detail || `요청을 처리하지 못했습니다. (오류 ${r.status})`));
  }
  return data;
};

export const getCapabilities = (): Promise<PlatformCapabilityRow[]> =>
  fetch(`${API_BASE}/api/publishing/capabilities`, { cache: "no-store" }).then(j);

export const listAccounts = (): Promise<AccountRow[]> =>
  fetch(`${API_BASE}/api/publishing/accounts`, { cache: "no-store" }).then(j);

export const mockConnect = (platform: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/publishing/accounts/${platform}/mock-connect`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ account_name: `Mock ${platform}`, account_type: "BUSINESS" }),
  }).then(j);

export const startConnect = (platform: string): Promise<{ authorization_url: string; mode: string }> =>
  fetch(`${API_BASE}/api/publishing/accounts/${platform}/connect`, { method: "POST" }).then(j);

export const disconnectAccount = (id: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/publishing/accounts/${id}/disconnect`, { method: "POST" }).then(j);

export const createPublishJobs = (
  campaignId: string,
  body: { accounts?: Record<string, string>; schedule?: Record<string, string>; run_mode?: string; dry_run?: boolean },
): Promise<PublishJobRow[]> =>
  fetch(`${API_BASE}/api/publishing/campaigns/${campaignId}/jobs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then(j);

export const getPublishingDashboard = (
  campaignId: string,
): Promise<{ rollup: string; dry_run: boolean; publish_mode: string; jobs: PublishJobRow[] }> =>
  fetch(`${API_BASE}/api/publishing/campaigns/${campaignId}`, { cache: "no-store" }).then(j);

export const approvePublishJob = (id: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/publishing/jobs/${id}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ actor: "dashboard-user" }),
  }).then(j);

export const runPublishJob = (id: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/publishing/jobs/${id}/run`, { method: "POST" }).then(j);

export const reschedulePublishJob = (id: string, whenIso: string, tz = "Asia/Seoul"): Promise<unknown> =>
  fetch(`${API_BASE}/api/publishing/jobs/${id}/reschedule`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ when: whenIso, tz }),
  }).then(j);

export const getJobEvents = (
  id: string,
): Promise<{ event: string; detail: unknown; at: string }[]> =>
  fetch(`${API_BASE}/api/publishing/jobs/${id}/events`, { cache: "no-store" }).then(j);

// ---- Phase 3: analytics / learning ----

export const getAnalyticsOverview = (): Promise<{
  metrics: Record<string, number | null>;
  availability: Record<string, string[]>;
  revenue: { total: number };
  cost: { total: number };
  net_profit: number;
  margin: number | null;
}> => fetch(`${API_BASE}/api/analytics/overview`, { cache: "no-store" }).then(j);

export const getAnalyticsCapabilities = (): Promise<
  { platform: string; official_api: string; revenue_support: boolean; analytics_delay: string; known_limitations: string; metrics: Record<string, string> }[]
> => fetch(`${API_BASE}/api/analytics/capabilities`, { cache: "no-store" }).then(j);

export const getRankings = (
  sort: string,
): Promise<Record<string, unknown>[]> =>
  fetch(`${API_BASE}/api/analytics/rankings?sort=${encodeURIComponent(sort)}`, { cache: "no-store" }).then(j);

export const getNaturalnessAnalytics = (): Promise<{ n: number; rows: Record<string, unknown>[] }> =>
  fetch(`${API_BASE}/api/analytics/naturalness`, { cache: "no-store" }).then(j);

export const getRevenueDashboard = (): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/analytics/revenue`, { cache: "no-store" }).then(j);

export type MemoryRow = {
  id: string;
  type: string;
  platform: string | null;
  dimension: string | null;
  statement: string;
  status: string;
  confidence: number;
  sample_size: number;
  recommendation: Record<string, unknown>;
  evidence_ids: string[];
};

export const getLearningDashboard = (): Promise<{
  strong: MemoryRow[];
  moderate: MemoryRow[];
  experimental: MemoryRow[];
  last_run: { run_date: string; summary: Record<string, unknown> } | null;
}> => fetch(`${API_BASE}/api/learning/dashboard`, { cache: "no-store" }).then(j);

export const getMemories = (params: string = ""): Promise<MemoryRow[]> =>
  fetch(`${API_BASE}/api/learning/memories${params}`, { cache: "no-store" }).then(j);

export const memoryAction = (id: string, action: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/learning/memories/${id}/${action}`, { method: "POST" }).then(j);

export const getRecipes = (): Promise<Record<string, unknown>[]> =>
  fetch(`${API_BASE}/api/learning/recipes`, { cache: "no-store" }).then(j);

export const runLearning = (): Promise<unknown> =>
  fetch(`${API_BASE}/api/learning/run`, { method: "POST" }).then(j);

// ---- Phase 4: autopilot ----

export type AutopilotStatus = {
  mode: string;
  emergency_stop: boolean;
  today_budget: { spent: number; daily: number; hard: number; trend_reserve: number };
  last_run: { run_id: string; mode: string; status: string; stage: string; pause_reason: string | null } | null;
  candidates: number;
  strong_opportunities: number;
  selected: number;
  producing: number;
  scheduled: number;
};

export type AutopilotCandidate = {
  id: string;
  topic: string;
  angle: string;
  trend_type: string;
  dedup_status: string;
  status: string;
  portfolio_type: string | null;
  opportunity_score: number | null;
  trend_score: number | null;
  velocity_score: number | null;
  historical_score: number | null;
  audience_fit_score: number | null;
  revenue_score: number | null;
  competition_score: number | null;
  originality_score: number | null;
  fact_availability_score: number | null;
  natural_content_score: number | null;
  risk_level: string;
  estimated_cost: number;
  platform_scores: Record<string, number>;
};

export const getAutopilotStatus = (): Promise<AutopilotStatus> =>
  fetch(`${API_BASE}/api/autopilot/status`, { cache: "no-store" }).then(j);

export const getAutopilotConfig = (): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/autopilot/config`, { cache: "no-store" }).then(j);

export const setAutopilotConfig = (changes: Record<string, unknown>): Promise<unknown> =>
  fetch(`${API_BASE}/api/autopilot/config`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ changes, actor: "user" }),
  }).then(j);

export const autopilotScan = (mode?: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/autopilot/scan`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(mode ? { mode } : {}),
  }).then(j);

export const autopilotEmergencyStop = (): Promise<unknown> =>
  fetch(`${API_BASE}/api/autopilot/emergency-stop`, { method: "POST" }).then(j);

export const autopilotResumeStop = (): Promise<unknown> =>
  fetch(`${API_BASE}/api/autopilot/resume-stop`, { method: "POST" }).then(j);

export const getAutopilotCandidates = (): Promise<AutopilotCandidate[]> =>
  fetch(`${API_BASE}/api/autopilot/candidates`, { cache: "no-store" }).then(j);

export const getWhyThisTopic = (id: string): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/autopilot/candidates/${id}/why`, { cache: "no-store" }).then(j);

export const rejectCandidate = (id: string, scope: string, reason: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/autopilot/candidates/${id}/reject`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ scope, reason }),
  }).then(j);

// ================= Phase 5 — Ops / Production ================= //

export type OpsStatus = {
  version: string;
  env: string;
  dependencies: Record<string, { status: string; detail?: string; [k: string]: unknown }>;
  workers: {
    worker_id: string;
    type: string;
    hostname: string;
    version: string;
    status: string;
    last_heartbeat: string;
    started_at: string;
    current_job: string | null;
  }[];
  flags: Record<string, unknown>;
  backups: Record<string, unknown>;
  open_alerts: {
    id: string; severity: string; key: string; message: string;
    count: number; detail?: unknown; first_seen: string; last_seen: string;
  }[];
  dlq_open: number;
};

export type DlqRow = {
  id: string; job_kind: string; job_id: string; campaign_id: string | null;
  reason: string; error_type: string | null; attempts: number; status: string;
  created_at: string;
};

export const getOpsStatus = (): Promise<OpsStatus> =>
  fetch(`${API_BASE}/api/ops/status`, { cache: "no-store" }).then(j);

export const getOpsQueues = (): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/ops/queues`, { cache: "no-store" }).then(j);

export const getOpsDeepHealth = (force = false): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/ops/deep-health?force=${force ? "true" : "false"}`, { cache: "no-store" }).then(j);

export const opsScanStuck = (): Promise<{ recovered: unknown }> =>
  fetch(`${API_BASE}/api/ops/workers/scan-stuck`, { method: "POST" }).then(j);

export const getOpsAlerts = (): Promise<OpsStatus["open_alerts"]> =>
  fetch(`${API_BASE}/api/ops/alerts`, { cache: "no-store" }).then(j);

export const resolveOpsAlert = (id: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/ops/alerts/${id}/resolve`, { method: "POST" }).then(j);

export const getOpsDlq = (status = "OPEN"): Promise<DlqRow[]> =>
  fetch(`${API_BASE}/api/ops/dlq?status=${encodeURIComponent(status)}`, { cache: "no-store" }).then(j);

export const retryOpsDlq = (id: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/ops/dlq/${id}/retry`, { method: "POST" }).then(j);

export const resolveOpsDlq = (id: string): Promise<unknown> =>
  fetch(`${API_BASE}/api/ops/dlq/${id}/resolve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ status: "RESOLVED" }),
  }).then(j);

export const setOpsFlag = (flag: string, enabled: boolean, confirm: boolean): Promise<unknown> =>
  fetch(`${API_BASE}/api/ops/flags/${flag}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ enabled, confirm }),
  }).then(j);

export const getOpsBackups = (): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/ops/backups`, { cache: "no-store" }).then(j);

export const runOpsBackup = (kind = "full"): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/ops/backups/run`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ kind }),
  }).then(j);

export const verifyOpsBackup = (id: string): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/ops/backups/${id}/verify`, { method: "POST" }).then(j);

export const checkCostAnomaly = (): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/ops/cost-anomaly/check`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({}),
  }).then(j);

export const scanStorageIntegrity = (): Promise<Record<string, unknown>> =>
  fetch(`${API_BASE}/api/ops/storage/integrity`, { method: "POST" }).then(j);

// ================= Phase 6 — Multi-Brand / Portfolio / Monetization ================= //

const authHeaders = (): Record<string, string> => {
  if (typeof window === "undefined") return {};
  const key = window.localStorage?.getItem("acf_api_key");
  const ws = window.localStorage?.getItem("acf_workspace_id");
  const h: Record<string, string> = {};
  if (key) h["X-Api-Key"] = key;
  if (ws) h["X-Workspace-Id"] = ws;
  return h;
};

const jget = (path: string) =>
  fetch(`${API_BASE}${path}`, { cache: "no-store", headers: authHeaders() }).then(j);
const jpost = (path: string, body: unknown) =>
  fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify(body ?? {}),
  }).then(j);
const jput = (path: string, body: unknown) =>
  fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify(body ?? {}),
  }).then(j);
const jpatch = (path: string, body: unknown) =>
  fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify(body ?? {}),
  }).then(j);
const jdelete = (path: string) =>
  fetch(`${API_BASE}${path}`, { method: "DELETE", headers: authHeaders() }).then(j);

// ---- Phase 11: AI 연결 (provider credentials + safe probes) ---------------- //
export type ProviderVoice = {
  voice_id: string;
  name: string;
  labels?: Record<string, string>;
  category?: string;
  preview_url?: string;
};
export type ProviderRow = {
  provider: string;
  configured?: boolean;
  key_source?: "workspace" | "instance" | "env" | "none";
  last4?: string;
  status: string;
  configured_at?: string | null;
  last_checked_at?: string | null;
  last_success_at?: string | null;
  last_error_code?: string;
  meta?: Record<string, unknown>;
  enabled?: boolean;
  default_model?: string;
  detail?: string;
};
export const listProviders = (probe = false): Promise<{ providers: ProviderRow[]; workspace_scope: string }> =>
  jget(`/api/providers${probe ? "?probe=true" : ""}`);
export const setProviderKey = (provider: string, api_key: string): Promise<ProviderRow> =>
  jput(`/api/providers/${provider}/key`, { api_key });
export const deleteProviderKey = (provider: string): Promise<ProviderRow> =>
  jdelete(`/api/providers/${provider}/key`);
export const testProvider = (provider: string): Promise<Record<string, unknown>> =>
  jpost(`/api/providers/${provider}/test`, {});
export const elevenlabsVoices = (): Promise<{ voices: ProviderVoice[]; voice_id: string; voice_selected: boolean }> =>
  jget(`/api/providers/elevenlabs/voices`);
export const setElevenlabsVoice = (voice_id: string): Promise<Record<string, unknown>> =>
  jput(`/api/providers/elevenlabs/voice`, { voice_id });

export type WorkspaceRow = { id: string; name: string; slug: string; status: string; objective: string; role: string | null };
export type BrandRow = { id: string; workspace_id: string; name: string; slug: string; category: string; status: string; channels: number };
export type ChannelRow = {
  id: string; workspace_id: string; brand_id: string; name: string; platform: string;
  channel_type: string; lifecycle: string; status: string; autopilot_mode: string; daily_budget_usd: number;
  target_audience?: string;
  content_strategy?: {
    concept?: string; topics?: string[]; blocked_topics?: string[]; strict_topic_match?: boolean;
  };
};
export type PortfolioView = {
  workspace_id: string; objective: string;
  channels: Record<string, Record<string, unknown>>;
  totals: Record<string, unknown>;
};

export const listWorkspaces = (): Promise<WorkspaceRow[]> => jget("/api/workspaces");
export const getWorkspace = (id: string): Promise<Record<string, unknown>> => jget(`/api/workspaces/${id}`);
export const createWorkspace = (name: string): Promise<{ id: string; slug: string }> =>
  jpost("/api/workspaces", { name });
export const createBrand = (workspaceId: string, name: string): Promise<{ id: string; slug: string }> =>
  jpost("/api/brands", { workspace_id: workspaceId, name });

/** AUDIT-P8-004 — persist the setup wizard to the server: create the workspace
 *  and first brand via the existing tenant endpoints. Idempotent-ish: reuses a
 *  workspace whose name already matches. */
export async function finishSetup(input: {
  workspace: string; brand: string; sns: string[]; concept: string; topics: string[];
}): Promise<{
  workspace_id: string | null; brand_id: string | null; created: string[];
}> {
  const created: string[] = [];
  let workspace_id: string | null = null;
  let brand_id: string | null = null;
  const wsName = input.workspace.trim();
  if (wsName) {
    const existing = (await listWorkspaces().catch(() => [] as WorkspaceRow[]))
      .find((w) => w.name === wsName);
    if (existing) {
      workspace_id = (existing as { id: string }).id;
    } else {
      const w = await createWorkspace(wsName);
      workspace_id = w.id;
      created.push("workspace");
    }
  }
  const brName = input.brand.trim();
  if (brName && workspace_id) {
    const dup = (await listBrands(workspace_id).catch(() => [] as BrandRow[]))
      .find((b) => b.name === brName);
    if (dup) {
      brand_id = (dup as { id: string }).id;
    } else {
      const b = await createBrand(workspace_id, brName);
      brand_id = b.id;
      created.push("brand");
    }
  }
  if (brand_id) {
    const existingChannels = await listChannels(`?brand_id=${brand_id}`).catch(() => [] as ChannelRow[]);
    const channelTypes: Record<string, string> = {
      youtube_shorts: "YOUTUBE_SHORTS", tiktok: "TIKTOK", instagram_reel: "INSTAGRAM_REEL",
      x: "X", threads: "THREADS", linkedin: "LINKEDIN", naver_blog: "NAVER_BLOG",
    };
    for (const platform of input.sns) {
      const contentStrategy = {
        concept: input.concept,
        topics: input.topics,
        blocked_topics: [],
        strict_topic_match: true,
      };
      const existing = existingChannels.find((channel) => channel.platform === platform);
      if (existing) {
        await updateChannel(existing.id, { content_strategy: contentStrategy });
        continue;
      }
      await createChannel({
        brand_id,
        name: `${brName} · ${platform}`,
        platform,
        channel_type: channelTypes[platform] ?? platform.toUpperCase(),
        content_strategy: contentStrategy,
      });
      created.push(`channel:${platform}`);
    }
  }
  return { workspace_id, brand_id, created };
}
export const listBrands = (workspaceId?: string): Promise<BrandRow[]> =>
  jget(`/api/brands${workspaceId ? `?workspace_id=${workspaceId}` : ""}`);
export const listChannels = (params: string = ""): Promise<ChannelRow[]> =>
  jget(`/api/channels${params}`);
export const createChannel = (input: {
  brand_id: string; name: string; platform: string; channel_type?: string;
  content_strategy?: Record<string, unknown>;
}): Promise<{ id: string; lifecycle: string }> => jpost("/api/channels", input);
export const updateChannel = (id: string, patch: Record<string, unknown>): Promise<Record<string, unknown>> =>
  jpatch(`/api/channels/${id}`, patch);
export const getChannelHealth = (id: string): Promise<Record<string, unknown>> =>
  jget(`/api/channels/${id}/health`);
export const getChannelPlan = (id: string): Promise<Record<string, unknown>> =>
  jget(`/api/channels/${id}/plan`);
export const getChannelMonetization = (id: string): Promise<Record<string, unknown>> =>
  jget(`/api/channels/${id}/monetization`);
export const getChannelRevenue = (id: string): Promise<Record<string, unknown>> =>
  jget(`/api/channels/${id}/revenue`);
export const getPortfolio = (workspaceId: string): Promise<PortfolioView> =>
  jget(`/api/portfolio?workspace_id=${workspaceId}`);
export const getPortfolioRecs = (workspaceId: string): Promise<Record<string, unknown>[]> =>
  jget(`/api/portfolio/recommendations?workspace_id=${workspaceId}`);
export const allocatePortfolioBudget = (workspaceId: string, objective?: string, totalUsd?: number) =>
  jpost("/api/portfolio/budget", { workspace_id: workspaceId, objective, total_usd: totalUsd });
export const routeTopic = (workspaceId: string, topic: string, angle = "") =>
  jpost("/api/portfolio/route", { workspace_id: workspaceId, topic, angle });

// ================= Phase 7 — Content Governance ================= //

export type GovCase = {
  id: string; campaign_id: string; content_id: string | null; case_type: string;
  severity: string; state: string; decision: string; reason_codes: string[];
  hard_block: boolean; detail: Record<string, unknown>; created_at: string;
};
export type RightsRow = {
  id: string; asset_id: string; source_type: string; license_type: string;
  rights_status: string; commercial_use: string; attribution_required: boolean;
  expiration_at: string | null; ai_generated: boolean; watermark_detected: boolean;
  platform_restrictions: Record<string, unknown>;
};
export type PolicyStatusRow = {
  platform: string; rules: number; stale: boolean; unknown_rules: number; version: string | null;
};

export const listGovCases = (workspaceId?: string, state?: string): Promise<GovCase[]> =>
  jget(`/api/governance/cases?${new URLSearchParams({
    ...(workspaceId ? { workspace_id: workspaceId } : {}),
    ...(state ? { state } : {}),
  })}`);
export const govReviewQueue = (workspaceId?: string): Promise<GovCase[]> =>
  jget(`/api/governance/review${workspaceId ? `?workspace_id=${workspaceId}` : ""}`);
export const reviewGovCase = (caseId: string, approve: boolean, note = "") =>
  jpost(`/api/governance/cases/${caseId}/review`, { approve, note });
export const govCheck = (campaignId: string, runMode = "FULL_AUTO") =>
  jpost("/api/governance/check", { campaign_id: campaignId, run_mode: runMode });
export const govRepair = (campaignId: string, reasonCode: string, contentId?: string) =>
  jpost("/api/governance/repair", { campaign_id: campaignId, reason_code: reasonCode, content_id: contentId });
export const listRights = (campaignId: string): Promise<RightsRow[]> =>
  jget(`/api/rights?campaign_id=${campaignId}`);
export const listManifests = (campaignId: string): Promise<Record<string, unknown>[]> =>
  jget(`/api/rights/manifests?campaign_id=${campaignId}`);
export const policyStatus = (): Promise<PolicyStatusRow[]> => jget("/api/policy/status");

// ============ Cross-Phase Intelligence Upgrade — URL learning / prompts / platform selection ============ //

export type ReferenceRow = {
  id: string; url: string; canonical_url: string; source_type: string; support_level: string;
  purpose: string; resolved_purpose: string; scope: string; status: string; title: string;
  publisher: string; quality_score: number; trust_score: number; relevance_score: number;
  freshness_score: number; learning_weight: number; rights_status: string;
  injection_flag: boolean; injection_detail: Record<string, unknown>; language: string;
  topic_cluster: string; error: string; created_at: string | null;
};
export type LearningDashboard = {
  total_references: number; ready_references: number; dataset_records: number;
  video_references: number; writing_references: number; prompt_blueprints: number;
  learned_skills: number; creative_recipes: number; collections: number;
  learning_cost_usd: number; last_learning_run: string | null;
};
export type PromptBlueprintRow = {
  id: string; agent_type: string; purpose: string; instructions: string[]; constraints: string[];
  positive_patterns: string[]; negative_patterns: string[]; status: string; version: number;
  confidence: number; sample_size: number; source_diversity: number; consistency: number;
  platforms: string[]; content_types: string[];
};
export type LearnedSkillRow = {
  id: string; agent_type: string; skill_category: string; rule: string; confidence: number;
  sample_size: number; status: string; evidence_ids: string[]; platform: string; content_type: string;
};
export type LearningGaps = {
  library_counts: Record<string, number>;
  weak_dimensions: Record<string, number>;
  recommendations: { reason: string; recommended_dataset: string; have: number; target: number; priority: string }[];
};
export type PlatformSelection = Record<string, Record<string, string>>;
export type CostPreview = {
  campaign_id: string;
  platforms: Record<string, { content_pieces: number; media_variants: number; publish_jobs: number; est_usd: number | string }>;
  totals: { content_pieces: number; media_variants: number; publish_jobs: number };
  total_est_usd: number | string; note: string;
};

export const addReferences = (body: {
  urls: string[]; execution_mode?: string; workspace_id?: string; topic?: string;
  purpose?: string; scope?: string; collection_id?: string; run?: boolean;
}): Promise<{ job_id: string; status: string; result: Record<string, unknown>; references: ReferenceRow[] }> =>
  jpost("/api/references", body);
export const listReferences = (workspaceId?: string, status?: string): Promise<ReferenceRow[]> =>
  jget(`/api/references?${new URLSearchParams({
    ...(workspaceId ? { workspace_id: workspaceId } : {}),
    ...(status ? { status } : {}),
  })}`);
export const retryFailedReferences = (workspaceId?: string): Promise<{ retried: number; ready: number; failed: number }> =>
  jpost("/api/references/retry-failed", workspaceId ? { workspace_id: workspaceId } : {});
export const getReference = (id: string): Promise<ReferenceRow & { analyses: Record<string, unknown> }> =>
  jget(`/api/references/${id}`);
export const learningDashboard = (workspaceId?: string): Promise<LearningDashboard> =>
  jget(`/api/learning${workspaceId ? `?workspace_id=${workspaceId}` : ""}`);
export const learningGaps = (workspaceId?: string): Promise<LearningGaps> =>
  jget(`/api/learning/gaps${workspaceId ? `?workspace_id=${workspaceId}` : ""}`);
export const listBlueprints = (workspaceId?: string, agentType?: string): Promise<PromptBlueprintRow[]> =>
  jget(`/api/learning/prompts?${new URLSearchParams({
    ...(workspaceId ? { workspace_id: workspaceId } : {}),
    ...(agentType ? { agent_type: agentType } : {}),
  })}`);
export const getBlueprint = (id: string): Promise<PromptBlueprintRow & { evidence: Record<string, unknown>[] }> =>
  jget(`/api/learning/prompts/${id}`);
export const testBlueprint = (id: string, body: Record<string, unknown> = {}) =>
  jpost(`/api/learning/prompts/${id}/test`, body);
export const promoteBlueprint = (id: string, toStatus: string, actor = "user") =>
  jpost(`/api/learning/prompts/${id}/promote`, { to_status: toStatus, actor });
export const rollbackBlueprint = (id: string) => jpost(`/api/learning/prompts/${id}/rollback`, {});
export const listSkills = (workspaceId?: string, agentType?: string): Promise<LearnedSkillRow[]> =>
  jget(`/api/learning/skills?${new URLSearchParams({
    ...(workspaceId ? { workspace_id: workspaceId } : {}),
    ...(agentType ? { agent_type: agentType } : {}),
  })}`);
export const platformContentTypes = (): Promise<{ content_types: Record<string, string[]>; presets: string[] }> =>
  jget("/api/platform-selection/content-types");
export const getPlatformSelection = (campaignId: string): Promise<{ campaign_id: string; selection: PlatformSelection; cost_preview: CostPreview }> =>
  jget(`/api/platform-selection/${campaignId}`);
export const setPlatformSelection = (body: { campaign_id: string; selection?: PlatformSelection; preset?: string }) =>
  jpost("/api/platform-selection", body);
export const composeCampaign = (body: {
  topic?: string; execution_mode: string; reference_urls?: string[];
  platform_selection?: PlatformSelection; preset?: string; workspace_id?: string; audience_goal?: string;
}): Promise<{ execution_mode: string; campaign_id: string | null; pipeline_started: boolean; generate_platforms: string[]; learning: Record<string, unknown> }> =>
  jpost("/api/campaigns/compose", body);

// ================= Phase 8 — Local AI / Model Router / Cost / Content Library ================= //

export type LocalAIStatus = {
  ollama_enabled: boolean; base_url: string; default_model: string;
  allow_cloud_fallback: boolean; local_only: boolean;
  status: "CONNECTED" | "NOT_RUNNING" | "NO_MODEL" | "DEGRADED" | "DISABLED";
  models: string[]; version: string | null; reason?: string;
};
export type ModelEntry = {
  model_id: string; provider: string; family: string; kind: string; enabled: boolean;
  health: string; vision: boolean; tools: boolean; context_tokens: number;
  latency_class: string; quality_class: string; pricing_state: string;
  input_usd_per_1k: number; output_usd_per_1k: number; benchmark_state: string;
};
export type RoutingDecision = {
  task_type: string; agent_type: string; tier: string; selected_model: string;
  provider: string; fallback_chain: string[]; reason: string; deterministic: boolean;
  estimated_cost: { usd: number | null; state: string; model?: string; local?: boolean };
};
export type CostEstimate = {
  quality_preset: string; execution_mode: string; generate_platforms: string[];
  publish_platforms: string[]; categories: Record<string, {
    usd: number | null; state: string; local_processing?: boolean; detail?: Record<string, unknown>;
  }>;
  total_known_usd: number; total_known_krw: number; has_unknown: boolean;
  total_state: string; note: string;
};
export type LibraryCard = {
  campaign_id: string; topic: string; workspace_id: string | null; brand_id: string | null;
  channel_id: string | null; created_at: string | null; status: string;
  execution_mode: string | null; legacy: boolean; platforms: string[]; platform_count: number;
  content_types: string[]; governance: string; publish_state: string; has_video: boolean;
  video_playable: boolean; duration: number | null; thumbnail_path: string | null;
  is_demo: boolean; views: number | null; revenue_actual: number | null;
  revenue_estimated: number | null; cost_usd: number | null; currency: string;
};
export type LibraryPage = { total: number; page: number; page_size: number; pages: number; items: LibraryCard[] };

export const localAIStatus = (): Promise<LocalAIStatus> => jget("/api/local-ai/status");
export const localAIPing = () => jpost("/api/local-ai/ping", {});
export const listAIModels = (): Promise<ModelEntry[]> => jget("/api/models?refresh=true");
export const previewRoute = (body: Record<string, unknown>): Promise<RoutingDecision> =>
  jpost("/api/models/route", body);
export const benchmarkModel = (modelId?: string) =>
  jpost("/api/models/benchmark", modelId ? { model_id: modelId } : {});
export const modelPerformance = (taskType?: string) =>
  jget(`/api/models/performance${taskType ? `?task_type=${taskType}` : ""}`);
export const routingTelemetry = (campaignId?: string) =>
  jget(`/api/routing/telemetry${campaignId ? `?campaign_id=${campaignId}` : ""}`);
export const estimateCost = (body: {
  selection: Record<string, Record<string, string>>; quality_preset?: string;
  execution_mode?: string; reference_count?: number;
}): Promise<CostEstimate> => jpost("/api/cost/estimate", body);

export const contentLibrary = (params: Record<string, string> = {}): Promise<LibraryPage> =>
  jget(`/api/library?${new URLSearchParams(params)}`);
export const libraryStats = (workspaceId?: string) =>
  jget(`/api/library/stats${workspaceId ? `?workspace_id=${workspaceId}` : ""}`);
export const contentDetail = (campaignId: string): Promise<Record<string, unknown>> =>
  jget(`/api/library/${campaignId}`);
export const deleteContent = (campaignId: string): Promise<{ ok: boolean; deleted_records: number }> =>
  jdelete(`/api/library/${campaignId}`);
export const addPlatformToContent = (campaignId: string, platform: string, mode = "GENERATE_AND_PUBLISH") =>
  jpost(`/api/library/${campaignId}/add-platform`, { platform, mode });
export const contentVideoUrl = (campaignId: string) => `${API_BASE}/api/library/${campaignId}/media/video`;

export type CalendarJob = {
  job_id: string; platform: string; campaign_id: string; scheduled_at: string | null;
  timezone: string; status: string; title: string;
};
export const publishCalendar = (days = 45): Promise<CalendarJob[]> =>
  jget(`/api/publishing/calendar?days=${days}`);

// ---- Phase 10: AI Support Snapshot + kill switches ----
export type SupportSnapshot = {
  product: string; version: string; environment: string; generated_at: string; timezone: string;
  overall_health: "OK" | "DEGRADED" | "ERROR";
  kill_switches: Record<string, boolean>;
  system: Record<string, { status?: string; [k: string]: unknown }>;
  current_jobs: Array<Record<string, unknown>>;
  focus_campaign_id: string | null;
  pipeline: Array<{ step: string; state: string }>;
  model_routing: { local_only: boolean; cloud_fallback_enabled: boolean;
    last_route: Record<string, unknown> | null };
  ollama: Record<string, unknown>;
  workers_queues: Record<string, unknown>;
  last_error: Record<string, unknown> | null;
  recent_events: Array<{ at: string; event: string; campaign_id: string | null }>;
  governance: Record<string, unknown>;
  platform_selection: Array<{ platform: string; content_type: string; mode: string }>;
  cost: Record<string, unknown>;
  learning: Record<string, unknown> | null;
  test: Record<string, unknown> | null;
  scope: string;
};

export const supportSnapshot = (params: Record<string, string> = {}): Promise<SupportSnapshot> =>
  jget(`/api/support/snapshot${Object.keys(params).length ? `?${new URLSearchParams(params)}` : ""}`);
export const supportSnapshotText = (params: Record<string, string> = {}): Promise<string> =>
  fetch(`${API_BASE}/api/support/snapshot.txt${Object.keys(params).length ? `?${new URLSearchParams(params)}` : ""}`,
    { cache: "no-store", headers: authHeaders() }).then((r) => r.text());
export const supportVersion = (): Promise<{ product: string; version: string; release_name: string; environment: string }> =>
  jget("/api/support/version");

export const toggleKillSwitch = (flag: string, enabled: boolean) =>
  jpost(`/api/ops/flags/${flag}`, { enabled, confirm: true });
