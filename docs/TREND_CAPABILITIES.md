# TREND CAPABILITIES

Trend-discovery source availability checked against official developer docs on
**2026-08-31**. Machine-readable copy: `backend/app/trends/capabilities.json`
(served at `GET /api/autopilot/trend-sources`). Re-verify at implementation time.

`auth_status`: `AVAILABLE` · `AUTH_REQUIRED` · `APPROVAL_REQUIRED` · `LIMITED` ·
`DISABLED` · `UNAVAILABLE`. **APPROVAL_REQUIRED / LIMITED / UNAVAILABLE are never
reported as AVAILABLE**, and platforms without a public API are **not scraped**.

Every source below runs in **MOCK** this phase (no real trend credentials).

| Source | Type | Provider | auth_status | Notes |
|---|---|---|---|---|
| **YouTube mostPopular** | OFFICIAL_API | `YouTubeTrendProvider` | AUTH_REQUIRED | `videos.list?chart=mostPopular&regionCode=KR`. Since 2025‑07 this returns the Music/Movies/Gaming charts (the Trending page was deprecated), so it is a *popular-video* signal, not general "what's trending". |
| **Google Trends** | APPROVED_API | `GoogleTrendProvider` | APPROVAL_REQUIRED | Official Trends API announced 2025‑07‑24 but still an **application-gated alpha** in 2026; `pytrends` is archived/unmaintained. Use an approved third-party API or web search — do not scrape. Skipped by default. |
| **Web / News search** | PUBLIC_SEARCH | `WebSearchTrendProvider` / `NewsTrendProvider` | AUTH_REQUIRED | Uses the Phase 1‑A `SearchProvider` (Tavily etc.). Filter recirculated old articles by `published_at`. News is a **trend SIGNAL, never a FACT SOURCE**. |
| **Naver DataLab** | OFFICIAL_API | `NaverTrendProvider` | AUTH_REQUIRED | Official Naver DataLab search-term trend API (client id/secret). Returns relative search-interest ratios by keyword group. |
| **Reddit** | OPTIONAL | `RedditTrendProvider` | AUTH_REQUIRED | API usage terms + rate limits. Community data is a **SIGNAL only**, kept separate from Research fact sources. |
| **Own analytics** | OWN_ANALYTICS | `OwnAnalyticsTrendProvider` | **AVAILABLE** | Evergreen + historical-performance signal from Phase 3 data. Always available. Not a live external trend. |
| **TikTok trends** | OPTIONAL | `TikTokTrendProvider` | UNAVAILABLE | No official public trending-discovery API for third parties (Display API is own-content only). Not scraped. |
| **X trends** | OPTIONAL | `XTrendProvider` | LIMITED | Trends endpoints require a paid API tier; free/basic tiers cannot read. |
| **Threads trends** | OPTIONAL | `ThreadsTrendProvider` | UNAVAILABLE | No official trending-discovery API. Not scraped. |

## Default scan set
`OWN_ANALYTICS` (available) + `AUTH_REQUIRED` sources (mock produces data; a real
run needs the key). `APPROVAL_REQUIRED` / `LIMITED` / `UNAVAILABLE` sources are
**skipped** and reported in `ingest["skipped"]`.

## Cross-cutting rules honoured in code
- No unofficial scraping of a platform that lacks a public API.
- The real `HttpTrendClient` raises `PERMISSION_MISSING` until per-source
  credentials + adapters are wired — it never fabricates trend data.
- `TrendSource.value_score` is adjusted from observed outcomes (Score Calibration),
  so a source that historically produced bad picks is de-weighted.
