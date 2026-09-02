# RIGHTS LEDGER (Phase 7)

> Code: `backend/app/governance/rights.py`, `licenses.py`, `attribution.py`,
> `manifest.py`; tables in `models_gov.py`. Parent: `CONTENT_GOVERNANCE.md`.

## What it is

Every media asset that enters a campaign gets one `RightsLedger` row. The row's
`rights_status` is **derived deterministically** from source type + licence +
provenance + consent + expiration — never assumed permissive. It is written by
`record_asset_rights(...)` and (re)computed by `resolve_status(db, led)` on every
change (including when evidence is added).

## `rights_status` values

| status | meaning | auto-publish? |
|---|---|---|
| `VERIFIED` | known licence, commercial OK, no attribution needed | yes (`AUTO_SAFE_STATUS`) |
| `LICENSED` | stock / music provider licence with a reference or evidence | yes |
| `USER_OWNED` | user-supplied + explicitly owned | yes |
| `AI_GENERATED_VERIFIED` | model output, provider/terms referenced, model licence allows commercial | yes |
| `PUBLIC_DOMAIN_VERIFIED` | source + licence both say public domain / CC0 | yes |
| `VERIFIED_WITH_ATTRIBUTION` | as LICENSED/VERIFIED but attribution required | only once the attribution package exists |
| `RESTRICTED` | non-commercial licence, revoked consent, or a superseded auto-fix row | no → HUMAN_REVIEW |
| `EXPIRED` | `expiration_at` in the past (or before the scheduled publish time) | no → **hard BLOCK** |
| `DISPUTED` | synthetic person + misleading-association flag | no → HUMAN_REVIEW |
| `BLOCKED` | third-party watermark, cloned voice without consent, or explicitly set | no → **hard BLOCK** |
| `UNKNOWN_RIGHTS` | anything unclear — screenshot / news / social repost / claimed-licensed-without-proof / model output without terms | no → **hard BLOCK in FULL_AUTO / AUTOPILOT / SEMI_AUTO**, HUMAN_REVIEW otherwise |

## `resolve_status` order (short-circuits top-down)

1. explicit `BLOCKED` → `BLOCKED`
2. `watermark_detected` → `BLOCKED`
3. `voice_kind == CLONED_VOICE` and consent ∉ {USER_CONFIRMED, DOCUMENTED} → `BLOCKED`
4. synthetic person + `MISLEADING_ASSOCIATION_RISK` → `DISPUTED`
5. `expiration_at` past → `EXPIRED`
6. per `source_type`:
   - `AI_GENERATED` / `GENERATED_*`: model terms/provider present + commercial ≠ NO → `AI_GENERATED_VERIFIED`, else `RESTRICTED` / `UNKNOWN_RIGHTS`
   - `PUBLIC_DOMAIN` + licence CC0/PUBLIC_DOMAIN → `PUBLIC_DOMAIN_VERIFIED`
   - `USER_UPLOAD`: revoked consent → `RESTRICTED`; owned → `USER_OWNED`; else `UNKNOWN_RIGHTS`
   - `STOCK_LICENSED` / `MUSIC_LIBRARY` / `SFX_LIBRARY`: non-commercial → `RESTRICTED`; no reference & no evidence → `UNKNOWN_RIGHTS`; attribution required → `VERIFIED_WITH_ATTRIBUTION`; else `LICENSED`
   - `SCREENSHOT` / `SOCIAL_POST` / `NEWS_MEDIA` / `OFFICIAL_SOURCE` → `UNKNOWN_RIGHTS` (**referencing a fact ≠ a right to reproduce the media**)
7. fallback: commercial YES + known licence → `VERIFIED` / `VERIFIED_WITH_ATTRIBUTION`, else `UNKNOWN_RIGHTS`

## Licence registry (`licenses.py`)

`LicenseRegistry` seeds ~18 keys with `(kind, commercial, derivative,
attribution_required, share_alike, expiration_possible, redistribution_limit)`.
`kind` is one of `CONTENT_LICENSE / ASSET_LICENSE / MODEL_LICENSE /
SOFTWARE_LICENSE` — **a code licence is not a content licence** (spec §9):
`commercial_ok()` returns `UNKNOWN` when a `SOFTWARE_LICENSE` (MIT / Apache-2.0 /
GPL-3.0) is attached to a media asset. Unknown key ⇒ conservative
(`commercial_allowed = UNKNOWN`, `expiration_possible = True`).

Seeded content/asset/model keys: `CC0`, `PUBLIC_DOMAIN`, `CC-BY`, `CC-BY-SA`,
`CC-BY-NC`, `CC-BY-ND`, `COMMERCIAL_STOCK`, `EDITORIAL_STOCK`, `USER_OWNED`,
`USER_PERMISSION`, `PROVIDER_MUSIC`, `MODEL_OUTPUT_COMMERCIAL`,
`MODEL_OUTPUT_NONCOMMERCIAL`, `UNKNOWN`.

## Evidence

`RightsEvidence` rows (`add_evidence`) attach a licence screenshot / receipt /
model-terms URL / consent record hash to a ledger row; the row's `evidence_ids`
list and `rights_status` are re-resolved. Evidence can move a claimed-licensed
stock asset from `UNKNOWN_RIGHTS` to `LICENSED`.

## Attribution (`attribution.py`) — does NOT create rights (spec §66)

`build_attribution_package(db, campaign_id)` returns `description_block` (YouTube /
Naver), `caption_suffix` (short platforms), `credits_section`, and
`unusable_assets` — assets whose status is `UNKNOWN_RIGHTS` / `EXPIRED` /
`BLOCKED` / `DISPUTED`. Those are listed so a human sees them; they stay BLOCK and
must be replaced. Building the package is what promotes a
`VERIFIED_WITH_ATTRIBUTION` asset to auto-publishable.

## Rights Manifest (`manifest.py`) — spec §6, §85, §107, §137

`build_manifest(...)` is built from the `Asset` rows **actually joined to the
campaign/render**, not the plan. It records per-asset rights id / status / source /
licence / attribution / expiry, the lists of music / sfx / screenshots / charts /
AI-generated assets, `unknown_rights_assets`, `disclosure_required`, the
governance decision, and `content_hash` = sha256 of the real render file on disk.
`is_published_snapshot=True` marks the copy taken at publish time; it survives
asset-cache cleanup. Verified by
`tests/governance/test_e2e.py::test_manifest_matches_final_render`.

## Multi-brand isolation (Phase 6)

Every ledger / evidence / manifest / fingerprint / case row carries
`workspace_id` + `brand_id` + `channel_id`. The `/rights*` API scopes reads to the
caller's workspace. Verified by
`tests/governance/test_e2e.py::test_rights_data_is_workspace_scoped`.
