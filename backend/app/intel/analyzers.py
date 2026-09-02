"""Reference analyzers — deterministic feature extraction.

FactExtractor / KnowledgeExtractor  — claims, stats, quotes, entities, concepts.
StyleAnalyzer                       — WritingProfile (features, never copied text).
VideoReferenceAnalyzer             — VideoObservation + Hook/Story/Editing/B-roll/
                                     Subtitle/Voice/Audio/Graphics/Thumbnail/
                                     Retention profiles from PROVIDED structure;
                                     any field that cannot be measured is UNKNOWN.
GitHubReferenceAnalyzer            — repo/file technical summary.
CompetitorAnalyzer                — positioning signal from a competitor reference.

No fabricated numbers. LLM is optional; on mock it uses regex/statistics only.
"""
from __future__ import annotations

import re
import statistics

UNKNOWN = "UNKNOWN"

_NUM = re.compile(r"-?\d[\d,]*\.?\d*\s*(?:%|퍼센트|배|억|만|천|원|달러|명|건|위|K|M|B)?")
_STAT = re.compile(r"\d[\d,]*\.?\d*\s*(?:%|퍼센트|배|percent)")
_QUOTE = re.compile(r"[\"“”']([^\"“”']{8,240})[\"“”']")
_DATE = re.compile(r"\b(20\d{2}|19\d{2})[-./년]\s?\d{1,2}[-./월]?\s?\d{0,2}\b|\b20\d{2}\b")
_ENTITY = re.compile(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,3})\b")
_SENT = re.compile(r"(?<=[.!?…])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if len(s.strip()) > 12]


# --------------------------------------------------------------------- #
#  Fact / Knowledge
# --------------------------------------------------------------------- #

def extract_facts(text: str, *, source_url: str = "") -> dict:
    sents = _sentences(text)
    claims, stats, quotes = [], [], []
    for s in sents:
        if _STAT.search(s):
            stats.append(s[:280])
        if _QUOTE.search(s):
            quotes.append(_QUOTE.search(s).group(1))
        if re.search(r"(is|are|was|were|according to|found that|shows|reported|이다|했다|밝혔|나타났)", s, re.I) \
                and not re.search(r"(I think|in my opinion|maybe|아마|같다는 느낌)", s, re.I):
            claims.append(s[:280])
    dates = sorted({m.group(0).strip() for m in _DATE.finditer(text or "")})[:20]
    entities = _rank_entities(text)
    return {
        "claims": claims[:40],
        "statistics": stats[:30],
        "quotes": quotes[:20],
        "dates": dates,
        "entities": entities,
        "examples": [s[:240] for s in sents if re.search(r"(for example|e\.g\.|예를 들|가령|사례)", s, re.I)][:15],
        "counterarguments": [s[:240] for s in sents if re.search(r"(however|but critics|on the other hand|반론|비판|하지만)", s, re.I)][:10],
        "source_url": source_url,
        # a URL is NEVER auto-VERIFIED — the Fact Checker decides
        "verification_status": "UNVERIFIED_EXTERNAL",
    }


def _rank_entities(text: str) -> list[str]:
    counts: dict[str, int] = {}
    for m in _ENTITY.finditer(text or ""):
        e = m.group(1)
        if len(e) < 3 or e.lower() in _STOP_ENT:
            continue
        counts[e] = counts.get(e, 0) + 1
    return [e for e, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:20]]


_STOP_ENT = {"the", "this", "that", "these", "there", "and", "for", "with"}


def extract_knowledge(text: str) -> dict:
    sents = _sentences(text)
    defs = [s[:280] for s in sents if re.search(r"( is defined as | refers to | means that |란 |이란 |라고 한다)", s, re.I)]
    rel = [s[:240] for s in sents if re.search(r"(because|therefore|as a result|leads to|causes|때문에|따라서|결과적으로)", s, re.I)]
    kw = _rank_entities(text)
    return {
        "concepts": kw[:15],
        "definitions": defs[:15],
        "relationships": rel[:15],
        "main_points": [s[:240] for s in sents[:8]],
        "examples": [s[:240] for s in sents if re.search(r"(예를 들|for example|사례)", s, re.I)][:10],
        "keywords": kw,
        "questions": [s[:200] for s in sents if s.rstrip().endswith(("?", "?"))][:10],
        "visual_opportunities": _visual_opportunities(sents),
    }


