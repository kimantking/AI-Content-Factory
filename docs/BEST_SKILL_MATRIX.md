# BEST SKILL MATRIX

GitHub Best-of-Breed Audit — step 2. For each major agent/engine: current
skills, GitHub candidates compared, the specific features worth adopting, and the
decision (with implementation type and reason).

Reviewed 2026-08-31. Inputs: `docs/AGENT_SKILL_INVENTORY.md` + GitHub/web survey
(sources listed at the end). Scores are **/80** (8 axes × /10: Architecture,
Feature, Maintenance, Production, Integration, License, Performance, Project-Fit).
Scores rank candidates within a row; the **Decision** line is the human call and
sometimes overrides the top score (spec §5).

Implementation types (spec §7): `DIRECT_DEPENDENCY` · `ADAPTER` · `ALGORITHM_PORT`
· `ARCHITECTURE_PATTERN` · `PROMPT_PATTERN` · `REFERENCE_ONLY` · `DO_NOT_USE`.

Status: `APPLIED` (in code this session) · `RECOMMENDED` (low-risk, do next) ·
`RECOMMENDED_FOR_LATER` (real benefit, regression risk too high to bundle here) ·
`NO_CHANGE` (current implementation is the right call).

---

## AGENT: Master Orchestration / Director  (`app/agents/graph.py`, `autopilot/controller.py`)

**Current skills:** two hand-wired LangGraph `StateGraph`s (content + media) with a
Postgres checkpointer; a bespoke Python autopilot loop on top. `langgraph==0.2.60`.

**GitHub candidates:**
| Repo | License | Score /80 | Note |
|---|---|---|---|
| LangGraph (current) upgraded to 0.6.x + `langgraph-supervisor` | MIT | **66** | same runtime, gains `interrupt()` HITL, `Command` dynamic routing, node caching, durability modes, deferred nodes, `create_supervisor()` |
| LangChain **Deep Agents** (`deepagents`) | MIT | 58 | planning-tool + sub-agent + virtual-FS + long system-prompt pattern; good for the *research* sub-agent, not the whole pipeline |
| CrewAI | MIT | 47 | role/goal/task nice for readability, but a second runtime — rejected by spec §10/§24 |
| Microsoft AutoGen / AG2 | Apache-2.0 | 45 | conversational multi-agent; heavier, second runtime |
| MetaGPT | MIT | 40 | SOP/"software company" metaphor doesn't fit a content pipeline |
| PydanticAI graph | MIT | 44 | clean, but migrating the runtime is pure regression risk for no capability we lack |

**Best features to adopt:**
- LangGraph 0.6: **`interrupt()` / `Command(resume=…)`** → real in-graph human approval (replaces the DB-poll approval in `autopilot/bridge.py`).
- **Node-level caching** (`CachePolicy`) → skip re-running deterministic nodes on resume/retry.
- **`durability="sync"|"async"|"exit"`** awareness → today we run the implicit default.
- **`langgraph-supervisor` / `Command`-based routing** → the ARCHITECTURE_PATTERN for a future SkillRouter (route to only the nodes a campaign needs).
- Deep Agents: **explicit planning tool + isolated sub-agent context** for the Research agent.

**Decision:** keep LangGraph as the single runtime (spec §10). `RECOMMENDED_FOR_LATER`:
bump `langgraph` 0.2.60 → current, adopt `interrupt()` for HITL and node caching.
`ARCHITECTURE_PATTERN` (not a dep): Deep Agents planner+sub-agent shape for B1.
**Implementation:** dependency bump + `ARCHITECTURE_PATTERN`.
**Reason:** the pin is ~8 months stale and we're hand-rolling things 0.6 gives for
free (HITL, caching), but a version bump touches every graph test → not safe to
bundle with this audit. No second runtime.

---

## AGENT: Research Agent  (`app/agents/nodes.py::_do_research`)  ★ core, deep-dive

**Current skills:** one search call per pass; fixed fix-pass query string; one LLM
call synthesises a Knowledge Pack; 2 fix passes max; `<2 sources` → error.

**GitHub candidates:**
| Repo | License | Score /80 | Note |
|---|---|---|---|
| **gpt-researcher** (assafelovic) | Apache-2.0 | **63** | query decomposition → N parallel sub-queries → scrape+aggregate → cited report; "research then write" split matches ours |
| **STORM / Co-STORM** (stanford-oval) | MIT | 60 | perspective-guided question generation, outline-driven depth, multi-perspective conversation → simulated interviews |
| LangChain **local-deep-researcher** | MIT | 57 | tight iterative loop: generate query → search → **reflect / find knowledge gap** → loop until satisfied; explicit stopping criterion |
| **DeerFlow** (ByteDance) | MIT | 52 | plan→research→report multi-agent; heavier, LangGraph-based |
| **OpenDeepResearcher** / nanoDeepResearch | MIT | 44 | minimal reference implementations |
| Tongyi DeepResearch / WebSailor | Apache-2.0 | 46 | strong web-reasoning, model-coupled, too heavy |

**Best features to adopt:**
- gpt-researcher: **deterministic query decomposition** — expand `{topic + keywords}` into 3–4 sub-queries hitting different angles (definition, statistics, counter-evidence, recent/primary).
- gpt-researcher: **run sub-queries, then dedup+merge results by URL/domain**; prefer domain diversity.
- local-deep-researcher: **reflection step** — after fact-check, ask "which claims are still weak / uncovered?" and target the next fix query at *that gap* (we currently just re-search a fixed string).
- local-deep-researcher: **explicit stopping criterion** — stop when coverage ≥ X or new results stop adding facts, not only when `fact_score` clears.
- STORM: **primary-source preference** + a simple domain-authority tier.

**Decision:**
- `APPLIED` (this session, `ALGORITHM_PORT`, minimal): the fix pass now rotates
  through 3 **angle-varied deterministic queries** (`_FIX_QUERY_ANGLES` in
  `nodes.py`) instead of one fixed string — same call count / cost, better
  coverage. First concrete piece of the gpt-researcher pattern.
- `RECOMMENDED`: deterministic multi-sub-query fan-out on the **first** research
  pass (2–3 queries, merge+dedup by URL), behind the existing single LLM
  synthesis. Low risk once cost-assert tests are updated.
