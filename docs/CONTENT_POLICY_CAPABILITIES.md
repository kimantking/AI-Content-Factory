# CONTENT POLICY CAPABILITIES (Phase 7)

> Code: `backend/app/governance/policy.py`. Table: `policy_registry`,
> `policy_snapshots`. Parent: `CONTENT_GOVERNANCE.md`.

## Honesty statement

The `PolicyRegistry` rows are **fixtures that model the SHAPE of each platform's
published rules** — policy type, a `rule_id`, a human description, severity,
whether disclosure / human review is required, an `action`, a `source_reference`
("official <platform> help/policy centre (fixture — verify in production)"), and a
`last_verified_at`. Where an official rule could not be verified the row is
`status = "UNKNOWN"` and is **not** used as `ACTIVE`. Nothing here is invented as
"AVAILABLE" or "verified" that was not.

**Real, current policy verification against each platform's live terms is a
`NEEDS_PRODUCTION_ENVIRONMENT` / `LEGAL_REVIEW_REQUIRED` step.** `is_stale(db,
platform)` returns `True` when the newest `last_verified_at` for a platform is
older than `policy_max_age_days` (default 120) — a stale registry downgrades an
otherwise-auto disclosure decision to `HUMAN_REVIEW` and raises `POLICY.STALE`.

`POLICY_REGISTRY_VERSION = "2026-09-fixture-v1"` is stamped on every rule, every
`PolicySnapshot`, and every `GovernanceCase`.

## Registry version & snapshots

`seed_policy_registry(db, force=False)` is idempotent (skips existing rows unless
`force`). `snapshot(db, platform, campaign_id=…, publication_id=…)` freezes the
active rule set + `stale` flag into a `PolicySnapshot` so a published piece can be
audited against the policy set that was in force at publish time.

## Modelled platforms & rules (fixture v1)

| platform | policy types modelled | notable rule / action |
|---|---|---|
| `youtube_shorts` | SYNTHETIC_MEDIA, COPYRIGHT, SPAM, ADVERTISING | altered/synthetic → **PLATFORM_FIELD_REQUIRED** ("altered content"); unlicensed 3rd-party A/V → **BLOCK**; mass/repetitious → HUMAN_REVIEW; paid promo → DISCLOSE |
| `youtube_long` | SYNTHETIC_MEDIA, COPYRIGHT, SPAM | reused-content-without-transformation not monetisable → HUMAN_REVIEW |
| `tiktok` | SYNTHETIC_MEDIA ×2, COPYRIGHT, ADVERTISING | AIGC label → **PLATFORM_FIELD_REQUIRED**; synthetic public-figure endorsement/politics → HUMAN_REVIEW/prohibited; commercial-account music library → **BLOCK** on uncleared sound; branded-content toggle → DISCLOSE |
| `instagram_reel` | SYNTHETIC_MEDIA, COPYRIGHT, ADVERTISING | "AI info" label → DISCLOSE; music rights vary by account/region → FIX_REQUIRED; paid partnership label → DISCLOSE |
| `instagram_carousel` | ADVERTISING | paid partnership label → DISCLOSE |
| `facebook_reel` | SYNTHETIC_MEDIA, ADVERTISING | realistic AI media → DISCLOSE; branded content tools → DISCLOSE |
| `threads` | SYNTHETIC_MEDIA, SPAM | Meta AI labelling → DISCLOSE; templated mass posting → HUMAN_REVIEW |
| `x` | SYNTHETIC_MEDIA, ADVERTISING | deceptively altered media may be labelled/removed → HUMAN_REVIEW; disclose paid → DISCLOSE |
| `pinterest` | ADVERTISING, SPAM | disclose paid partnerships; duplicative Pins limited → HUMAN_REVIEW |
| `linkedin` | ADVERTISING, SYNTHETIC_MEDIA | disclose sponsored; be transparent about AI media → DISCLOSE |
| `naver_blog` | ADVERTISING, COPYRIGHT | 경제적 대가 콘텐츠 '광고'/'협찬' 표시 (표시광고법) → DISCLOSE; 타인 저작물 무단 게시 → **BLOCK** |
| `naver_clip` | ADVERTISING | sponsored marking → DISCLOSE |

`action` ∈ `{DISCLOSE, REQUIRED, PLATFORM_FIELD_REQUIRED, BLOCK, HUMAN_REVIEW,
FIX_REQUIRED}`. `rules_for(db, platform, policy_type=…)` returns only `ACTIVE`
rows and self-seeds if the platform has none.

## Policy sources (fixtures reference these, not scraped)

YouTube Help / "Disclosing AI-generated / altered content" & Content ID docs;
TikTok "AIGC" / branded content / Commercial Music Library help; Instagram / Meta
"AI info" label & branded-content / paid-partnership help; X synthetic &
manipulated media policy; Pinterest paid-partnership & spam guidelines; LinkedIn
advertising / synthetic-media transparency; Naver 표시·광고의 공정화에 관한 법률
(표시광고법) + 저작권 안내. All marked "verify in production".

## GAP / follow-up

- Live policy fetch + diff + re-verification job (per platform) — not built.
- Region-specific ad-disclosure law tables (KR 표시광고법 done as a fixture; FTC,
  EU AI Act transparency, etc. not modelled).
- Per-platform machine-readable policy feeds do not exist for most platforms;
  this stays a periodic human/legal review.