def _visual_opportunities(sents: list[str]) -> list[dict]:
    out = []
    for s in sents:
        if _STAT.search(s):
            out.append({"narration": s[:160], "suggested_visual": "data_visualization"})
        elif re.search(r"(process|step|how to|절차|단계|방법)", s, re.I):
            out.append({"narration": s[:160], "suggested_visual": "process_footage"})
        elif re.search(r"(feel|fear|hope|worry|감정|두려움|불안|희망)", s, re.I):
            out.append({"narration": s[:160], "suggested_visual": "contextual_visual"})
    return out[:15]


# --------------------------------------------------------------------- #
#  Writing style (features only — never store long verbatim text)
# --------------------------------------------------------------------- #

def writing_profile(text: str) -> dict:
    sents = _sentences(text)
    if not sents:
        return {"status": "EMPTY"}
    lens = [len(s.split()) for s in sents]
    paras = [p for p in re.split(r"\n{1,}", text or "") if p.strip()]
    q = sum(1 for s in sents if s.rstrip().endswith(("?", "?")))
    first = sents[0].lower()
    opening = (
        "QUESTION" if first.rstrip().endswith(("?", "?")) else
        "STAT" if _STAT.search(sents[0]) else
        "STORY" if re.search(r"(when i|last year|한때|어느 날|예전에)", first) else
        "DIRECT_CLAIM" if re.search(r"(is|are|will|해야|이다|한다)", first) else "CONTEXT"
    )
    return {
        "opening_type": opening,
        "hook_structure": "PROMISE" if re.search(r"(you will|이 글에서|알려드리|정리)", " ".join(sents[:2])) else "CURIOSITY",
        "sentence_length_distribution": {
            "mean": round(statistics.mean(lens), 1),
            "stdev": round(statistics.pstdev(lens), 1) if len(lens) > 1 else 0.0,
            "short_ratio": round(sum(1 for x in lens if x <= 8) / len(lens), 2),
            "long_ratio": round(sum(1 for x in lens if x >= 22) / len(lens), 2),
        },
        "paragraph_rhythm": round(statistics.mean([len(_sentences(p)) for p in paras]), 1) if paras else 0.0,
        "vocabulary_level": _vocab_level(text),
        "tone": _tone(text),
        "directness": round(sum(1 for s in sents if re.search(r"\b(you|your|당신|여러분)\b", s, re.I)) / len(sents), 2),
        "humor": bool(re.search(r"(lol|😂|ㅋㅋ|농담|joke)", text, re.I)),
        "argument_structure": "CLAIM_EVIDENCE" if _STAT.search(text or "") else "NARRATIVE",
        "story_structure": "PROBLEM_SOLUTION" if re.search(r"(problem|solution|문제|해결)", text, re.I) else UNKNOWN,
        "information_density": round(len(_NUM.findall(text or "")) / max(1, len(sents)), 2),
        "example_usage": round(sum(1 for s in sents if re.search(r"(예를 들|for example|사례)", s, re.I)) / len(sents), 2),
        "analogy_usage": round(sum(1 for s in sents if re.search(r"(like a|as if|마치|처럼)", s, re.I)) / len(sents), 2),
        "question_frequency": round(q / len(sents), 2),
        "transition_pattern": "EXPLICIT" if re.search(r"(first|next|finally|먼저|다음|마지막)", text, re.I) else "IMPLICIT",
        "cta_style": "DIRECT" if re.search(r"(subscribe|follow|click|구독|팔로우|눌러)", text, re.I) else "SOFT",
        "conclusion_style": "SUMMARY" if re.search(r"(in conclusion|to sum up|정리하면|결론)", text, re.I) else UNKNOWN,
    }


def _vocab_level(text: str) -> str:
    words = re.findall(r"[A-Za-z가-힣]+", text or "")
    if not words:
        return UNKNOWN
    avg = statistics.mean(len(w) for w in words)
    return "SIMPLE" if avg < 4.5 else "MODERATE" if avg < 6 else "TECHNICAL"