- `RECOMMENDED_FOR_LATER`: gap-targeted reflection loop (needs the fact-checker to
  emit an "uncovered claims" list — couples B1↔B5) and a page-fetch/extract step
  (snippets → full text) via a `PageReader` provider (Firecrawl/Trafilatura, MIT).
**Implementation:** `ALGORITHM_PORT` + `PROMPT_PATTERN`. No dependency.
**Reason:** the single-query, snippet-only research step is the audit's #1 quality
gap; gpt-researcher/STORM/local-deep-researcher all converge on decompose→
parallel→reflect, and it ports as plain code without a framework.

---

## AGENT: Fact Checker  (`app/agents/nodes.py::fact_check_node`)  ★ core, deep-dive

**Current skills:** one LLM call labels the facts research happened to emit
(VERIFIED/PARTIALLY/UNVERIFIED/CONTRADICTED + confidence + source_ids + reason);
`fact_score` gates the fix loop; unverified facts blocked in `script_qa`.

**GitHub candidates:**
| Repo | License | Score /80 | Note |
|---|---|---|---|
| **Loki** (Libr-AI/OpenFactVerification) | Apache-2.0 | **64** | 5-step pipeline: decompose → checkworthiness → query-gen → retrieve → verify; multilingual; built for practical latency/cost |
| **OpenFactCheck** | Apache-2.0 | 59 | clean `claim_processor / retriever / verifier` abstraction — mix components from different systems |
| **FactScore** (shmsw25) | MIT | 52 | atomic-fact decomposition + support precision metric; great decomposition idea, dataset-oriented |
| **SAFE** (Google DeepMind, "long-form factuality") | Apache-2.0 | 55 | split into individual facts → each gets its own Google queries → rate supported/not; multi-step per claim |
| Hybrid KG+LLM+Search fact-check (2511.03217) | research/MIT | 41 | KG lookup → LLM classify → web-agent fallback; needs a KG |

**Best features to adopt:**
- Loki / FactScore / SAFE: **atomic claim splitting** — decompose each candidate
  fact into independently-checkable atomic claims (deterministic split on
  conjunctions/clauses first, LLM only if needed) *before* verification.
- Loki: **check-worthiness filter** — skip verifying opinion/definitional lines,
  spend the LLM budget on factual+consequential claims.
- Loki / SAFE: **per-claim query generation + retrieval** — a shaky claim gets its
  own targeted search instead of relying on the original snippets.
- SAFE: **cross-source agreement count** — "supported by N independent domains"
  feeds confidence, not just the model's self-reported number.
- OpenFactCheck: formalise our step as `claim_processor → retriever → verifier`
  so each is swappable.

**Decision:** `RECOMMENDED_FOR_LATER` — high value, but it changes what the
fact-check LLM sees and therefore the persisted `VerifiedFact` rows, and
`test_pipeline_integration.py` / `test_script_only_uses_usable_facts` assert on
those. Do it as its own change with fresh fixtures:
1. `ALGORITHM_PORT` Loki's atomic-split + check-worthiness (deterministic pre-step).
2. `ARCHITECTURE_PATTERN` OpenFactCheck's 3-part interface.
3. `PROMPT_PATTERN` SAFE's per-claim "supported by independent sources?" rubric.
**Reason:** verifying snippet-level compound "facts" in one shot is the weakest
link in the truth chain; the OSS consensus (Loki/SAFE/FactScore) is atomic +
per-claim retrieval. Not a dependency — the algorithms are small.

---

## AGENT: Web Search / Source Ranking  (`app/providers/*search*`)

**Current skills:** `SearchProvider` Protocol; deterministic mock; one real vendor
(Tavily, pinned old); snippets only; sources kept in provider order.

**GitHub candidates:** SearXNG (AGPL-3 — self-host meta-search, **DO_NOT_USE as a
linked dep**, fine as an external service via HTTP), Firecrawl (AGPL-3 core / SDK
MIT — scrape+extract), Trafilatura (Apache-2.0 — robust main-text extraction),
Exa/Brave/Serper SDKs (MIT clients, paid APIs), `newspaper4k` (MIT).

**Best features to adopt:** add a **`PageReader` provider** (fetch URL → main text)
so research reads sources, not snippets — Trafilatura (Apache-2.0) is the
dependency-light pick; second real `SearchProvider` (Brave/Exa) for diversity;
deterministic **source ranking**: domain-authority tier × recency × dedup-by-domain.

**Decision:** `RECOMMENDED` — add `PageReader` (Trafilatura, `ADAPTER`) + a
deterministic source-ranking function (`ALGORITHM_PORT` from gpt-researcher).
Bump `tavily-python`. `DO_NOT_USE`: SearXNG/Firecrawl core as in-process deps (AGPL).
**Reason:** snippet-only research caps fact-check quality no matter how good B5 gets.

---

## ENGINE: Knowledge Pack / RAG  (`Campaign.knowledge_pack`)

**Current skills:** a single JSON blob in graph state + DB; no store, no retrieval.

**GitHub candidates:** LightRAG (MIT), MiniRAG (MIT), nano-graphrag (MIT),
Microsoft GraphRAG (MIT, heavy), LlamaIndex (MIT).

**Best features to adopt:** LightRAG/MiniRAG **entity+relation extraction into a
lightweight graph** + **dual-level retrieval** — so a scene prompt can pull "the 3
facts about *this* sub-topic" instead of the whole pack, and packs become reusable
across campaigns on the same cluster.

**Decision:** `NO_CHANGE` for now / `RECOMMENDED_FOR_LATER`. For a single
short-form piece the whole-pack-in-context approach is fine and simplest. Revisit
LightRAG-style structuring only when (a) packs are reused across campaigns or
(b) long-form output makes selective retrieval necessary. `ARCHITECTURE_PATTERN`
if/when adopted — not a dependency (nano-graphrag is ~1k LOC to reference).
**Reason:** adding a graph store now is architecture bloat (spec §24) for a
capability the product doesn't need at Phase 5 scope.

---

## AGENT: Content Strategist / Hook / Script / Script-QA  (`app/agents/nodes.py`)

**Current skills:** one LLM call each; hook self-scores; script draft → natural
pass → fact-preservation check; QA = LLM pass/fail + deterministic slop gate.

