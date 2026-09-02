# REFERENCE DATASET ENGINE

> Code: `backend/app/intel/dataset.py`, `intel/quality.py`. Tables:
> `dataset_records`, `reference_sources`, `reference_analysis`, `reference_chunks`.

## Principle

A reference is not stored as a plain Memory. Each analysis output becomes a
`DatasetRecord` with component scores and a `learning_weight`. **Data volume ≠
quality** — a low-scoring record gets a low weight, not deleted (except
duplicates / spam / rights problems / empty metadata, which are deactivated).

## DataQualityScore (`quality.analyze_quality`)

Components (each 0..1): `source_quality`, `information_density`, `relevance`
(cheap embedding cosine vs the topic), `novelty`, `freshness` (unknown date ⇒
`0.5`, not `0`), `noise`, `technical_usefulness`. `aggregate` is a weighted sum
minus penalties (short body, prompt-injection severity). `learning_weight =
clamp(aggregate, 0.05, 1.0)`. `low_value` when `aggregate < 0.35`.

## Dataset types

`FACT_DATASET`, `KNOWLEDGE_DATASET`, `WRITING_DATASET`, `HOOK_DATASET`,
`SCRIPT_DATASET`, `VIDEO_DATASET`, `EDITING_DATASET`, `BROLL_DATASET`,
`VOICE_DATASET`, `AUDIO_DATASET`, `SUBTITLE_DATASET`, `THUMBNAIL_DATASET`,
`PLATFORM_DATASET`, `COMPETITOR_DATASET`, `TECHNICAL_DATASET`. The
analysis-kind → dataset-type mapping is `router.DATASET_FOR_ANALYSIS`.

## Deduplication (`quality.duplicate_of`)

In order: canonical URL, normalised content hash, cheap simhash text fingerprint
(Hamming ≤ 3), semantic cosine ≥ 0.985, and `text_similarity` combined ≥ 0.92
(reuses `app.governance.originality.text_similarity`). A duplicate reference is
marked `DUPLICATE` with weight 0.1 and is not deep-analysed.

## DataCurator (`dataset.curate`)

Sweeps `dataset_records`, flags `duplicate` / `spam` / `low_quality` /
`wrong_language` / `stale` / `rights_problem` / `bad_metadata`, halves
`learning_weight` per flag, and **deactivates** records with duplicate / spam /
rights problem / bad metadata.

## Multi-brand isolation

Every `DatasetRecord` / `ReferenceSource` / `ReferenceAnalysis` carries
`workspace_id` + `brand_id` + `channel_id`. Reads and the deduplication corpus
are workspace-scoped, so Brand A's references never leak into Brand B.

## Semantic chunking (`extract.chunk`)

Long documents split into `reference_chunks` (`chunk_index`, `heading`,
`position` 0..1, `content_hash`, `token_count`, `text`) so an agent retrieves
only the chunks it needs instead of the whole document.
