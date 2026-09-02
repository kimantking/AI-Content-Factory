# ORIGINALITY ENGINE V2 (Phase 7)

> Code: `backend/app/governance/originality.py`, `phash.py`. Tables:
> `content_fingerprints`, `similarity_results`. Parent: `CONTENT_GOVERNANCE.md`.

## Principle

No single metric blocks. The engine combines independent deterministic signals,
then maps the combined score + transformation + reuse risk to a level and a
decision. There is **no LLM** in the path.

## Signals

| signal | function | robust to |
|---|---|---|
| exact hash | `_hash(text)` | — |
| normalised hash | `_hash(_norm(text))` (lowercase, stop-words dropped) | whitespace / particle noise |
| token Jaccard | `_jaccard(set, set)` | reordering |
| n-gram (3) overlap | `_jaccard(_ngrams…)` | light editing |
| cheap embedding cosine | `analytics.embedding.embed` + `cosine` on script / hook / title | synonym swaps (weak — see limits) |
| image pHash | `phash.phash` = `a:<aHash>|d:<dHash>` (8×8 + 9×8, Pillow only) | resize / re-compress |
| video fingerprint | `build_video_fingerprint` — duration + scene count + per-scene duration profile + visual-type sequence + camera-motion sequence + audio-energy profile + a scene/motion sequence hash | re-encode / recolour / crop / subtitle-colour / music swap |
| transformation score | `transformation_score` — original narration / new analysis / data-viz / commentary / contextualisation / original graphics / visual restructuring / editing structure | — |
| reuse risk | `reused_content_risk` — external-footage ratio, generic-stock ratio, low transformation | — |

`text_similarity` returns `{exact, norm, jaccard, ngram, embed, combined}` where
`combined = max(exact, norm, 0.45·embed + 0.30·jaccard + 0.25·ngram)`.
`video_fp_similarity` averages the structural sub-similarities and is deliberately
insensitive to codec / colour / caption changes.

## Comparison scope (`check_originality`)

This campaign's fingerprints are persisted, then compared against up to 400 recent
`ContentFingerprint` rows **in the same workspace but a different campaign**. Per
prior campaign a combined score is computed as
`0.5·script + 0.2·video + 0.15·hook + 0.15·title`. The best match's
`brand_id` / `channel_id` set the **scope**: `INTERNAL` / `CROSS_BRAND` /
`CROSS_CHANNEL` (cross-brand / cross-channel duplication is a cannibalisation +
originality risk, spec §125).

## Levels & decisions

| combined | transformation | level | decision |
|---|---|---|---|
| ≥ `originality_block_threshold` (0.90) | < 0.40 | `DUPLICATE` | **BLOCK** (hard) |
| ≥ 0.90 | ≥ 0.40 | `REUSED_WITH_TRANSFORMATION` | HUMAN_REVIEW |
| ≥ `originality_review_threshold` (0.78) | — | `HIGH_SIMILARITY` | HUMAN_REVIEW |
| ≥ 0.58 | — | `SIMILAR` | ALLOW |
| else | — | `ORIGINAL` | ALLOW |

`reused_content_risk` verdict overrides: risk ≥ 0.80 → BLOCK, ≥ 0.55 → HUMAN_REVIEW.
The **platform-native check** (`_platform_native_check`) flags near-identical
copy-paste across platform variants (`script ≥ 0.92` and `hook ≥ 0.90`) →
`FIX_REQUIRED` (spec §25-§26). Each run writes a `SimilarityResult` row with the
dimensions, transformation score, reuse risk, scope and human-readable reasons.

## Known limitations

- The embedding cosine is the cheap 24-dim hashed bag-of-tokens
  (`analytics.embedding`) — it catches close paraphrase but misses distant
  paraphrase. This is a known ceiling; a real `EmbeddingProvider` is deferred
  (DECISIONS D61). The hash / Jaccard / n-gram / pHash / video-structure signals
  do not depend on it.
- Perceptual hashing is average+difference hash, not DCT pHash; no scene-level
  CV fingerprint. A heavy fingerprint (e.g. videohash / PDQ) is an OPTIONAL
  adapter, not installed (install policy D67).
- The comparison corpus is this deployment's own fingerprints only — there is no
  external web-duplication / re-upload check.
