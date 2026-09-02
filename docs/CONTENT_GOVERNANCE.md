# CONTENT GOVERNANCE LAYER (Phase 7)

> Code is the source of truth. Entry points: `backend/app/governance/`,
> `backend/app/db/models_gov.py`, migration `0008_governance`.
> Sibling docs: `RIGHTS_LEDGER.md`, `ORIGINALITY_ENGINE.md`,
> `CONTENT_POLICY_CAPABILITIES.md`, `AI_DISCLOSURE.md`, `COPYRIGHT_RESPONSE.md`.

## Purpose

A deterministic pre-publish gate that, across the whole pipeline (Research →
Script → Image → Video → Stock → Screenshot → Music → SFX → Voice → Thumbnail →
Final Render → Publishing), tracks source / copyright / licence / commercial-use /
AI-generation / edit-transform / person-brand risk / originality / duplicate
content / platform policy / ad-affiliate disclosure / fact provenance, and returns
one of **ALLOW / ALLOW_WITH_DISCLOSURE / ALLOW_WITH_ATTRIBUTION / FIX_REQUIRED /
HUMAN_REVIEW / BLOCK**.

### Absolute principles (spec §0, enforced in code)

- "publicly on the internet" ≠ "free for commercial use".
- "AI generated" ≠ "no rights problem".
- "attributed" ≠ "licensed" — attribution never creates a right
  (`attribution.build_attribution_package` returns `unusable_assets` that are
  still BLOCK).
- No auto-approval on an AI "probably fair use" guess. **No LLM produces a
  governance verdict** — every verdict is metadata / hashes / DB / rules /
  registries / cheap embeddings.
- Unclear rights ⇒ `UNKNOWN_RIGHTS`, which is **blocked from Production
  FULL_AUTO / AUTOPILOT / SEMI_AUTO auto-publish** (`rights._rights_stage`,
  `_HARD_BLOCK_CODES`).

## Architecture

```
app/governance/
  engine.py        govern_campaign() / govern_pre_publish() — orchestrator, persists cases+events
  decision.py      GovernanceDecision, decide(), state machine, _HARD_BLOCK_CODES, apply_human_override
  rights.py        RightsLedger writes + deterministic resolve_status()
  licenses.py      LicenseRegistry seed + interpret() + commercial_ok()  (code≠model≠content licence)
  policy.py        PolicyRegistry fixtures + versioning + staleness (CONTENT_POLICY_CAPABILITIES.md)
  disclosure.py    provenance_summary() + per-platform decide() + assert_not_stripped()  (AI_DISCLOSURE.md)
  identity.py      likeness / voice-clone / trademark / fake-endorsement / watermark / PII / screenshot guards
  claims.py        classify_claim + statistic/quote/opinion/temporal validation + fact↔chart mismatch
  originality.py   multi-signal similarity + transformation/reuse risk + cross-brand/channel scope
  phash.py         aHash + dHash perceptual hash (Pillow only, no new dep)
  manifest.py      RightsManifest built from assets ACTUALLY in the render + render file hash
  repair.py        one-click safe fixes (replace asset / add attribution / set AI field / refresh policy)
  attribution.py   collect + build per-placement attribution package
```

### Decision flow (`engine.govern_campaign`)

1. **Legacy short-circuit** — a campaign with `workspace_id IS NULL` and no
   `RightsLedger` row and no `governance_forced` flag returns
   `GOVERNANCE.NOT_APPLICABLE_LEGACY` ALLOW. Keeps the pre-Phase-7 suite green;
   every new Phase-7 flow creates a ledger via `record_asset_rights`, so BLOCKED
   content is still caught.
2. **Rights stage** — per ledger row: `UNKNOWN_RIGHTS` (hard block in auto modes),
   `EXPIRED`, `BLOCKED`, `RESTRICTED`, `VERIFIED_WITH_ATTRIBUTION`, watermark,
   platform restriction, Content-ID risk.
3. **Identity stage** — watermark, voice-clone consent, likeness, trademark,
   screenshot PII, fake endorsement, PII in script.
4. **Policy stage** — registry staleness for the target platform.
5. **Disclosure** — provenance → NOT_REQUIRED / RECOMMENDED / REQUIRED /
   PLATFORM_FIELD_REQUIRED / HUMAN_REVIEW.
6. **Claims** — statistic must trace to a verified fact; a chart backing a
   statistic must use the same number; opinion not stated as fact; temporal
   staleness.
7. **Originality** (post-render / pre-publish) — vs recent workspace fingerprints,
   own + cross-brand + cross-channel; transformation & reuse risk; platform-native
   variant check.
8. `decision.decide(sub_results, run_mode)` combines: worst decision wins, any
   `_HARD_BLOCK_CODES` reason or `hard_block` sub ⇒ `BLOCK`.
9. Persist one `GovernanceCase` per non-ALLOW sub + a `GovernanceEvent` rollup;
   write `PlatformContent.governance_state` / `.governance_decision` and the
   merged `disclosure_meta`.

### State machine (`decision._TRANSITIONS`)

`PENDING → SCANNING → PASS | PASS_WITH_REQUIREMENTS | FIX_REQUIRED | HUMAN_REVIEW |
BLOCKED → RESOLVED`. Invalid transitions are rejected. `BLOCKED` leaves only via
`SCANNING` (a real fix) or `RESOLVED` (authorised review of a **soft** block).

### Hard blocks (never cleared by a UI approval or an agent — spec §79-§80)