**GitHub candidates / references:** ShortGPT (MIT), MoneyPrinterTurbo (MIT),
`wordware`/`promptfoo` (MIT, eval), `dspy` (MIT — prompt optimisation),
storytelling-beat-sheet references (no canonical repo).

**Best features to adopt:**
- ShortGPT/MoneyPrinterTurbo: **explicit short-form beat structure** (hook →
  context → payoff → turn → CTA) as a `PROMPT_PATTERN` for the script node, with
  scene-count/duration targets per beat.
- **Hook generation against learned `hook_type` performance** — pass the top
  Phase-3 `HOOK` memories into the hook prompt so it biases toward what worked
  (data exists in F6, not wired to C2).
- `dspy`-style: treat the slop threshold + QA rubric as **calibratable** against
  Phase-3 outcomes rather than hand-set constants.
- **Multiple strategies generated → scored → best selected** (cheap; one extra
  parse, no extra call if the prompt returns a list).

**Decision:** `RECOMMENDED` (`PROMPT_PATTERN`, no dep): beat-structured script
prompt + feed `HOOK`/`SCRIPT` memories into C2/C3 (closes an existing
Phase-3→Phase-1 loop). `RECOMMENDED_FOR_LATER`: calibrate slop/QA thresholds from
Phase-3 (needs a calibration job like `autopilot/calibration.py`).
**Reason:** the writing agents are fine structurally; the gap is that learned
knowledge (F6) never reaches them at generation time.

---

## ENGINE: Natural Writing / AI-Slop / Naturalness  (`app/naturalness/*`)  ★ core

**Current skills:** deterministic `score_ai_slop` (8 tells + burstiness);
deterministic rhythm/opener/connective cleanup as the mock-mode natural pass;
LLM rewrite + fact-preservation revert with a real provider; per-brand
`VoiceProfile` (sample-derived, 3 numeric proxies); rotating CTA library.

