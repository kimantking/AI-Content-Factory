# SNS PLATFORM SELECTION

> Code: `backend/app/intel/platform_selection.py`. Tables:
> `campaign_platform_selections`, `platform_presets`. Wired into
> `publishing/service.create_jobs_for_campaign` and `publishing/engine.run_publish_job`.

## Three-state model (per platform / content-type)

| mode | generate content + media | create PublishJob | remote API call |
|---|---|---|---|
| `DISABLED` | **no** | no | no |
| `GENERATE_ONLY` | yes | **no** | no |
| `GENERATE_AND_PUBLISH` | yes | yes | yes (if governance ALLOW) |

**Check off = generation skip**, not just publish skip. `set_selection` writes
`Campaign.platforms` = the non-DISABLED platform list, which is the only list the
Phase 1-B media pipeline builds. A DISABLED platform therefore produces zero
`PlatformContent`, zero media variants, zero thumbnails, zero jobs, zero API calls.

## Content types (spec §AQ, `CONTENT_TYPES`)

YouTube Shorts/Long · TikTok Video · Instagram Reels/Feed/Carousel · Facebook
Reels · Threads Text/Thread/Image/Video · X Post/Thread/Image/Video · Pinterest
Image Pin/Video Pin · LinkedIn Text/Image/Video/Document · Naver Blog · Naver Clip.

## Router + gates

- `platforms_to_generate` / `platforms_to_publish` / `mode_for` — resolve the
  current selection (falls back to `Campaign.platforms` as GENERATE_AND_PUBLISH
  when no explicit rows exist, e.g. Autopilot campaigns).
- `create_jobs_for_campaign` — creates a job **only** for GENERATE_AND_PUBLISH
  platforms, and returns `[]` entirely for a LEARN_ONLY campaign.
- **Publisher final gate** (`run_publish_job`) — re-reads the selection right
  before the remote call. A platform turned off (or set to GENERATE_ONLY) **after
  a job was queued** → job `BLOCKED`, `last_error_type = PLATFORM_DESELECTED`, no
  API call (spec §AY). Fails closed on any selection error.
- `publish_allowed` runs both at job creation and at the final gate.

## User override is a hard rule (spec §AT)

`user_explicit=True` sets `Campaign.platform_selection_locked`. `autopilot_may_enable`
returns `False` for a platform the user explicitly disabled (or did not select) on
a locked campaign — Autopilot cannot turn it back on.

## Selection hierarchy

Campaign user override → Channel default → Brand default → Workspace default.
(Currently: campaign rows win; absence falls back to `Campaign.platforms`. Channel/
Brand/Workspace defaults are stored via `platform_presets` and applied at compose
time.)

## Presets (spec §AV)

Builtin: `shortform_all` (YT Shorts + TikTok + IG Reels + FB Reels + Naver Clip),
`text_all` (Threads + X + LinkedIn + Naver Blog), `youtube_only`. Users save custom
presets (`POST /api/platform-presets`). "전체 선택 / 전체 해제" and All-Off are
supported; All-Off + LEARN_ONLY still learns normally.

## Re-enable

Turning a platform back on reuses existing valid assets; `create_jobs_for_campaign`
is idempotent by `idempotency_key`, so no duplicate PublishJob is created.

## Cost preview (spec §BB — honest)

`cost_preview` returns exact structural counts (content pieces / media variants /
publish jobs per platform) and a dollar figure of **`PRICING_UNKNOWN`** whenever a
media provider is MOCK (which is currently always). No fabricated numbers.
