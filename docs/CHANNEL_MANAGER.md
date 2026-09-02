# CHANNEL MANAGER (Phase 6)

`backend/app/mb/channel_manager.py` — deterministic. No LLM in the hot path (§102).

## ChannelHealthScore (0–100)

Components (each 0–100), computed from existing Phase 1–3 rows scoped by
`channels.id`:

| Component | Source |
|---|---|
| `activity` | campaigns in the last 30 days |
| `publishing_reliability` | SUCCESS ÷ attempted campaigns |
| `content_performance` | mean Phase-3 `PerformanceScore.score` **excluding `is_outlier`/`has_anomaly`** |
| `audience_growth` | follower series (not wired yet → 0/unknown) |
| `revenue` | actual `RevenueEntry` sum (30d) — estimate rows excluded |
| `profit` | actual revenue − scoped cost (30d) |
| `cost_efficiency` | inverse of scoped cost |
| `topic_diversity` | distinct topic-cluster prefixes among campaigns |
| `brand_consistency`, `policy_health`, `account_health` | assumed OK unless a violation is recorded; account_health low if no `platform_account_id` |

The final score is a **weighted** blend keyed by the channel's `primary_objective`
(GROWTH / REVENUE / PROFIT / BALANCED weight tables).

## Scale status (`scale_status`)

`NOT_ENOUGH_DATA → HOLD → TEST_MORE → SCALE_CAUTIOUSLY → SCALE → REVIEW`

Rules (`_scale_status`):
- `sample < 6` → `NOT_ENOUGH_DATA` (a WARMUP channel is never told to scale).
- Uses the **median** (not max) of non-outlier performance scores, so a single
  viral clip cannot trigger `SCALE` (§114). `sample < 12` caps the best outcome
  at `SCALE_CAUTIOUSLY`.
- Median ≥ 68 & sample ≥ 12 → `SCALE`; ≥ 55 → `SCALE_CAUTIOUSLY`; < 40 → `REVIEW`.

Actual budget scaling is a **Portfolio Manager** decision and still bounded by the
Workspace/Brand/Channel hard limits — the Channel Manager only *proposes*.

## ChannelOperatingPlan

`operating_plan()` → `channel_operating_plans` row:

```
content_target        (bounded by daily_min/max; -1 in REVIEW/HOLD)
topic_preferences     (active ContentPillars, else content_strategy.topics)
content_mix           CORE/TREND/EVERGREEN/EXPERIMENT/REVENUE — configurable;
                      WARMUP forces EXPERIMENT >= 25%
production_profile    (WARMUP downgrades CINEMATIC → STANDARD)
publish_windows       (channel.schedule)
growth_goal / revenue_goal
scale_status / health_score
recommended_actions   accumulate_data | fix_publishing_reliability |
                      broaden_topic_pillars | lower_production_profile |
                      propose_scale_to_portfolio | reposition_review_recommended | continue
risks                 no_platform_account_connected | sustained_underperformance
```

## Warmup (§16) & cold start (§94)

`lifecycle in (DRAFT, WARMUP)` or `sample < 6` ⇒ `warmup=True`: diverse topics /
hooks / durations, controlled experiments, **no high-confidence optimisation**.
Channel memory priority is Channel-specific → Brand → Platform → Global (§17);
cross-channel transfer needs similarity + sample size + confidence and is
labelled `DIRECT_EVIDENCE / TRANSFERABLE / WEAK_TRANSFER / NOT_TRANSFERABLE`
(the label vocabulary is defined; the retrieval wiring reuses Phase-3 memory
filters — full cross-channel transfer scoring is DESIGN_ONLY).

## Channel Manager skills (§99, registered concept)

`channel_health, content_mix, budget_recommendation, schedule_recommendation,
growth_analysis, profitability_analysis, topic_fatigue, brand_consistency,
experiment_planning, scale_recommendation, reposition_recommendation`. All
deterministic except `reposition_recommendation` (LLM, DESIGN_ONLY).

## API

`GET /api/channels/{id}/health` · `GET /api/channels/{id}/plan` ·
`GET /api/channels/{id}/monetization` · `GET /api/channels/{id}/revenue` ·
`PATCH /api/channels/{id}` (role-gated per field) · `POST /api/channels/{id}/pause`.

## Tests

`tests/mb/test_managers.py` — health + scale status, warmup never scales, single
outlier does not trigger SCALE, operating plan shape.