**GitHub candidates:**
| Repo | License | Score /80 | Note |
|---|---|---|---|
| **textstat** | MIT | 55 | readability/grade-level metrics — a real, cheap naturalness signal we lack |
| **textdescriptives** (spaCy) | Apache-2.0 | 52 | coherence, dependency-distance, information-density metrics |
| blader/**humanizer** | MIT | 44 | "AI tell" list — already `REFERENCE_IMPLEMENTATION` in our registry; **not** a detector-evasion tool |
| `lexical-diversity` / MTLD implementations | MIT | 48 | type-token ratio / MTLD → real "vocabulary variety" number |
| GPTZero / detector repos | mixed | — | `DO_NOT_USE` — spec §15 forbids AI-detector-evasion framing |

**Best features to adopt:**
- textstat: **grade-level + sentence-complexity** as an explicit sub-signal (not a tell — a quality gate: "reads like a 6th-grade lecture" vs "natural spoken").
- lexical-diversity: **MTLD / type-token ratio** → a deterministic "vocabulary is repetitive" tell (we have *phrase* repetition, not *lexical*).
- **semantic repetition**: cosine between successive sentences (reuse `embed`) → "same idea restated" tell, which the current bag-of-phrases misses.
- textdescriptives: **discourse coherence** proxy.

**Decision:** `RECOMMENDED` (not applied here — `test_naturalness.py` asserts hard
`score <= 20` boundaries and any new positive sub-score can tip them; needs the
threshold re-tuned in the same change). Add as `DIRECT_DEPENDENCY` (`textstat`,
MIT, zero transitive deps) + `ALGORITHM_PORT` (MTLD, semantic-repeat). Keep the
strict "this is content quality, NOT detector evasion" framing (spec §15).
**Reason:** the slop score is good but purely surface-level; readability + lexical
diversity + semantic-repeat are cheap, deterministic, and catch failure modes it
can't see. `VoiceProfile.analyze_samples` should also gain an n-gram style
fingerprint (`ALGORITHM_PORT`).

---

## ENGINE: Embedding / Clustering / Dedup  (`app/analytics/embedding.py`)  ★ core, highest leverage

**Current skills:** 24-dim hashed bag-of-tokens + ~20-word synonym map + Korean
particle stripping; `cosine` + `assign_cluster`. Powers **every** cluster / dedup /
memory-retrieval / topic-fatigue / creative-diversity decision in Phase 3 & 4.

**GitHub candidates:**
| Repo | License | Score /80 | Note |
|---|---|---|---|
| **model2vec** (MinishLab) | MIT | **62** | static distilled embeddings, **no torch**, ~30MB, µs-latency, multilingual models; drop-in real semantics |
| **fastembed** (Qdrant) | Apache-2.0 | 60 | ONNX runtime, small, `bge-small`/`multilingual-e5-small`, no torch |
| sentence-transformers + `paraphrase-multilingual-MiniLM` / `bge-m3` | Apache-2.0 | 54 | best quality, but pulls torch (~1GB) — heavy for the gain |
| `fasttext` (cc.ko) | MIT | 40 | classic, large vector files, maintenance stale |

**Best features to adopt:** replace the hashed vector with **real multilingual
static/ONNX embeddings** behind an `EmbeddingProvider` adapter — mock stays the
default in tests, real one is opt-in.

**Decision:** `RECOMMENDED_FOR_LATER` with a concrete plan (do NOT bundle here):
1. `ADAPTER`: `EmbeddingProvider` Protocol; `HashedEmbeddingProvider` (current) is
   the default; `Model2VecEmbeddingProvider` (`DIRECT_DEPENDENCY`, MIT) opt-in.
2. Route `embed()` / `cosine()` / `assign_cluster()` through the provider.
3. Re-baseline: cluster ids change → analytics + autopilot fixtures need a
   regenerate; run both suites, tune the `assign_cluster` threshold.
**Reason:** this is the single highest-leverage upgrade in the whole system
(clustering, dedup, memory relevance, topic fatigue, diversity all improve at
once) — and exactly why it's too much regression surface to change in an audit
pass. It gets its own task. model2vec/fastembed are the finds: real semantics
without the torch tax.

---

## ENGINE: Learning Engine / Memory / Experiments  (`app/learning/*`)  ★ core

**Current skills:** deterministic median-lift pattern mining with a false-learning
guard (`_consistent`), evidence+n+confidence on every memory, 16 memory types,
bounded relevance-ranked retrieval, staleness deprecation, advisory-only
injection; sequential (non-A/B) experiments.

**GitHub candidates:**
| Repo | License | Score /80 | Note |
|---|---|---|---|
| **LangMem** (LangChain) | MIT | **58** | semantic/episodic/procedural types, fact+behaviour extraction, sits on the LangGraph store we already run |
| **Mem0** | Apache-2.0 | 57 | parallel semantic+keyword+entity retrieval **fusion**; graph + vector; managed option |
| **Letta / MemGPT** | Apache-2.0 | 55 | OS-tier memory (core/archival/recall), **self-editing memory blocks** |
| **Graphiti / Zep** | Apache-2.0 | 56 | **temporal knowledge graph** with fact-validity intervals → memory-conflict + "true as of" |
| **pybandits** (Playtika) | MIT | 54 | Thompson-sampling sMAB/cMAB — for the experiment engine |
| **river** | BSD-3 | 50 | online ML + bandits (considered & deferred in Phase 4) |
| **contextualbandits** (Cortes) | BSD-2 | 48 | contextual bandit algorithms |

**Best features to adopt:**
- Mem0: **multi-signal retrieval fusion** — our `retrieve_memories` is one score
  (topic-cosine × confidence × recency); add parallel keyword + dimension-exact
  passes and fuse ranks. Cheap, deterministic.
- Graphiti/Zep: **temporal validity + conflict resolution** — when two memories
  on the same key disagree, keep the newer/higher-n and mark the other superseded
  (today `upsert_memory` just overwrites by key, losing history).
- LangMem: **episodic memory** — store notable past campaigns as retrievable
  episodes ("last time we did an ELECTION topic on TikTok, QA failed twice").
- pybandits: replace the sequential experiment picker with **Thompson sampling**
  over variant arms (hook_type, cta_type, subtitle_style) — principled
  explore/exploit, still logged.
- Letta: **self-editing** is interesting but conflicts with our "AI never mutates
  its own rules" principle — adopt the *block* structure, not the self-edit.

**Bug found during the audit:** `app/learning/experiment.py:85`
`rng = random.Random(seed) if seed else random` — when called unseeded it uses the
**process-global `random` module**, so experiments are non-reproducible *and* any
other code that touches the global RNG (e.g. retry jitter) silently changes
experiment outcomes. `RECOMMENDED` fix: always use a dedicated
`random.Random(seed or <stable-hash-of-experiment-id>)`.

**Decision:**
- `RECOMMENDED` (`ALGORITHM_PORT`, no dep): Mem0-style retrieval fusion in
  `retrieve_memories`; memory-supersede instead of silent overwrite; fix the
  unseeded-global-RNG fallback above.
- `RECOMMENDED_FOR_LATER` (`DIRECT_DEPENDENCY`, MIT): `pybandits` for F8 — real
  benefit, but changes experiment outcomes that Phase-3 tests assert on.
- `ARCHITECTURE_PATTERN`: LangMem episodic type (add `EPISODE` to `MEMORY_TYPES`).
- `DO_NOT_USE` as runtime deps: Mem0/Letta/Zep servers (we don't need a service;
  the DB + `embed` provider is enough) — pattern-only.
**Reason:** the learning engine's *statistics* are already conservative and sound;
the gaps are retrieval (single-signal), history (overwrite loses the trail), and
experiment selection (not principled). All portable as small code except the
bandit, which earns a dependency.

---

## ENGINE: Trend Signals / Opportunity Scoring / Calibration  (`app/autopilot/*`)  ★ core

**Current skills:** pure 0–100 signal functions (velocity/accel/status/freshness/
competition/saturation/risk/difficulty/…) with **hand-set coefficients**; 17-dim
opportunity formula with **hand-authored per-objective weights**; calibration
nudges only `TrendSource.value_score`.

**GitHub candidates:**
| Repo | License | Score /80 | Note |
|---|---|---|---|
| **ruptures** | BSD-2 | **58** | offline change-point detection — real "trend broke / accelerated" segmentation vs our second-difference heuristic |
| statsmodels **STL** | BSD-3 | 56 | seasonal-trend decomposition → separate genuine trend from weekly noise (we have neither) |
| **ADTK** | MPL-2.0 | 52 | rule/unsupervised TS anomaly primitives (persistence, level-shift, volatility) |
| **STUMPY** (matrix profile) | BSD-3 | 51 | motif/anomaly discovery in interest series; heavier |
| **Merlion** (Salesforce) | BSD-3 | 49 | full TS framework — too much for our need |
| **PyOD** | BSD-2 | 48 | outlier detection for the performance-score anomaly flag (F3) |

**Best features to adopt:**
- ruptures: **change-point detection on `interest_series`** → a principled
  `trend_status` / acceleration signal instead of `accel * 220`.
- STL: **de-seasonalise** interest + publish-hour data before scoring (kills a
  class of false "fatigue"/"decline" calls).
- ADTK: **level-shift + volatility** primitives for burst detection.
- PyOD: swap `performance.py`'s median-based outlier test for a real detector
  (IsolationForest / MAD) — better false-learning protection.
- **Calibration should tune the scorer**, not only source weights: log predicted
  vs actual per dimension, fit simple per-objective weight adjustments (ridge)
  offline, version as `opportunity_formula_v2`.

**Decision:** `RECOMMENDED_FOR_LATER`. Highest-value item: extend
`autopilot/calibration.py` to learn `_WEIGHTS` adjustments (no new dep — it's a
least-squares fit over data we already store) and stamp a new formula version so
Phase-3 backtest can compare. Then `DIRECT_DEPENDENCY` `ruptures` (BSD-2, light)
for change-point-based velocity/acceleration, behind the existing pure-function
interface so mock tests are unaffected. `ALGORITHM_PORT` STL de-seasonalisation.
**Reason:** "hand-tuned coefficients that are never calibrated" is a core audit
finding; the fix is mostly using data we already collect, plus one small,
well-maintained TS library for the signal that's genuinely hard to hand-roll
(change-point detection).

---

## ENGINE: TTS / Voice Prosody / Speech Alignment  (`app/media/word_timing.py`, media providers)

**Current skills:** `mock_tts` writes silence; `EstimatorAlignmentProvider`
(proportional duration split — honest, but wrong for real speech);
`WhisperXAlignmentProvider` is a **stub that raises NotImplementedError**.

**GitHub candidates:**
| Repo | License | Score /80 | Note |
|---|---|---|---|
| **faster-whisper** (SYSTRAN) | MIT | **64** | CTranslate2 Whisper, ~4× faster, low VRAM — the STT base |
| **WhisperX** (m-bain) | BSD-2-Clause | **62** | faster-whisper + wav2vec2 **forced alignment** + diarization → real word timestamps (finishes our stub) |
| **stable-ts** | MIT | 57 | word timestamps + regrouping without a separate aligner |
| **Kokoro-82M** (hexgrad) | Apache-2.0 | 60 | 2025-26 standout open TTS — small, high quality, multilingual incl. Korean |
| **Piper** (rhasspy/OHF) | MIT | 56 | fast fully-offline neural TTS; lower quality than Kokoro but tiny |
| **F5-TTS** / XTTS-v2 | MIT / **Coqui non-commercial** | 45 | XTTS licence blocks commercial → `DO_NOT_USE`; F5-TTS ok but heavy |
| rany2/**edge-tts** | LGPL-3 | 30 | already flagged: MS-ToS risk, dev-only |

**Best features to adopt:**
- **Finish the WhisperX alignment adapter** — the interface already exists
  (`AlignmentProvider`), the estimator stays the offline default, WhisperX
  becomes the real path (`DIRECT_DEPENDENCY`, BSD-2, optional import).
- **Real `TTSProvider`**: Kokoro (Apache-2.0) as the quality default, Piper (MIT)
  as the ultra-light offline option — both `DIRECT_DEPENDENCY` behind the
  existing `TTSProvider` interface.
- Prosody: WhisperX word timings + energy → drive subtitle **emphasis** styling
  and image-motion beats (currently round-robin).

**Decision:** `RECOMMENDED` — implement `WhisperXAlignmentProvider` for real
(`ADAPTER` over `DIRECT_DEPENDENCY` whisperx/faster-whisper, BSD-2/MIT, lazy
import, estimator fallback preserved). `RECOMMENDED_FOR_LATER`: Kokoro/Piper
`TTSProvider` adapters (needs model download infra + audio fixtures). `DO_NOT_USE`:
XTTS/Coqui (non-commercial), edge-tts as production default.
**Reason:** the "optional real alignment" story is explicitly unfinished in code
(stub raises); WhisperX is the obvious, correctly-licensed completion and the
interface is already there.

---

## ENGINE: Automatic Video Editing / Scene Detection / Silence  (`app/media/ffmpeg.py`)

**Current skills:** `detect_silence` / `detect_black` via FFmpeg stderr; used for
QA only; **no cut-list editor**; renderer concatenates planned scenes.

**GitHub candidates:** **auto-editor** (WyattBlue, Unlicense/public-domain — cut
list from silence/motion with margins), **PySceneDetect** (BSD-3 — content-aware
shot boundaries), `ffsubsync` (MIT — sub/audio sync), MoneyPrinterTurbo /
opensource-clipping (MIT — kinetic captions, face-tracking, CLIP b-roll).

**Best features to adopt:**
- auto-editor: **silence-removal cut list with configurable margins** (keep
  80–350 ms around speech) — `ALGORITHM_PORT` into the Edit Engine for when real
  footage exists.
- PySceneDetect: **don't cut across a detected shot boundary** — `DIRECT_DEPENDENCY`
  when real footage arrives.
- opensource-clipping: **CLIP visual-similarity b-roll matching** (transcript
  segment → best clip) — this is the semantic upgrade for `mock_stock` search and
  the Visual Director's "no trigger word → generic image" weakness.

**Decision:** `RECOMMENDED_FOR_LATER` — these only bite with real footage / real
media providers, which don't exist yet. Keep both in `OPEN_SOURCE_COMPONENTS.md`
(already there) as `ALGORITHM_PORT` (auto-editor) and `DIRECT_DEPENDENCY`
(PySceneDetect) to wire when a real `VideoProvider`/`StockProvider` lands.
**Reason:** correct call already recorded in Phase 1-B; no regression-safe work to
do now.

---

## ENGINE: Subtitle / Caption Animation  (`app/media/subtitles.py`)

**Current skills:** strong Korean phrase-unit line breaking; SRT/ASS/JSON/Pillow
outputs; number/keyword highlight; **no kinetic/karaoke word reveal** (the Pillow
path renders a static plate; `animation="pop"` is an unused flag).

**GitHub candidates:** `ass` / `pysubs2` (MIT — ASS karaoke `\k` tags),
CapCut-style caption repos, opensource-clipping "kinetic karaoke subtitles" (MIT),
Remotion caption templates (source-available).

**Best features to adopt:** **ASS `\k` karaoke tags** driven by our per-word
timings (we already have `WordTiming`) — the ASS writer can emit real word-timed
reveal with zero new dependency; per-word pop in the Pillow burn-in path.

**Decision:** `RECOMMENDED` (`ALGORITHM_PORT`, no dep) — extend `write_ass()` to
emit `\k`/`\kf` karaoke timing from `WordTiming`, and add an optional per-word
reveal to `render_overlays()`. Low risk (additive; existing outputs unchanged
unless a `karaoke=True` flag is set). `pysubs2` (MIT) only if the hand-rolled ASS
writer gets unwieldy.
**Reason:** we already compute everything karaoke captions need; it's a small
additive win on a format we control, and "caption animation" is a named audit gap.

---

## ENGINE: Thumbnail Generation  (`app/media/thumbnail.py`)

**Current skills:** 3 hand-templated concepts, Pillow composite (code renders
text, never the model), deterministic proxy `_score` with two constants literally
`0.7`.

**GitHub candidates:** **thumbor** (MIT — saliency/face-aware smart crop),
`rembg` (MIT code / model weights caveat — subject cutout), OpenCV
`saliency` module (BSD — spectral-residual / fine-grained saliency), ThumbCraft
(MIT — high-CTR SVG template set, reference).

**Best features to adopt:**
- OpenCV saliency (spectral residual) or thumbor's algorithm: **compute a
  saliency map → place text in the least-salient region** (text-safe placement) —
  `ALGORITHM_PORT`, cv2 is already transitively near via matplotlib/Pillow stack
  but not a dep; spectral-residual saliency is ~20 lines of numpy.
- thumbor: **face/subject box avoidance** for text.
- ThumbCraft: proven **layout templates** as a reference for `propose_concepts`.

**Decision:** `RECOMMENDED_FOR_LATER` — real value is low while backgrounds are
`mock_image` gradients; revisit when a real `ImageProvider` lands. Then
`ALGORITHM_PORT` spectral-residual saliency (numpy-only) for text placement and
replace the `0.7` constants with saliency-contrast-derived scores. Keep A/B
variants + a CTR feedback hook (Phase 3 already stores `thumbnail` as a memory
dimension — wire it).
**Reason:** avoid architecture bloat for a mock-only benefit; the plan is cheap
(numpy) when it matters.

---

## SUBSYSTEM: Publishing  (`app/publishing/*`)

**Current skills:** capability-honest `PublisherProvider` interface, 10 mock
providers, OAuth+Fernet, scheduler/idempotency/reconcile/retry/DLQ/webhooks —
genuinely production-shaped; **no real platform SDK wired**.

**GitHub candidates:** **official SDKs** — `google-api-python-client` (Apache-2.0,
YouTube Data v3), `facebook-python-business-sdk` / Graph API (platform licence),
TikTok Content Posting API (official), `atproto` (MIT, Bluesky), `tweepy`
(MIT, X) / `praw` (BSD, Reddit). Aggregators: **Postiz** (AGPL-3 — `DO_NOT_USE`
as a dep), **Mixpost** (paid licence), **Ayrshare** (paid API, MIT client).

**Best features to adopt:** none architectural — our engine already does the hard
parts (idempotency, reconcile, DLQ, capability model). What's missing is just the
**real adapters**, and the spec (§17) says **official API first, no browser bots
where an API exists**.

**Decision:** `REFERENCE_ONLY` for all aggregators; when credentials arrive,
implement each `PublisherProvider` against its **official SDK** (`ADAPTER`).
`DO_NOT_USE`: Postiz/Mixpost as dependencies (licence), unofficial browser-bot
libraries (spec §17). `NO_CHANGE` to the engine.
**Reason:** the publishing engine is one of the strongest parts of the codebase;
the OSS survey confirms there's nothing better to borrow — just credentials to add.

---

## SUBSYSTEM: Analytics Collection / Performance / Revenue  (`app/analytics/*`)

**Current skills:** capability-gated providers (unsupported metric → null, never
0), time-series snapshots, feature store, median/percentile baselines,
channel-relative scoring, outlier/anomaly exclusion. Mock only.

**GitHub candidates:** official analytics SDKs (YouTube Analytics API —
`google-api-python-client`, Apache-2.0; Meta Insights — Graph). Stats libs:
**PyOD** (BSD-2 — better outlier detection), **statsmodels** (BSD-3 — seasonality
normalisation), `scipy.stats` (BSD — confidence intervals).

**Best features to adopt:** PyOD/MAD for `is_outlier`; statsmodels STL to
day-of-week-normalise before scoring; a confidence interval on
`ContentPerformanceScore` itself.

**Decision:** `RECOMMENDED_FOR_LATER` (`ALGORITHM_PORT` MAD outlier — no dep;
`DIRECT_DEPENDENCY` statsmodels only if STL is adopted for trends too, so they
share it). `ADAPTER` real analytics providers when credentials land. `NO_CHANGE`
to the capability model — it's exactly right.
**Reason:** the "never fake a zero" design is a strength to preserve; the only
soft spots are the simplicity of the outlier test and no seasonality control,
both small.

---

## SUBSYSTEM: Error Recovery / Durable Execution / Retry  (`app/providers/retry.py`, `app/publishing/retry.py`, Celery, LangGraph)

**Current skills:** LangGraph Postgres checkpointer (journal+resume); Celery
at-least-once; app idempotency keys + crash reconcile; Phase-5 circuit breaker,
DLQ + non-retryable guard, `JobLease` duplicate guard, stuck-job scan. **Three
separate retry implementations**; `tenacity` is a dependency but barely used; no
saga/compensation for multi-step partial failure.

**GitHub candidates:**
| Repo | License | Score /80 | Note |
|---|---|---|---|
| **tenacity** (already a dep) | Apache-2.0 | **60** | unify all retry on one policy layer (stop/wait/retry-if predicates, jitter) |
| LangGraph 0.6 durability modes + node cache | MIT | 58 | resume/replay we partly reinvent |
| **DBOS-Transact-py** | MIT | 52 | Postgres-native durable exec + exactly-once — but a second runtime (spec §10) |
| Temporal / Restate / Inngest | MIT/Apache | 40 | dedicated cluster / second runtime — `DO_NOT_USE` per spec §10/§24 |
| `stamina` (hynek) | MIT | 55 | opinionated tenacity wrapper; nice, but tenacity's already in |

**Best features to adopt:**
- **tenacity**: collapse `providers/retry.py` + `publishing/retry.py` onto one
  `retry` policy object per error class (jittered exponential backoff, per-class
  `stop`, non-retryable predicate) — kills the "three mechanisms" finding and
  removes a dead dependency.
- Saga pattern: a **compensation hook** in `autopilot/bridge.py` — if produce
  succeeds but multi-platform scheduling half-fails, record the partial state and
  a compensating action instead of leaving orphans.
- LangGraph: explicit `durability=` + node `CachePolicy`.

**Decision:**
- `APPLIED` (this session): `call_with_retry` now uses **full-jitter exponential
  backoff** (AWS pattern) instead of fixed linear sleep — the one safe piece.
- `RECOMMENDED` (`REFERENCE_ONLY` → adopt tenacity): unify the two hand-rolled
  retry modules onto `tenacity` with per-error-class policies. Medium risk
  (touches core + publishing paths); do as its own change with the full suite.
- `RECOMMENDED_FOR_LATER`: saga/compensation in the autopilot bridge; LangGraph
  durability/cache config (bundled with the 0.6 bump).
- `DO_NOT_USE`: Temporal/Restate/DBOS as a second runtime (spec §10).
**Reason:** the *guarantees* are already solid (no dup campaign / no dup post,
enforced at the DB); the debt is three retry code paths + an unused dep +
no compensation for one partial-failure shape.

---

## SUBSYSTEM: Human Approval  (`autopilot/bridge.py`, ops flags)

**Current skills:** risk matrix forces MANUAL/SEMI_AUTO run modes; approval is a
DB-state poll; ops actions need `confirm=true`.

**Best feature to adopt:** LangGraph **`interrupt()` / `Command(resume=…)`** —
first-class in-graph pause for approval, resumable by the checkpointer we already
run.

**Decision:** `RECOMMENDED_FOR_LATER` (`ARCHITECTURE_PATTERN`, bundled with the
LangGraph 0.6 bump). **Reason:** cleaner than polling and free with the upgrade,
but not worth a version bump on its own.

---

## SkillRouter / Skill Metadata / Skill Versioning  (spec §26–§29 — new capability)

**Current state:** every node runs on every campaign; no `skill_id` / cost /
latency / `requires_llm` metadata; prompt versions are tracked
(`prompt_versions` on `ContentFeature`) but skills aren't.

**GitHub inspiration:** LangGraph conditional edges + `Command` routing; Deep
Agents sub-agent gating; `dspy` module registry; feature-flag patterns.

**Best features to adopt:**
- A **`SkillRegistry`**: `skill_id, name, version, category, requires_llm,
  estimated_cost, estimated_latency, dependencies, fallback, quality_impact,
  enabled` (spec §27).
- A **`SkillRouter`**: inputs `(task, content_type, platform, risk, budget,
  quality_profile)` → `{required, optional, skipped}` skills (spec §26). E.g.
  FAST profile skips the LLM natural-writing pass and extra QA; a text-only
  platform skips scene/visual skills.
- **Skill versioning tags** (`hook_generation_v2`, `subtitle_breaking_v3`) wired
  into `ContentFeature` alongside `prompt_versions` so Phase-3 can measure a
  skill change's effect (spec §28–§29).

**Decision:** `RECOMMENDED` — build `app/skills/registry.py` + `router.py` as a
**thin metadata + gating layer** over the *existing* nodes (no framework). Start
read-only (registry + metrics fields), then let the media graph consult the
router for optional QA/enhancement passes. `ARCHITECTURE_PATTERN` from LangGraph
conditional routing; no dependency.
**Reason:** directly requested (spec §26–§29), real cost/latency benefit (don't
run every skill on a FAST job), and it's the structural hook that makes every
future skill upgrade measurable — but it's net-new surface, so it's a scoped
change, not an audit-pass edit.

---

## Applied in the continuation pass (2026-08-31 part 2) — agent core

| Agent | Improvement | Module | Was | Now |
|---|---|---|---|---|
| Research | first-pass **query decomposition** (3 sub-queries) + **merge/rank** (authority × relevance × freshness) + **domain-diversity** cap + **contradiction discovery** + **coverage score** | `app/agents/research.py` | RECOMMENDED (D60 did the fix-pass only) | **IMPLEMENTED** — `tests/test_agent_core_upgrades.py` |
| Fact Checker | **atomic claim extraction** + **check-worthiness** + **cross-source agreement count** + **temporal markers** + **confidence re-blend** + lone-source `VERIFIED→PARTIALLY_VERIFIED` | `app/agents/factcheck.py` | RECOMMENDED_FOR_LATER | **IMPLEMENTED** (no-op on mock data by design) |
| Hook Agent | **diversity filter** (min-keep floor) + **recent-hook similarity penalty** + **platform re-rank** + **factual-exaggeration guard** | `app/agents/hooks.py` | RECOMMENDED | **IMPLEMENTED** |
| Memory | **keyword-overlap fusion** boost on the existing rank (Mem0-style multi-signal) | `app/learning/memory.py::retrieve_memories` | RECOMMENDED | **IMPLEMENTED** (cap + DEPRECATED filter untouched) |
| Script / Strategy | beat-structured prompt + learned-memory injection | — | RECOMMENDED | **DEFER** (C) — prompt-only, low marginal value vs the existing natural-writing + memory injection |
| Error Recovery | unify 3 retry paths on `tenacity` | — | RECOMMENDED | **DEFER** (C) — all three already pass; pure-refactor regression risk |

## Applied this session (low-risk, evidence-backed) — see also `DECISIONS.md`

| Change | File | Type | Before → After | Reason | Risk | Test |
|---|---|---|---|---|---|---|
| Robust JSON extraction | `app/agents/common.py::parse_json` | ALGORITHM_PORT (instructor/outlines idea, no dep) | bare `json.loads` → strip ```` ```json ```` fences + balanced-brace extraction fallback | real LLM adapters wrap JSON in prose; mock unaffected (clean JSON parses first) | very low (no-op for valid JSON) | `tests/test_agents_common.py` (7 cases) + full regression |
| Research fix-pass query variety | `app/agents/nodes.py::_fix_query` | ALGORITHM_PORT (gpt-researcher / STORM query decomposition) | one fixed string `"{topic} 통계 최신 근거 사례"` → 3 rotating angle queries (stats / counter-evidence / primary-recent), 1 per pass | single-query research is the #1 audit gap; keeps call count + cost identical | low (mock search returns N for any query; fix loop test asserts counts, not query text) | `tests/test_agents_common.py::test_fix_query_*` + `test_pipeline_integration` + full regression |
| Full-jitter exponential backoff | `app/providers/retry.py::call_with_retry` | ALGORITHM_PORT (AWS "Exponential Backoff and Jitter") | `time.sleep(base_delay * i)` (linear, no jitter) → `_JITTER.uniform(0, base_delay * 2**(i-1))` via a **dedicated `random.Random()`** (not the global RNG — `experiment.py` falls back to it) | avoid synchronised retry storms against a real API | very low, after fixing a first cut that used the global RNG and caused 3 order-dependent `tests/ops` failures | `tests/test_retry.py` + full regression 172✓ (×2) |

## Rejected repositories

| Repo | Reason |
|---|---|
| CrewAI / AutoGen / MetaGPT / PydanticAI-graph / DBOS / Temporal / Restate / Inngest | second agent runtime — spec §10 ("no mixing runtimes") + §24 ("no architecture bloat"). LangGraph stays. |
| SearXNG, Firecrawl (core), Postiz | AGPL-3 → not linkable into a commercial service; fine only as a separately-run external service over HTTP |
| Mixpost | paid/commercial licence for the useful parts |
| Coqui XTTS-v2 | model licence is non-commercial |
| rany2/edge-tts (as prod default) | hits Microsoft's endpoint with no subscription — ToS risk (already dev-only in registry) |
| GPTZero / AI-detector / "humanizer-to-evade" repos | spec §15 — we build content quality, **not** detector evasion |
| Remotion (as the render engine) | source-available, employee-count-gated commercial licence — stays `OPTIONAL_TOOL`, FFmpeg remains the default (already decided Phase 1-B) |
| sentence-transformers (for the embedding swap) | pulls ~1GB torch for a gain that model2vec/fastembed deliver without it |

## License risk summary

- **MIT / Apache-2.0 / BSD / Unlicense / MPL-2.0**: all proposed dependencies and
  ports (`model2vec`, `fastembed`, `textstat`, `pybandits`, `ruptures`,
  `PyOD`, `statsmodels`, `whisperx`, `faster-whisper`, `Kokoro`, `Piper`,
  `Trafilatura`, `google-api-python-client`, `atproto`, `tenacity`) are
  commercial-safe. MPL-2.0 (`ADTK`) is file-level copyleft — fine as a dep.
- **AGPL-3**: SearXNG, Firecrawl core, Postiz, Grafana/Loki (Phase 5) — **never a
  linked dependency**; only ever a separately-deployed service reached over a
  network boundary.
- **Model-weight terms** (Real-ESRGAN, RIFE, rembg, some Whisper alignment
  models): code licence ≠ weight licence — verify weight provenance before any
  weight ships in a paid product (already a registry rule).
- **Non-commercial**: Coqui XTTS — excluded.
- **Source-available employee-gated**: Remotion — excluded as a hard dependency.

## Sources (web survey, 2026-08-31)

- Deep research / agents: [firecrawl best OSS agent frameworks](https://www.firecrawl.dev/blog/best-open-source-agent-frameworks), [Awesome-Deep-Research](https://github.com/DavidZWZ/Awesome-Deep-Research), [OpenResearcher (arXiv 2603.20278)](https://arxiv.org/pdf/2603.20278), [Cognitive Kernel-Pro (arXiv 2508.00414)](https://arxiv.org/pdf/2508.00414)
- Fact-checking: [Loki (arXiv 2410.01794)](https://arxiv.org/html/2410.01794v1), [OpenFactCheck (arXiv 2405.05583)](https://arxiv.org/html/2405.05583), [Hybrid KG+LLM fact-check (arXiv 2511.03217)](https://arxiv.org/html/2511.03217), [CLEF-2026 CheckThat!](https://arxiv.org/pdf/2602.09516)
- Memory: [Atlan — best agent memory frameworks 2026](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/), [Vectorize — 8 memory systems compared](https://vectorize.io/articles/best-ai-agent-memory-systems), [Stork.ai — Mem0 vs Zep vs Letta](https://www.stork.ai/blog/best-memory-layer-ai-agents-2026), [mem0 State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026), [MOSS (arXiv 2607.04391)](https://arxiv.org/pdf/2607.04391)
- Video editing: [ai-video-editor topic](https://github.com/topics/ai-video-editor?l=python), [OpenCut-AI](https://github.com/Ekaanth/OpenCut-AI), [openshorts](https://github.com/mutonby/openshorts), [opensource-clipping](https://github.com/NaufalRizqullah/opensource-clipping)
- Durable execution: [Spheron — Temporal/Inngest/Restate](https://www.spheron.network/blog/ai-agent-workflow-orchestration-temporal-inngest-restate-gpu-cloud/), [AppScale — Temporal + LangGraph](https://appscale.blog/en/blog/durable-execution-llm-agents-temporal-langgraph-checkpointing-2026), [DBOS vs Temporal](https://tiarebalbi.com/en/blog/dbos-vs-temporal-postgres-durable-execution), [Reactify — durable AI agents 2026](https://www.reactify-solutions.com/articles/durable-ai-agents-2026)
- Time-series: [awesome-TS-anomaly-detection](https://github.com/rob-med/awesome-TS-anomaly-detection), [PyData Bench — anomaly detection 2026](https://pythondatabench.com/article/anomaly-detection-time-series-python-isolation-forest-lof-stl), [anomaly-detection topic](https://github.com/topics/anomaly-detection?l=python)
- STT / alignment: [Gladia — Whisper alternatives 2026](https://www.gladia.io/blog/best-whisper-alternatives-2026), [Modal — Whisper variants](https://modal.com/blog/choosing-whisper-variants), [easytranscriber](https://kb-labb.github.io/posts/2026-02-26-easytranscriber/), [Whisper internal aligner (arXiv 2509.09987)](https://arxiv.org/html/2509.09987v1)
- LangGraph: [LangGraph in 2026 (DEV)](https://dev.to/ottoaria/langgraph-in-2026-build-multi-agent-ai-systems-that-actually-work-3h5), [Supervisor vs Swarm (Focused)](https://focused.io/lab/multi-agent-orchestration-in-langgraph-supervisor-vs-swarm-tradeoffs-and-architecture), [Supervisor + Deep Agents guide](https://www.buildmvpfast.com/blog/langgraph-supervisor-deep-agents-multi-agent-patterns-2026)
- Thumbnail / saliency: [ThumbCraft](https://github.com/AbhishekNavgan95/ThumbCraft), [thumbnail-generator topic](https://github.com/topics/thumbnail-generator), [image-saliency topic](https://github.com/topics/image-saliency), [thumbor](https://github.com/thumbor/thumbor)
- Publishing: [SocialChamp — social media APIs 2026](https://www.socialchamp.com/blog/best-social-media-apis/), [Phyllo — social media API guide](https://www.getphyllo.com/post/social-media-api-guide-on-top-apis-for-developers), [ayrshare/social-media-api](https://github.com/ayrshare/social-media-api), [Mallary — OSS social media API tools](https://mallary.ai/blog/social-media-api-open-source)
- RAG: [Fastio — KG tools for RAG 2026](https://fast.io/resources/best-knowledge-graph-tools-rag/), [ArcadeDB — OSS GraphRAG compared](https://arcadedb.com/blog/open-source-knowledge-graph-graphrag-databases-compared/), [LightRAG / MiniRAG / KET-RAG survey (arXiv 2601.05254)](https://arxiv.org/pdf/2601.05254)
- Bandits: [PlaytikaOSS/pybandits](https://github.com/PlaytikaOSS/pybandits), [thompson-sampling topic](https://github.com/topics/thompson-sampling?l=python)
