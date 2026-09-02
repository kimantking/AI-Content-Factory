# COPYRIGHT CLAIM & CORRECTION RESPONSE (Phase 7)

> Code: `backend/app/api/routes_governance.py` (`/copyright/claims`),
> `models_gov.CopyrightClaim`, `models_gov.CorrectionCase`,
> `governance/manifest.py`. Parent: `CONTENT_GOVERNANCE.md`.

## Guiding rule

Nothing here files, disputes, or answers a legal notice automatically. The system
**assembles a review package** from data it already has (the Rights Manifest, the
ledger, the attribution package) and routes it to a human. Every generated
artefact is labelled *"review package only — not an automated legal filing"*.

## Inbound copyright claim

`POST /api/copyright/claims` records a `CopyrightClaim`
(`platform`, `publication_id`, `asset_id`, `claimant`, `claimed_segment`,
`claim_type`, `evidence`) with `status = RECEIVED`. If the publication has a
`RightsManifest`, a `dispute_package` is attached:

```
{ manifest_id, assets:[…per-asset rights id / status / source / licence…],
  attributions:[…], note:"review package only — not an automated legal filing" }
```

`status` lifecycle (human-driven):
`RECEIVED → REVIEWING → CONTENT_HELD | ACTION_REQUIRED → RESOLVED`.
`GET /api/copyright/claims` lists them, workspace-scoped by membership.

**What the package gives a reviewer:** which asset in the finished render is
implicated, its recorded source / licence / evidence / attribution, and whether
governance had flagged it (`UNKNOWN_RIGHTS` assets would not have passed a
FULL_AUTO publish in the first place — so a claim on one usually means a manual
override or a legacy publish).

## Post-publish correction (`CorrectionCase`)

Raised when something that was true at publish time stops being true:

| `trigger` | example | recommended `status` |
|---|---|---|
| `SOURCE_RETRACTED` | a cited article is retracted | `POST_CORRECTION` / `UNPUBLISH_RECOMMENDED` |
| `FACT_CORRECTED` | a statistic is revised | `UPDATE_METADATA` / `POST_CORRECTION` |
| `LICENSE_EXPIRED` | a stock/music licence lapses after publish | `UNPUBLISH_RECOMMENDED` |
| `CLAIM` | an inbound copyright / likeness complaint | `REVIEW` |

`status` ∈ `REVIEW | UPDATE_METADATA | POST_CORRECTION | UNPUBLISH_RECOMMENDED |
NO_ACTION`. The engine only **recommends**; unpublishing / editing a live post is
a human action (consistent with the Phase 6 rule that the AI never deletes).

## Prevention (why claims should be rare)

- `UNKNOWN_RIGHTS` / `EXPIRED` / watermarked / cloned-voice-without-consent
  assets are hard-blocked from auto-publish.
- The `RightsManifest` + `AssetLineage` give a defensible record of every asset's
  origin and every transform applied.
- Scheduled-publish honours licence expiry: a job scheduled after an asset's
  `expiration_at` is blocked at preflight (`govern_pre_publish`).

## Known limitations / LEGAL_REVIEW_REQUIRED

- No integration with any platform's actual dispute API (YouTube Content ID
  dispute form, etc.) — the package is generated, a human files it.
- "Fair use / fair dealing / 인용" is **never** asserted by the system; any such
  argument in a dispute is a `LEGAL_REVIEW_REQUIRED` item.
- Counter-notification / DMCA 512(g) workflows are out of scope.
- Jurisdiction-specific takedown timelines are not modelled.
