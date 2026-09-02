# MONETIZATION (Phase 6)

`backend/app/mb/monetization.py` — deterministic analysis + safety guards on top
of the Phase 3 revenue/cost ledgers. Phase 6 does **not** build a commerce system
(§35).

## Profit centre (§26, §29, §115)

`profit_center(channel_id, days=30)`:

```
revenue_actual_usd      sum of RevenueEntry where is_estimate = false
revenue_estimated_usd   sum where is_estimate = true   — NEVER summed with actual
production_cost_usd      scoped CostLog sum
net_profit_usd          revenue_actual - cost           (estimate excluded)
profit_margin
cost_per_content_usd / revenue_per_content_usd / profit_per_content_usd
```

Estimated and actual revenue are returned in separate fields and never added
(§27, §115). Missing metrics are `null`, never `0` (Phase 3 rule).

## MonetizationAgent (§64, §66)

`monetization_agent(channel)` scores each revenue model `PLATFORM_AD_REVENUE /
AFFILIATE / SPONSOR / PRODUCT / SERVICE_LEAD / MEMBERSHIP` for fit from the
channel's type, objective and output history, and returns
`recommended_primary_model` + per-model `reasons`. Deterministic; no LLM.

## Safety guards

### Sponsor content guard (§34, §49, §116) — `sponsor_content_guard(...)`
`verdict = BLOCK` if any of:
- a sponsor `forbidden_claims` phrase appears in the script;
- a `required_mentions` line makes an unverifiable superlative ("최고", "1위",
  "유일", "부작용 없", "100%") not backed by a verified fact;
- the sponsor / deliverables match a brand `blocked_sponsor_categories` entry;
- the script implies "not sponsored" (`내돈내산`, `협찬 아님`) while a deal exists.

A paid deal **never** overrides Compliance / Platform Policy / Fact checks (§49).

### Commercial guards (§65, §67, §68) — `commercial_guards(...)`
- `sponsored_density` / `commercial_density` over the last N contents;
- `verdict = BLOCK` on **fake tactics**: fake scarcity ("마감 임박", "딱 오늘만"…),
  fake social proof ("모두가 샀", "후기 폭발"…). Also covered: hidden ads, fake
  discounts, fake reviews (§65) — no such content is produced.
- `verdict = WARN` when sponsored density > 40% or commercial density > 60%.

### Affiliate disclosure (§32, §117) — `enforce_affiliate_disclosure(...)`
If a content has an affiliate link and the required disclosure is **not** present,
it is **prepended** (`status = ADDED`). It is never auto-removed. `PRESENT` when
already there, `N/A` when there is no affiliate link.

## Schema (§30–§35)

`affiliate_programs, affiliate_links, sponsor_deals, offers` (+ `revenue_entries`
now carries `workspace_id/brand_id/channel_id`). `Offer` is a thin
product/service-lead/membership pointer — no cart, no checkout.

## Revenue / cost allocation (§27–§28)

`RevenueEntry` and `CostLog` gained NULLABLE `workspace_id/brand_id/channel_id`.
New scoped code sets them; the profit centre aggregates by channel. Shared
infrastructure-cost allocation rules with a version stamp are DESIGN_ONLY this
phase (the per-channel direct cost/revenue rollup is done).

## API

`GET /api/channels/{id}/monetization` · `GET /api/channels/{id}/revenue`.
Sponsor / affiliate CRUD endpoints are DESIGN_ONLY (schema + guards exist; the
create/list routes are a thin follow-up).

## Tests

`tests/mb/test_monetization.py` — estimate/actual never summed, model
recommendation, sponsor block (forbidden claim / superlative / blocked category),
sponsor OK when clean, affiliate disclosure added-not-removed, fake-tactic BLOCK.
