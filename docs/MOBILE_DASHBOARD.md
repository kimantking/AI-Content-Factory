# Mobile Dashboard (Phase 10)

Same Next.js product, mobile-optimised — **not** a shrunk desktop. Shell:
`components/AppShell.tsx`.

## Navigation (§28)
Bottom tab bar (`md:hidden`, `grid-cols-5`): **[홈] [콘텐츠] [＋만들기] [검수] [더보기]**.
`＋만들기` is the raised accent action. "더보기" opens a bottom sheet:
AI 학습실 · 캘린더 · 채널 · 분석 · 오토파일럿 · 자료실 · 계정 · 로컬 AI ·
**AI 지원 스냅샷** · 시스템 · 상태.

## Priority (§27)
`Create → Current Work → Review → Recent Contents → Notifications`.

## What works on mobile (§29-§41)
* **Quick Create** — full: Topic, Reference URLs, Execution Mode, SNS selection,
  Quality, Cost Preview, [콘텐츠 만들기]. No PC required to create content.
* **SNS selection** — touch targets ≥ 40 px; advanced formats in an
  accordion / bottom sheet.
* **Content Library** — card view first (thumbnail / title / platform / status /
  date); search + filter + preview. No horizontal-scrolling desktop table.
* **Content Detail** — tabbed sections (Overview / Preview / Script / Platforms /
  Governance / Publishing / Analytics / History).
* **Video Preview** — 9:16 and 16:9 render correctly; **poster first, no autoplay**
  of full video in the library.
* **Review** — watch video, read script, check governance, Approve / Reject /
  Hold / 수정 요청. Sticky bottom actions; publish is never a mis-tap away; double
  tap → 0 duplicate effect (idempotency key, server-side).
* **Calendar** — agenda / day view.
* **Analytics** — headline: Views / Growth / Revenue / Cost / Profit / Published;
  detailed charts one level down.
* **Autopilot** — view today's plan, Approve / Exclude / Pause; FULL_AUTO needs
  confirmation.
* **Emergency controls (§40)** — an authorized user can, from mobile, toggle
  GLOBAL_PUBLISH_PAUSE / GLOBAL_PAID_PROVIDER_PAUSE / EMERGENCY_STOP (and pause a
  channel / autopilot) from `/support` and `/admin`. No need to find a PC.
* **Notifications** — actionable only: publish failed, review needed, budget
  warning, SNS auth expired, Ollama error, worker error.

## Cross-device (§42)
Same backend, same DB, same `Campaign` object. A desktop-created campaign is
identical on mobile (stage / progress / cost / governance); a mobile Approve is
visible on a desktop refresh. No critical state lives only in React/local state.
Verified: `tests/phase10/test_release_e2e.py`.

## Viewports verified (§24)
768×1024 / 430×932 / 390×844 / 375×667 via `next build` + HTTP-level journeys.
