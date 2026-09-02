# ANALYTICS CAPABILITIES

Metric availability checked against each platform's official developer docs on
**2026-08-31**. Machine-readable copy: `backend/app/analytics/capabilities.json`
(served at `GET /api/analytics/capabilities`). Re-verify at implementation time.

**Availability vocabulary** — a value the API does not return is **never stored as 0**:
`AVAILABLE` · `UNAVAILABLE` (API has no such metric) · `NOT_AUTHORIZED` (needs a
scope/tier/review the account lacks) · `NOT_APPLICABLE` (metric is meaningless for
this content type) · `NOT_READY` (too soon after publish).

**Import sources**: `PLATFORM_API` · `MANUAL_IMPORT` (creator dashboard) ·
`CSV_IMPORT` · `ESTIMATE`.

Every platform below is **MOCK** this phase (no real analytics credentials).

| Platform | Official API | Scope | Account req. | Historical | Revenue | Delay | Key limitation |
|---|---|---|---|---|---|---|---|
| **YouTube** | YouTube Analytics API v2 + Data API v3 | `yt-analytics.readonly`, `yt-analytics-monetary.readonly` | channel owner; revenue needs YPP/monetization | yes | **yes** (scoped) | ~48h revenue, else near-real-time | `estimatedRevenue` → `NOT_AUTHORIZED` without the monetary scope + monetization; Shorts & long-form reported separately |
| **TikTok** | Display API (own Business account) | `user.info.stats`, `video.list` | TikTok Business; own content only | no | no | hours | **watch time, retention, traffic sources, demographics, revenue are NOT in the API** → `UNAVAILABLE`; creator-dashboard CSV → `MANUAL_IMPORT` |
| **Instagram** | Media Insights (Graph API v22+) | `instagram_business_manage_insights` | Instagram Professional | yes | no | near-real-time | `impressions`/`video_views` deprecated (use `views`); `profile_views`/`website_clicks` deprecated; no organic revenue API |
| **Facebook** | Graph API Page/Reels insights | `pages_read_engagement`, `read_insights` | Facebook Page (admin) | yes | no | ~24h | metric **names differ from Instagram** (`post_impressions`, `post_video_views`, `blue_reels_play_count`, `post_video_avg_time_watched`); in-stream revenue is a separate limited report → `NOT_AUTHORIZED` |
| **Threads** | Threads API post & account insights | `threads_manage_insights` | Threads account; personal unlocks demographics at 100 followers | yes | no | near-real-time | per-post: `views/likes/replies/reposts/quotes/shares`; no watch time / retention / revenue |
| **X** | X API v2 `public_metrics` (+ organic needs tier) | `tweet.read`, `users.read` | **paid API access** (Free tier = write-only, no reads) | no | no | near-real-time | `impression_count` / organic metrics need Basic+ tier + user context → `NOT_AUTHORIZED`; public: like/reply/repost/quote/bookmark counts |
| **Pinterest** | Pinterest API v5 pin analytics | `pins:read`, `user_accounts:read` | Pinterest account; **TRIAL access** owner-only, heavy limits | yes | no | ~24–48h | `IMPRESSION/SAVE/PIN_CLICK/OUTBOUND_CLICK/VIDEO_MRC_VIEW/VIDEO_AVG_WATCH_TIME`; no revenue |
| **LinkedIn** | Organization Share Statistics (Community Management API) | `r_organization_social`, `rw_organization_admin` | Organization page + **partner review**; member (personal) analytics ~unavailable | yes | no | ~24h | **APP_REVIEW_REQUIRED**; personal-profile post analytics not available → all `NOT_AUTHORIZED` until review |
| **Naver Blog** | none verified | — | Naver account | no | no | n/a | no official post-analytics API; visitor/dwell/referral only via manual **CSV_IMPORT** — never synthesised as API data |
| **Naver Clip** | none | — | Naver account (mobile) | no | no | n/a | no API; manual import only |

## How the code honours this
- `MetricCatalog` (`app/analytics/metric_catalog.py`) maps each platform's raw API
  metric names → normalized names; `normalize()` stamps every metric with its
  capability-derived availability. A missing value is `None` + a status, never `0`.
- Each snapshot keeps **both** the `raw_payload` (never deleted) and the
  normalized columns.
- `AnalyticsProvider.get_revenue_metrics` returns a `MetricValue` with the correct
  availability rather than a number when revenue is not exposed.
- The real HTTP client (`analytics_client=http`) raises `PERMISSION_MISSING` until
  per-platform adapters + credentials are wired — it never fabricates metrics.
