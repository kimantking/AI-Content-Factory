# Platform Support Matrix (Phase 10)

Source of truth: `app/publishing/capabilities.py` +
`GET /api/publishing/platforms`. State ∈ `SUPPORTED · AUTH_REQUIRED ·
APP_REVIEW_REQUIRED · ACCOUNT_TYPE_REQUIRED · LIMITED · MANUAL_ONLY ·
NOT_SUPPORTED · UNKNOWN`. **All 10 are CODE_READY + MOCK_VERIFIED; none has done a
real remote publish.**

| Platform | Auth | Publish path | Analytics | Revenue | App review | Account req. | Current state |
|---|---|---|---|---|---|---|---|
| YouTube (Shorts/Long) | OAuth2 (Data API) | API | scopes needed | monetisation API | yes | channel | AUTH_REQUIRED → NEEDS_CREDENTIALS |
| TikTok | OAuth2 (Content Posting) | API | scopes | — | **yes (app review)** | — | APP_REVIEW_REQUIRED |
| Instagram (Reels/Feed/Carousel) | FB/IG Graph | API | Graph insights | — | **yes** | **business/creator** | APP_REVIEW_REQUIRED + ACCOUNT_TYPE_REQUIRED |
| Facebook (Reels) | Graph | API | insights | — | yes | Page | APP_REVIEW_REQUIRED |
| Threads | Threads API | API | limited | — | yes | — | AUTH_REQUIRED / LIMITED |
| X | OAuth2 | API | limited | — | paid API tier | — | AUTH_REQUIRED (paid tier) |
| Pinterest | OAuth2 | API | insights | — | yes | — | AUTH_REQUIRED |
| LinkedIn | OAuth2 | API | limited | — | yes | — | AUTH_REQUIRED |
| Naver Blog | — | **MANUAL_ONLY** (no official publish API) | — | — | — | — | MANUAL_ONLY |
| Naver Clip | — | **NOT_SUPPORTED** (no public API) | — | — | — | — | NOT_SUPPORTED |

Publisher engine (idempotency / retry / scheduler / crash-reconcile / DLQ /
governance+selection gate / `DRY_RUN` default) is CODE_READY + MOCK_VERIFIED
(`tests/publishing/`).