`RIGHTS.UNKNOWN_IN_AUTO`, `RIGHTS.EXPIRED`, `RIGHTS.WATERMARK`, `RIGHTS.BLOCKED`,
`RIGHTS.PLATFORM_RESTRICTED`, `VOICE.CLONE_NO_CONSENT`, `POLICY.COPYRIGHT_BLOCK`,
`PRIVACY.HIGH_RISK_PII`, `CLAIM.CHART_MISMATCH`, `ENDORSEMENT.PUBLIC_FIGURE`,
`ORIGINALITY.DUPLICATE`. `decision.apply_human_override` returns an error string
for any of these; a soft `HUMAN_REVIEW` / `FIX_REQUIRED` is clearable by an
authorised reviewer.

## Enforcement points

| Where | Call | Effect on a non-publishable verdict |
|---|---|---|
| **Publisher** `publishing/engine.run_publish_job` | `govern_pre_publish(session, job=job)` after the token check, before preflight | job → `BLOCKED` (hard) or `WAITING_APPROVAL` (soft HUMAN_REVIEW); `last_error_type="GOVERNANCE"`; `Publication` upserted with `error_code=GOVERNANCE`; **returns before the platform call** |
| **Autopilot** `autopilot/bridge.produce_from_context` | `govern_campaign(..., stage="post_render", run_mode=run_mode)` after `pre_publish_recheck` | candidate → `GOVERNANCE_HOLD`; an `AutopilotDecision(decision_type="governance_hold")` logged; **no publish jobs created** |
| **Manifest** at publish | `manifest.build_manifest(...)` | `RightsManifest` row persisted from the assets actually in the render + the render file sha256; `is_published_snapshot=True` |

Both gates **fail safe**: any exception inside governance ⇒ `HUMAN_REVIEW` +
`publishable: False`, never a silent pass. Governance can be disabled only by
`GOVERNANCE_ENFORCE=false` (default `true`).

## Config (`app/config.py`)

| Setting | Default | Meaning |
|---|---|---|
| `governance_enforce` | `true` | master switch for both gates |
| `policy_max_age_days` | `120` | a platform policy older than this is `POLICY.STALE` |
| `originality_block_threshold` | `0.90` | combined similarity ≥ ⇒ DUPLICATE / REUSED_WITH_TRANSFORMATION |
| `originality_review_threshold` | `0.78` | combined similarity ≥ ⇒ HIGH_SIMILARITY → HUMAN_REVIEW |

## API (`app/api/routes_governance.py`, prefix `/api`)

`POST /governance/check`, `GET /governance/cases`, `GET /governance/review`,
`POST /governance/cases/{id}/review` (hard block → 409),
`POST /governance/repair`, `GET /rights`, `GET /rights/assets/{asset_id}`,
`GET|POST /rights/manifests`, `POST /originality/check`, `GET /policy/status`,
`POST /disclosure/check`, `GET|POST /copyright/claims`. Tenant-scoped reads assert
the caller's workspace when the campaign has one (Phase 6 RBAC).

## Database (migration `0008_governance`, 14 tables, additive)

`rights_ledger`, `rights_evidence`, `asset_lineage`, `rights_manifests`,
`license_registry`, `policy_registry`, `policy_snapshots`, `governance_cases`,
`governance_events`, `claim_provenance`, `content_fingerprints`,
`similarity_results`, `copyright_claims`, `correction_cases`. Plus additive
columns: `platform_contents.governance_state` / `.governance_decision`,
`publish_jobs.governance_decision` / `.disclosure_meta` (all NULLABLE).

## Interaction with URL Learning (Cross-Phase Intelligence Upgrade)

- **Reference-use ≠ media rights (spec §BM).** Treating a fetched page as a
  research reference does not grant any right to reproduce the images / video
  inside it. A learned `ReferenceSource` carries `rights_status =
  RESEARCH_REFERENCE`; if an asset is later pulled from that reference it gets its
  own `RightsLedger` row and is governed normally (UNKNOWN_RIGHTS → hard block in
  auto modes).
- **Originality vs references (spec §BN).** Generated Hook / Script / Structure /
  Thumbnail / Scene / Video are similarity-checked against the campaign's learned
  references (`reference_similarity_fix_threshold`, default 0.82) as well as prior
  content — too-similar output is `FIX_REQUIRED`.
- **Distilled prompts never strip governance.** `PromptComposer` labels the
  LEARNED_GUIDANCE block as advisory and subordinate to facts, platform policy and
  copyright/governance rules; a learned instruction cannot lift a hard block.

## Known limitations

- Cheap 24-dim hashed embedding for text similarity (`app.analytics.embedding`) —
  weak far-paraphrase recall; a real `EmbeddingProvider` is deferred (DECISIONS
  D61). Exact / normalised / Jaccard / n-gram / pHash / video-structure signals
  are unaffected.
- Perceptual hashing is aHash+dHash only (no pHash-DCT, no heavy CV). Logo / face
  / on-frame-text detection is an OPTIONAL adapter slot (`identity.py` docstring)
  — absent, those fields stay UNKNOWN and route to review, never a faked pass.
- Platform policy rows are **fixtures modelling the shape** of each platform's
  rules with a `source_reference` + `last_verified_at`; real current-policy
  verification is `NEEDS_PRODUCTION_ENVIRONMENT`.
- No C2PA / Content Credentials signing (see `AI_DISCLOSURE.md` §"C2PA").
