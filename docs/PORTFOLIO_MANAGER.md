# PORTFOLIO MANAGER (Phase 6)

`backend/app/mb/portfolio.py` — deterministic. Manages *resource allocation across
channels*; it never creates content and never deletes a channel (§51, §52).

## Portfolio scoring (§21)

`snapshot(workspace_id, objective=?)` → `portfolio_snapshots` row. For every
channel it computes, from the latest `ChannelHealthSnapshot`:

`growth_score, revenue_score, profit_score, efficiency_score, stability_score,
audience_score, opportunity_score, risk_score, health_score` and a
**`portfolio_score`** = objective-weighted blend.

`portfolio_score` is scored by the **workspace** objective (or an override passed
to `allocate_budget`), so the whole portfolio view shifts with the workspace goal
(§112). `portfolio_score_channel_objective` is also kept as a secondary lens for
the channel dashboard.

Objective weight tables: `GROWTH / REVENUE / PROFIT / DIVERSIFICATION / BRAND /
BALANCED` (`_OBJ_WEIGHTS`).

## Budget allocation (§22, §98)

`allocate_budget(workspace_id, objective?, total_usd?, trend_reserve_frac=0.1,
min_exploration_frac=0.05)`:

1. `total` defaults to the **workspace daily hard budget**; any `total_usd`
   passed is **clamped** to it (`hard_capped=True` reported). Never exceeds a
   hard limit.
2. Hold back `trend_reserve_frac` (default 10%).
3. **Fairness floor** (§98): every ACTIVE channel gets at least
   `min_exploration_frac` of the distributable pool ÷ channel count, so
   experiment channels always accrue data.
4. The rest is split by `portfolio_score` weight, **dampened** for
   warmup / low-sample / `NOT_ENOUGH_DATA` / `TEST_MORE` channels (weight capped
   at 40) so a lucky month can't 5× a channel's budget (§93/§113/§114).

## Recommendations (§92) — advisory, evidence-backed, never applied

`recommendations(workspace_id)` → `portfolio_decisions` rows:

| Action | When |
|---|---|
| `EXPERIMENT` | `sample < 6` (cold start) |
| `INCREASE_BUDGET` (+15%, still hard-capped) | `scale_status == SCALE` & `sample >= 12` |
| `REPOSITION_RECOMMENDED` (keep identity) | `scale_status == REVIEW` |
| `REDUCE_PRODUCTION` (−20%) | `scale_status == HOLD` |
| `KEEP` | otherwise |

Every row carries `evidence` (the channel scores + objective), `confidence`
(0–1, grows with sample size), `sample_size`, and `applied=False`. **`DELETE` /
`ARCHIVE` are never emitted** — the user decides (§52, `CONTINUE / REDUCE /
PAUSE_RECOMMENDED / REPOSITION_RECOMMENDED / REVIEW_REQUIRED`).

## Content routing & cannibalization

See `routing.py` (`MULTI_BRAND_ARCHITECTURE.md` §5). `route()` picks the best
channel; `cannibalization_status()` returns `SAFE / OVERLAP /
CANNIBALIZATION_RISK` — same-brand native cross-platform adaptation is fine;
several *different* channels making near-identical content at once is flagged
(§38–§39).

## Portfolio Manager skills (§100)

`portfolio_scoring, budget_allocation, capacity_allocation, channel_priority,
diversification, risk_balance, trend_dispatch, experiment_allocation,
profit_optimization`. Capacity allocation / trend dispatch to real workers is
DESIGN_ONLY (the scoring + allocation math is done).

## API

`GET /api/portfolio?workspace_id=` · `GET /api/portfolio/recommendations?workspace_id=`
· `POST /api/portfolio/budget` (`budget.write`) · `POST /api/portfolio/route`.

## Tests

`tests/mb/test_managers.py` — objective changes allocation, hard-cap enforced,
recommendations never auto-delete, exploration floor keeps every channel funded,
routing respects brand policy, cannibalization detection.
