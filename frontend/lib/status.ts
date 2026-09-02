/**
 * Central status vocabulary. Every backend enum that reaches the UI is mapped
 * here to { ko label, tone, icon }. Screens must not hand-roll colour maps.
 *
 * DESIGN.md carries no amber/red. "warn" therefore uses brand-secure (muted
 * lavender-grey) and "block"/"error" lean on a strong border + icon + weight,
 * never colour alone (accessibility: state is never colour-only).
 */

export type Tone = "ok" | "run" | "wait" | "warn" | "block" | "error" | "neutral";

export type StatusMeta = {
  ko: string;
  tone: Tone;
  icon: IconName;
};

export type IconName =
  | "check"
  | "activity"
  | "clock"
  | "alert"
  | "lock"
  | "x"
  | "dot"
  | "pause"
  | "calendar"
  | "send"
  | "edit";

const M = (ko: string, tone: Tone, icon: IconName): StatusMeta => ({ ko, tone, icon });

/** keyed by UPPERCASED backend value */
const TABLE: Record<string, StatusMeta> = {
  // --- pipeline / step / campaign status ---
  SUCCESS: M("완료", "ok", "check"),
  DONE: M("완료", "ok", "check"),
  COMPLETED: M("완료", "ok", "check"),
  RUNNING: M("진행 중", "run", "activity"),
  IN_PROGRESS: M("진행 중", "run", "activity"),
  RETRY: M("재시도", "warn", "alert"),
  WAITING: M("대기", "wait", "clock"),
  PENDING: M("대기", "wait", "clock"),
  QUEUED: M("대기", "wait", "clock"),
  FAILED: M("오류", "error", "x"),
  ERROR: M("오류", "error", "x"),
  BLOCKED: M("차단됨", "block", "lock"),
  CANCELLED: M("취소됨", "neutral", "x"),

  // --- governance case state ---
  PASS: M("통과", "ok", "check"),
  PASS_WITH_REQUIREMENTS: M("조건부 통과", "ok", "check"),
  FIX_REQUIRED: M("수정 필요", "warn", "alert"),
  HUMAN_REVIEW: M("검토 필요", "warn", "alert"),
  RESOLVED: M("처리됨", "neutral", "check"),

  // --- library governance summary ---
  OK: M("정상", "ok", "check"),
  REVIEW: M("검수 필요", "warn", "alert"),
  NOT_APPLICABLE: M("해당 없음", "neutral", "dot"),
  NONE: M("없음", "neutral", "dot"),

  // --- library publish state ---
  PUBLISHED: M("게시됨", "ok", "send"),
  SCHEDULED: M("예약됨", "run", "calendar"),
  DRAFT: M("초안", "neutral", "edit"),
  NOT_PUBLISHED: M("미게시", "wait", "dot"),

  // --- system / provider health ---
  DEGRADED: M("주의 필요", "warn", "alert"),
  READY: M("정상", "ok", "check"),
  UP: M("정상", "ok", "check"),
  CONNECTED: M("연결됨", "ok", "check"),
  ALIVE: M("정상", "ok", "check"),
  SLOW: M("느림", "warn", "alert"),
  MOCK: M("모의(MOCK)", "warn", "alert"),
  WARNING: M("주의 필요", "warn", "alert"),
  NOT_CONFIGURED: M("설정 필요", "wait", "alert"),
  DISCONNECTED: M("연결 필요", "warn", "alert"),
  UNKNOWN: M("확인 불가", "neutral", "dot"),

  // --- severity ---
  INFO: M("정보", "neutral", "dot"),
  LOW: M("낮음", "neutral", "dot"),
  MEDIUM: M("보통", "warn", "alert"),
  HIGH: M("높음", "warn", "alert"),
  CRITICAL: M("심각", "error", "x"),

  // --- platform selection mode ---
  DISABLED: M("사용 안 함", "neutral", "dot"),
  GENERATE_ONLY: M("생성만", "warn", "alert"),
  FULL: M("전체", "ok", "check"),
};

export function statusMeta(value: string | null | undefined): StatusMeta {
  if (!value) return M(String(value ?? "-"), "neutral", "dot");
  return TABLE[value.toUpperCase()] ?? M(value, "neutral", "dot");
}

/** internal platform / content-type keys -> Korean display name (user-facing) */
export const PLATFORM_KO: Record<string, string> = {
  youtube: "YouTube",
  youtube_long: "YouTube",
  youtube_shorts: "YouTube Shorts",
  tiktok: "TikTok",
  instagram: "Instagram",
  instagram_reel: "Instagram 릴스",
  instagram_carousel: "Instagram 캐러셀",
  facebook: "Facebook",
  facebook_reel: "Facebook 릴스",
  threads: "Threads",
  x: "X",
  pinterest: "Pinterest",
  linkedin: "LinkedIn",
  naver_blog: "네이버 블로그",
  naver_clip: "네이버 클립",
};
export function platformKo(key: string): string {
  return PLATFORM_KO[key?.toLowerCase?.()] ?? key;
}

/** tone -> tailwind text colour (token-backed) */
export const TONE_TEXT: Record<Tone, string> = {
  ok: "text-success",
  run: "text-primary",
  wait: "text-ink-subtle",
  warn: "text-brand-secure",
  block: "text-ink",
  error: "text-ink",
  neutral: "text-ink-subtle",
};

/** tone -> dot colour */
export const TONE_DOT: Record<Tone, string> = {
  ok: "bg-success",
  run: "bg-primary",
  wait: "bg-ink-tertiary",
  warn: "bg-brand-secure",
  block: "bg-ink-subtle",
  error: "bg-ink-subtle",
  neutral: "bg-ink-tertiary",
};