def _tone(text: str) -> str:
    t = (text or "").lower()
    if re.search(r"(warning|danger|위험|경고|조심)", t):
        return "URGENT"
    if re.search(r"(amazing|incredible|대박|놀라운|충격)", t):
        return "HYPE"
    if re.search(r"(study|research|data|분석|연구|데이터)", t):
        return "ANALYTICAL"
    return "NEUTRAL"


# --------------------------------------------------------------------- #
#  Video deep analysis (from provided structure only)
# --------------------------------------------------------------------- #

_VIDEO_FIELDS = [
    "duration", "hook_duration", "hook_type", "first_frame_strategy", "story_arc",
    "story_beats", "scene_count", "scene_duration_mean", "scene_duration_variance",
    "shot_count", "shot_duration_mean", "shot_duration_variance", "shot_scale_distribution",
    "camera_motion", "visual_refresh_rate", "broll_ratio", "graphics_ratio",
    "text_card_ratio", "caption_density", "caption_style", "highlight_frequency",
    "voice_speed", "voice_energy", "pause_pattern", "music_energy", "sfx_density",
    "transition_density", "information_density", "cta_position", "opening_pattern",
    "ending_pattern", "visual_language", "editing_language",
]


def video_observation(profile: dict | None) -> dict:
    """profile: whatever structure the caller could obtain (YouTube API fields, a
    user-supplied edit list, scene timings). Missing/unmeasurable -> UNKNOWN.
    Derived stats are only computed when the raw inputs are present."""
    p = dict(profile or {})
    obs: dict = {}
    unknown: list[str] = []

    scenes = p.get("scene_durations") or []
    shots = p.get("shot_durations") or []
    if scenes:
        p.setdefault("scene_count", len(scenes))
        p.setdefault("scene_duration_mean", round(statistics.mean(scenes), 2))
        p.setdefault("scene_duration_variance", round(statistics.pvariance(scenes), 3) if len(scenes) > 1 else 0.0)
        p.setdefault("duration", round(sum(scenes), 2))
    if shots:
        p.setdefault("shot_count", len(shots))
        p.setdefault("shot_duration_mean", round(statistics.mean(shots), 2))
        p.setdefault("shot_duration_variance", round(statistics.pvariance(shots), 3) if len(shots) > 1 else 0.0)
    if p.get("duration") and p.get("hook_end"):
        p.setdefault("hook_duration", round(float(p["hook_end"]), 2))

    for f in _VIDEO_FIELDS:
        v = p.get(f)
        if v is None or v == "":
            obs[f] = UNKNOWN
            unknown.append(f)
        else:
            obs[f] = v
    obs["_unknown_fields"] = unknown
    obs["_measured_fields"] = [f for f in _VIDEO_FIELDS if f not in unknown]
    obs["_coverage"] = round(len(obs["_measured_fields"]) / len(_VIDEO_FIELDS), 2)
    return obs


def video_subprofiles(obs: dict) -> dict:
    """Break a VideoObservation into the learning sub-profiles (§N). Each keeps
    only fields that were measured; the rest stay UNKNOWN."""
    def g(*keys):
        return {k: obs.get(k, UNKNOWN) for k in keys}

    return {
        "HOOK_PATTERN": {
            **g("hook_duration", "hook_type", "first_frame_strategy", "opening_pattern"),
            "abstracted": _abstract_hook(obs),
        },
        "STORY_PROFILE": {**g("story_arc", "story_beats"),
                          "beats_used": _story_beats(obs.get("story_beats"))},
        "EDITING_PROFILE": g("scene_count", "scene_duration_mean", "scene_duration_variance",
                             "shot_count", "shot_duration_mean", "shot_duration_variance",
                             "visual_refresh_rate", "transition_density", "camera_motion",
                             "editing_language"),
        "BROLL_PROFILE": g("broll_ratio", "graphics_ratio", "text_card_ratio", "visual_language"),
        "SUBTITLE_PROFILE": g("caption_density", "caption_style", "highlight_frequency"),
        "VOICE_PROFILE": g("voice_speed", "voice_energy", "pause_pattern"),
        "AUDIO_PROFILE": g("music_energy", "sfx_density"),
        "GRAPHICS_PROFILE": g("graphics_ratio", "text_card_ratio"),
        "THUMBNAIL_PROFILE": g("thumbnail_style", "thumbnail_text", "thumbnail_face"),
        "RETENTION_PATTERN": {**g("cta_position", "information_density", "ending_pattern"),
                              "note": "retention curve requires platform analytics access — not derivable from the reference alone"},
    }


