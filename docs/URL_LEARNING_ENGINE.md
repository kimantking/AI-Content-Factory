# URL LEARNING ENGINE (Cross-Phase Intelligence Upgrade)

> Code: `backend/app/intel/`. Migration `0009_intelligence`. No new dependency.
> Reuses Research / Fact Check / Memory / Learning / Video Studio / Governance /
> Analytics — no new runtime architecture.

## Flow (`intel/engine.py`)

```
add_urls()  -> LearningJob + one ReferenceSource per URL (hard count/byte/daily guards)
run_learning_job():
  per reference:
    validate_url (SSRF, per redirect hop)        intel/url_security.py
    fetch (http adapter; browser adapter opt-in) intel/fetch.py
    clean + extract (strip chrome; metadata)     intel/extract.py
    prompt-injection scan + sanitize             intel/injection.py
    Stage-1 cheap quality + dedup                 intel/quality.py
    semantic chunks
  Stage-2 (cheap-first): deep-analyse only the top-K by quality
    FACTS / KNOWLEDGE / WRITING_PROFILE / VIDEO_OBSERVATION + 10 video sub-profiles /
    GITHUB_ANALYSIS / COMPETITOR_ANALYSIS         intel/analyzers.py
  if mode writes learning output:
    DatasetWriter -> dataset_records              intel/dataset.py
    PromptDistillationEngine -> prompt_blueprints intel/distillation.py
    Agent Skill Learning -> learned_skill_notes   intel/skills.py
    MemoryWriter -> learning.memory (guidance only, never auto-VERIFIED)
    DataCurator sweep
```

## Execution modes (`intel/modes.py`)

| mode | learns | writes datasets/prompts | produces content |
|---|---|---|---|
| `CREATE_ONLY` | no | no | yes |
| `CREATE_AND_LEARN` (UI default) | yes | yes | yes |
| `LEARN_ONLY` (Learning Studio default) | yes | yes | **no** |
| `REFERENCE_ONLY` | stores reference only | **no** | **no** |

`assert_no_production_side_effects(mode, op)` raises `ProductionSideEffectBlocked`
under LEARN_ONLY / REFERENCE_ONLY for `campaign_production`, `ai_image_generation`,
`ai_video_generation`, `tts_production`, `final_render`, `publish_job`,
`sns_api_call`. `create_jobs_for_campaign` and the Publisher both short-circuit on
a LEARN_ONLY campaign.

## Supported URL structures (`url_security.classify_url`)

`WEB_PAGE`, `NEWS_ARTICLE`, `BLOG`, `OFFICIAL_DOCUMENT`, `PDF`,
`GITHUB_REPOSITORY`, `GITHUB_FILE`, `YOUTUBE`, `VIDEO_PAGE`, `PRODUCT_PAGE`,
`SOCIAL_POST`, `UNKNOWN`. Each carries an honest `support_level`:
`SUPPORTED` / `LIMITED` (YouTube, social, video pages — metadata + a caller-supplied
structured profile only, no scraping) / `AUTH_REQUIRED` (login/paywall hints) /
`UNSUPPORTED`.

## Security (see `SECURITY_MODEL.md` §"URL Learning")

- External URL content is always **UNTRUSTED_EXTERNAL_CONTENT**. Text like "ignore
  previous instructions", "run this command", "reveal API key", "delete database",
  "change system prompt" is **data, never an instruction**.
  `injection.scan/sanitize/wrap_untrusted` detect + strip + quote; nothing is
  executed. A flagged reference records `injection_flag` + `injection_detail` and
  is quality-penalised.
- SSRF reuses the Phase 5 guard. Blocked: localhost, `127.0.0.0/8`, private /
  link-local / reserved IPs, metadata endpoints, `*.internal` / `*.local`,
  `file://`, `gopher://`, `ftp://`, `ws(s)://`, redis/postgres URLs. Every
  redirect hop is re-validated. In production the full DNS-rebinding check runs;
  in dev/test a hostname that does not resolve is allowed through (it cannot reach
  an internal service and the fetch fails safely).
- `BrowserFetchAdapter` (JS rendering) is **off by default** (`browser_fetch_enabled`,
  install policy D67 — Playwright is a pending project-scoped dependency). The stub
  raises `AdapterUnavailable` rather than faking a render. Forbidden for every
  adapter: CAPTCHA / paywall / login / DRM / anti-bot bypass.

## Hard guards (`app/config.py`)

`max_learning_items_per_job` (100), `max_daily_learning_items` (500),
`max_learning_cost_usd` (5.0), `max_reference_bytes` (5 MB),
`learning_deep_analysis_top_k` (20). Exceeding a limit raises `LearningGuardError`
→ HTTP 429.

## Rights separation (spec §BM)

Treating a page as a research reference is **not** a right to reuse the images /
video inside it. `ReferenceSource.rights_status` defaults to `RESEARCH_REFERENCE`;
any media pulled from a reference goes through the Phase 7 RightsLedger
separately.
