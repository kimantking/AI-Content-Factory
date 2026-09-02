# AI DISCLOSURE ENGINE (Phase 7)

> Code: `backend/app/governance/disclosure.py`. Parent: `CONTENT_GOVERNANCE.md`.

## Purpose

Meet each platform's transparency rule for AI-generated / synthetic / materially
altered media. **Not** a tool for hiding AI use. Disclosure information attached
here must never be stripped by a downstream step (spec §34).

## Provenance (`provenance_summary(db, asset_ids)`)

Reads the `RightsLedger` rows for the render's assets and returns booleans:
`ai_generated`, `ai_assisted`, `synthetic_image`, `synthetic_video`,
`synthetic_voice`, `tts_voice`, `synthetic_person`, `real_person_synthetic`,
`materially_altered` (AI edits applied to real stock / user footage).

## Decision (`decide(db, platform, provenance)`)

| result | when | engine effect |
|---|---|---|
| `NOT_REQUIRED` | no AI / no synthetic elements, platform has no rule | — |
| `RECOMMENDED` | AI-assisted only, platform encourages transparency | soft — `disclosure recommended` requirement, still ALLOW |
| `REQUIRED` | synthetic media + a platform rule with action `DISCLOSE`/`REQUIRED` | in-content disclosure text must be present or `DISCLOSURE.MISSING` → FIX_REQUIRED |
| `PLATFORM_FIELD_REQUIRED` | synthetic media + a platform rule with action `PLATFORM_FIELD_REQUIRED` (YouTube "altered content", TikTok "AIGC") | the platform AI/altered-content field must be set (`disclosure_meta.platform_ai_field`) or `DISCLOSURE.PLATFORM_FIELD_MISSING` → FIX_REQUIRED |
| `HUMAN_REVIEW` | synthetic depiction of a **real** person; or `any_ai` + stale policy registry | routes to review, never auto |

Disclosure text used: `이 콘텐츠에는 AI가 생성/합성한 요소가 포함되어 있습니다.`
(synthetic) or `이 콘텐츠는 실제 장면을 상당 부분 변형·합성하여 제작되었습니다.`
(materially altered). The engine merges the decision into
`PlatformContent.payload.disclosure_meta` with `disclosure_required`,
`disclosure_type`, `disclosure_text`, the provenance booleans, and
`policy_version`.

## Never-stripped guard (spec §34)

- `assert_not_stripped(before_meta, after_meta)` — returns violation strings if a
  natural-writing / platform-adapt / publisher step dropped a disclosure flag or
  cleared `disclosure_text`.
- `strip_disclosure_from_text_guard(original, new)` — `True` if a disclosure
  marker present in the original script is missing from a rewrite (blocks a
  naturalness pass that removed it). Markers: `AI가 생성`, `AI가 합성`,
  `합성하여 제작`, `AI-generated`, `synthetic`, `altered content`, `AI info`,
  `AIGC`.
- The Phase-6 `enforce_affiliate_disclosure` (D76) already **adds** a missing
  ad/affiliate disclosure and never removes one — Phase 7 relies on it and adds
  the AI-synthesis disclosure on the same principle.

## Repair (`repair.apply_fix`)

- `DISCLOSURE.PLATFORM_FIELD_MISSING` → `set_platform_ai_field` sets
  `disclosure_meta.platform_ai_field = True` + a default disclosure text.
- `DISCLOSURE.MISSING` / `DISCLOSURE.RECOMMENDED` → `add_disclosure_meta` sets
  `disclosure_required = True` + text.
Both write a `GovernanceEvent(kind="DISCLOSURE_ADDED")`. Re-running governance
then returns `ALLOW_WITH_DISCLOSURE`.

## C2PA / Content Credentials — investigated, NOT implemented (spec §156)

C2PA / Content Credentials (c2pa-python, `truepic`, Adobe CAI) would let the
render carry a signed manifest of its edit history. **Not adopted**: it needs a
signing identity / certificate and a trust list, adds a native dependency
(`c2pa` / OpenSSL bindings), and most target platforms do not yet consume or
display CR manifests for short-form uploads. The `RightsManifest` +
`AssetLineage` tables already record provenance internally. Generating a **fake**
Content Credential is explicitly refused. Revisit when a signing identity and a
platform that verifies CR are both available — tracked as OPTIONAL.

## Known limitations

- "Realistic / photoreal" is inferred from `source_type` + `ai_generated`, not
  from image analysis — a stylised cartoon AI image is treated the same as a
  photoreal one. A realism classifier is an OPTIONAL adapter.
- Platform field names / API parameters for the AI toggle are modelled, not
  wired to a live publish call (publishers are MOCK — Phase 2).
