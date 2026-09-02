# PLATFORM CAPABILITIES

Official-API facts checked against each platform's **developer documentation** on
**2026-08-31**. Old blogs/repos are not authoritative — re-verify at
implementation time. Machine-readable copy: `backend/app/publishing/capabilities.json`
(served at `GET /api/publishing/capabilities`).

`publishing_status` vocabulary: `SUPPORTED · AUTH_REQUIRED · APP_REVIEW_REQUIRED ·
ACCOUNT_TYPE_REQUIRED · LIMITED · MANUAL_ONLY · NOT_SUPPORTED · UNKNOWN`.
`implementation_status`: `CODE_COMPLETE · MOCK_TESTED · REAL_AUTH_TESTED ·
REAL_UPLOAD_TESTED · REAL_PUBLISH_TESTED · NOT_AVAILABLE`. **Every platform below
is `MOCK_TESTED` — no real credentials were supplied this phase.**

---

## YouTube
- **Official API:** YouTube Data API v3 — `videos.insert` with the resumable upload protocol.
- **Auth / scopes:** OAuth 2.0 · `youtube.upload`, `youtube.readonly`.
- **Content:** video (long-form + Shorts). No image / carousel / text.
- **Scheduling:** yes (`publishAt` with `privacyStatus=private`). **Analytics:** yes. **Webhook:** no (poll processing).
- **App review:** yes — unverified API projects created after 2020-07-28 upload as **PRIVATE** until an API audit; `videos.insert` has its own **100 uploads/day** quota bucket.
- **Account requirement:** Google account with a YouTube channel.
- **publishing_status:** `AUTH_REQUIRED` → `APP_REVIEW_REQUIRED` for public visibility.
- **Decision:** `YouTubePublisher` on Data API v3 + resumable upload; long-form and Shorts share infra with separate validation profiles; surface audit/verification state in Account Health.

## TikTok
- **Official API:** Content Posting API — `video.publish` (Direct Post) vs `video.upload` (inbox).
- **Auth / scopes:** OAuth 2.0 · `video.upload`, `video.publish`.
- **Content:** video, photo. **Scheduling:** no. **Analytics:** yes. **Webhook:** yes.
- **App review:** yes — Direct Post (`video.publish`) needs an **app audit** (~1–4 weeks); unaudited clients post **PRIVATE** only. `video.upload` lands in the user's **inbox for manual confirmation**. Query Creator Info for allowed privacy / comment / duet / stitch / max-duration before posting.
- **publishing_status:** `APP_REVIEW_REQUIRED` (Direct Post). Inbox flow → `WAITING_USER_ACTION`.
- **Decision:** `TikTokPublisher` implements both flows; defaults to `video.upload` (→ `WAITING_USER_ACTION`) until the app is audited; never forces unsupported options; never bypasses the consent flow.

## Instagram
- **Official API:** Instagram Platform Content Publishing — media **container → media_publish**.
- **Auth / scopes:** OAuth 2.0 (Meta) · `instagram_business_basic`, `instagram_business_content_publish`.
- **Content:** image, video, Reel, carousel. **Scheduling:** yes. **Analytics:** yes. **Webhook:** yes.
- **App review:** yes (for the publish permission). **Account:** Instagram **Professional** (Business/Creator); the Facebook-login path also needs a linked Facebook Page + Business.
- **Limits:** 100 API-published posts / rolling 24 h (carousel = 1). Reel: 9:16, 5–90 s, H.264/HEVC. Carousel = create child containers, wait `FINISHED`, then parent publish. Media from a public URL.
- **publishing_status:** `ACCOUNT_TYPE_REQUIRED`.
- **Decision:** `InstagramPublisher` on the container flow via a shared `MetaClient`; carousel aborts the parent unless all children are `FINISHED`; verify permalink.