def _abstract_hook(obs: dict) -> list[str]:
    tags = []
    ht = str(obs.get("hook_type", "")).upper()
    for key in ("QUESTION", "CURIOSITY", "WARNING", "PROMISE", "PROOF", "TENSION", "PATTERN_INTERRUPT"):
        if key in ht:
            tags.append(key)
    hd = obs.get("hook_duration")
    if isinstance(hd, (int, float)) and hd <= 3.5:
        tags.append("FAST_HOOK")
    return tags or [UNKNOWN]


_STORY_BEAT_VOCAB = ("HOOK", "SETUP", "QUESTION", "TENSION", "DISCOVERY", "PROOF",
                     "CONTRAST", "SURPRISE", "PAYOFF", "SUMMARY", "CTA")


def _story_beats(raw) -> list[str]:
    if not raw:
        return [UNKNOWN]
    seq = raw if isinstance(raw, list) else re.split(r"[,\s>]+", str(raw))
    return [b.upper() for b in seq if b.upper() in _STORY_BEAT_VOCAB] or [UNKNOWN]


BROLL_DECISION_RULES = {
    "STATISTIC": ["chart", "document"],
    "CLAIM": ["proof_visual"],
    "EMOTION": ["contextual_visual"],
    "PROCESS": ["process_footage"],
    "ABSTRACT_CONCEPT": ["motion_graphic", "metaphorical_broll"],
}


def broll_decision_pattern(narration_visual_pairs: list[dict]) -> dict:
    """narration_visual_pairs: [{narration_type, visual_type}] observed in the
    reference. Returns the learned mapping + support counts."""
    obs: dict[str, dict[str, int]] = {}
    for pair in narration_visual_pairs or []:
        nt = str(pair.get("narration_type", "")).upper()
        vt = str(pair.get("visual_type", "")).lower()
        if not nt or not vt:
            continue
        obs.setdefault(nt, {})
        obs[nt][vt] = obs[nt].get(vt, 0) + 1
    learned = {nt: max(vs, key=vs.get) for nt, vs in obs.items() if vs}
    return {"observed": obs, "learned_mapping": learned or UNKNOWN,
            "reference_rules": BROLL_DECISION_RULES}


# --------------------------------------------------------------------- #
#  GitHub / Competitor
# --------------------------------------------------------------------- #

def github_analysis(text: str, *, url: str = "") -> dict:
    langs = sorted(set(re.findall(r"\b(Python|TypeScript|JavaScript|Go|Rust|Java|C\+\+|C#|Ruby|Swift|Kotlin)\b", text or "")))
    return {
        "url": url,
        "languages": langs,
        "topics": _rank_entities(text)[:12],
        "has_license": bool(re.search(r"\bLICENSE\b|MIT|Apache-2\.0|GPL", text or "")),
        "readme_summary": " ".join(_sentences(text)[:5])[:600],
        "techniques": [s[:200] for s in _sentences(text)
                       if re.search(r"(algorithm|approach|technique|architecture|pipeline|모델|기법)", s, re.I)][:12],
        "note": "code licence is NOT a content licence; using code ≠ right to reuse repo media",
    }


def competitor_analysis(doc: dict) -> dict:
    text = doc.get("main_text", "")
    return {
        "publisher": doc.get("publisher", "") or UNKNOWN,
        "topic_focus": _rank_entities(text)[:10],
        "cadence_hint": UNKNOWN,   # not derivable from one page
        "positioning": _tone(text),
        "hook_samples_abstract": [writing_profile(text).get("opening_type", UNKNOWN)],
        "note": "single-page competitor snapshot; not a channel-level audit",
    }