## Facebook
- **Official API:** Graph API — Page feed / Page Video / Reels.
- **Auth / scopes:** OAuth 2.0 (Meta) Page access token · `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
- **Content:** text, image, video, carousel. **Scheduling:** yes. **Analytics:** yes. **Webhook:** yes.
- **App review:** yes (`pages_manage_posts`). **Account:** a Facebook **Page** (admin) — publishes as the Page, not a personal profile (personal-profile publishing is not available via API).
- **publishing_status:** `AUTH_REQUIRED`.
- **Decision:** `FacebookPublisher` on Page endpoints via the shared `MetaClient`; publisher logic separate from Instagram.

## Threads
- **Official API:** Threads API (`graph.threads.net`) — container → `threads_publish`.
- **Auth / scopes:** OAuth 2.0 (Meta) · `threads_basic`, `threads_content_publish` (+ `threads_manage_insights` for analytics).
- **Content:** text, image, video (≤ 5 min), carousel (≤ 10). Multi-post threads = **reply chain via `reply_to_id`**, sequential — no batch endpoint. **Scheduling:** no. **Analytics:** yes. **Webhook:** no.
- **App review:** Tech Provider Verification for the app. **Limit:** 250 posts / 24 h.
- **publishing_status:** `AUTH_REQUIRED`.
- **Decision:** `ThreadsPublisher` on the container flow; multi-post = root publish then reply chain, storing every remote id; uses the Phase 1-B native Threads content object, not the IG caption.

## X
- **Official API:** X API v2 — `POST /2/tweets`, media upload v2.
- **Auth / scopes:** OAuth 2.0 PKCE (user context) · `tweet.write`, `tweet.read`, `users.read`, `offline.access`, `media.write`.
- **Content:** text, image, video. Thread = reply chain (`in_reply_to_tweet_id`). **Scheduling:** no. **Analytics:** yes. **Webhook:** no.
- **Pricing / access:** free tier **discontinued**; pay-per-use is the current default for new devs (≈ **$0.015 per post created**, higher with a link); legacy Basic/Pro monthly tiers remain for existing subscribers. **Pricing is volatile → config only (`X_COST_PER_POST_USD`), `PRICING_UNKNOWN` if unset — never invent a number.**
- **publishing_status:** `AUTH_REQUIRED` (paid API access).
- **Decision:** `XPublisher` for post/reply/thread + media; record access level + per-post cost in the provider capability + cost log.

## Pinterest
- **Official API:** Pinterest API v5 — `POST /v5/pins`; video pins via `/v5/media` multi-step upload.
- **Auth / scopes:** OAuth 2.0 · `boards:read`, `pins:read`, `pins:write`.
- **Content:** image pin, video pin, carousel. Every pin needs a `board_id`. **Scheduling:** no. **Analytics:** yes. **Webhook:** no.
- **App review:** not required, but **new apps start in TRIAL access** (owner account only, heavy rate limits) until upgraded to STANDARD.
- **publishing_status:** `LIMITED`.
- **Decision:** `PinterestPublisher` on v5; require board selection; video = register media then create pin; surface TRIAL vs STANDARD in Account Health; use the Phase 1-B Pinterest-native asset.

## LinkedIn
- **Official API:** LinkedIn Posts API (part of the Community Management API).
- **Auth / scopes:** OAuth 2.0 · `w_member_social` (member) / `w_organization_social` (organization).
- **Content:** text, image, video, document. **Scheduling:** no. **Analytics:** yes. **Webhook:** no.
- **App review:** yes — a verified app with the **"Share on LinkedIn"** product for member posts; **organization** posting needs the Community Management API (registered company + verified Page + **two-tier partner review**). `r_member_social` is **closed** to new access.
- **publishing_status:** `APP_REVIEW_REQUIRED`.
- **Decision:** `LinkedInPublisher` for text/image/video/document; report `AUTH_REQUIRED` (member) or `APP_REVIEW_REQUIRED` (organization) accurately in Account Health.

## Naver Blog
- **Official API:** **None verified.** Naver's Login Open API historically exposed a blog-write endpoint; current availability is **UNKNOWN**.
- **publishing_status:** `MANUAL_ONLY`.
- **Decision:** **No fake publisher.** `NaverBlogPublisher` returns `WAITING_USER_ACTION` and emits a `NAVER_BLOG_PACKAGE` (title, HTML/Markdown article, images + placements, tags, sources, metadata). Browser assist stays behind `NAVER_BROWSER_ASSIST=false` and **never bypasses CAPTCHA / identity / security verification** (→ `WAITING_USER_ACTION`). Add a real adapter behind a flag only if an official write API is confirmed at implementation time.

## Naver Clip
- **Official API:** **None.** Clip upload is mobile-app only; no verified public publishing API.
- **publishing_status:** `NOT_SUPPORTED`.
- **Decision:** `NaverClipPublisher` returns `NOT_SUPPORTED` for auto-publish and emits a manual-upload package. The Phase 1-B vertical video is kept. Re-verify at implementation time.

---

## Cross-cutting rules honoured in code
- Official API first. No browser automation to bypass a missing/ungranted feature.
- `DRY_RUN=true` is the **default** — the engine never calls a real publish API in that mode.
- A real HTTP client (`PLATFORM_CLIENT=http`) with no verified adapter raises `PERMISSION_MISSING` — it never fabricates success.
- Mock results carry `provider_mode=MOCK` end-to-end and are never reported as a real API pass.
