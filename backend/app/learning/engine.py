from __future__ import annotations

import statistics
from collections import defaultdict

from app.analytics.embedding import cosine
from app.config import get_settings
from app.db.models import ContentFeature, PerformanceScore
from app.learning.memory import upsert_memory

# Learning Agent principles (enforced structurally, not just in a prompt):
#   correlation != causation · one viral post is not evidence ·
#   compare similar content · every recommendation carries evidence + n + confidence.

_MEM_FOR_DIM = {
    "hook_type": "HOOK", "cta_type": "SCRIPT", "duration_bucket": "SCRIPT",
    "publish_hour_bucket": "TIMING", "ai_video_bucket": "VISUAL",
    "scene_var_bucket": "NATURALNESS", "subtitle_style": "SUBTITLE",
    "ai_slop_bucket": "NATURALNESS",
}


def _duration_bucket(v):
    if v is None:
        return None
    if v < 30:
        return "<30s"
    if v < 45:
        return "30-45s"
    if v < 60:
        return "45-60s"
    if v < 85:
        return "60-85s"
    return "85s+"


def _hour_bucket(h):
    if h is None:
        return None
    return ["night", "morning", "afternoon", "evening"][min(3, h // 6)]


def _ai_video_bucket(v):
    if v is None:
        return None
    return "low" if v <= 0.15 else "mid" if v <= 0.35 else "high"


def _scene_var_bucket(v):
    if v is None:
        return None
    return "flat" if v < 0.5 else "moderate" if v < 1.5 else "bursty"


def _slop_bucket(v):
    if v is None:
        return None
    return "clean" if v < 15 else "ok" if v < 25 else "sloppy"


_DIMS = {
    "hook_type": lambda cf: cf.hook_type,
    "cta_type": lambda cf: cf.cta_type,
    "duration_bucket": lambda cf: _duration_bucket(cf.video_duration),
    "publish_hour_bucket": lambda cf: _hour_bucket(cf.publish_hour),
    "ai_video_bucket": lambda cf: _ai_video_bucket(cf.ai_video_ratio),
    "scene_var_bucket": lambda cf: _scene_var_bucket(cf.scene_duration_variance),
    "subtitle_style": lambda cf: cf.subtitle_style,
    "ai_slop_bucket": lambda cf: _slop_bucket(cf.ai_slop_score),
}


def _records(session, objective: str):
    feats = {f.content_id: f for f in session.query(ContentFeature).all()}
    out = []
    for ps in session.query(PerformanceScore).filter(PerformanceScore.objective == objective).all():
        cf = feats.get(ps.content_id)
        if cf is None:
            continue
        out.append({"ps": ps, "cf": cf, "score": ps.score,
                    "excluded": ps.is_outlier or ps.has_anomaly,
                    "platform": ps.platform, "content_type": ps.content_type})
    return out


def _consistent(scores: list[float], overall_med: float, lift: float) -> bool:
    """False-learning guard: a pattern must not be driven by a single data point.

    - n < 6: drop the single best/worst; the advantage must survive (>=40%).
    - n >= 6: a clear majority of the group must individually sit on the same
      side of the overall median (a real, repeated pattern, not one item).
    """
    n = len(scores)
    if n < 3:
        return False
    if n >= 6:
        if lift > 0:
            frac_above = sum(1 for s in scores if s >= overall_med) / n
            return frac_above >= 0.6
        frac_below = sum(1 for s in scores if s <= overall_med) / n
        return frac_below >= 0.6
    trimmed = sorted(scores)[:-1] if lift > 0 else sorted(scores)[1:]
    tmed = statistics.median(trimmed)
    tlift = (tmed / overall_med - 1.0) if overall_med else 0.0
    return tlift >= lift * 0.4 if lift > 0 else tlift <= lift * 0.4


def _confidence(n: int, lift: float, consistent: bool) -> float:
    base = 0.25 + 0.04 * min(n, 15) + min(0.3, abs(lift) * 1.5)
    if not consistent:
        base *= 0.5
    return round(min(0.95, base), 3)


def analyze(session, objective: str | None = None) -> dict:
    s = get_settings()
    objective = (objective or s.default_objective).upper()
    records = _records(session, objective)
    summary = {"objective": objective, "records": len(records), "patterns": 0,
               "topic_fatigue": 0, "diversity_warnings": 0, "prompt_perf": 0}
    if len(records) < s.memory_min_moderate_sample:
        return summary

    groups: dict[tuple[str, str], list] = defaultdict(list)
    for r in records:
        groups[(r["platform"], r["content_type"])].append(r)

    for (platform, ctype), recs in groups.items():
        usable = [r for r in recs if not r["excluded"]]
        if len(usable) < s.memory_min_moderate_sample:
            continue
        overall_med = statistics.median([r["score"] for r in usable]) or 1.0

        for dim_name, dim_fn in _DIMS.items():
            by_val: dict[str, list] = defaultdict(list)
            for r in usable:
                v = dim_fn(r["cf"])
                if v is not None:
                    by_val[str(v)].append(r)
            for val, rs in by_val.items():
                if len(rs) < max(3, s.memory_min_moderate_sample // 2):
                    continue
                scores = [r["score"] for r in rs]
                med = statistics.median(scores)
                lift = round(med / overall_med - 1.0, 3)
                if abs(lift) < 0.08:
                    continue
                consistent = _consistent(scores, overall_med, lift)
                conf = _confidence(len(rs), lift, consistent)
                direction = "우수" if lift > 0 else "저조"
                upsert_memory(
                    session, memory_type=_MEM_FOR_DIM.get(dim_name, "PLATFORM"),
                    platform=platform, content_type=ctype, dimension=f"{dim_name}={val}",
                    topic_cluster=None,
                    statement=(f"[{platform}/{ctype}] {dim_name}={val} 콘텐츠가 채널 baseline 대비 "
                               f"performance score {lift:+.0%} {direction} (상관관계, 인과 아님)"),
                    recommendation={"dimension": dim_name, "value": val, "lift": lift,
                                    "objective": objective},
                    confidence=conf, sample_size=len(rs),
                    evidence_ids=[r["cf"].content_id for r in rs[:20]],
                    consistent=consistent,
                )
                summary["patterns"] += 1

    summary["topic_fatigue"] = _topic_fatigue(session, records)
    summary["diversity_warnings"] = _creative_diversity(session)
    summary["prompt_perf"] = _prompt_version_perf(session, records, objective)
    return summary


def _topic_fatigue(session, records) -> int:
    by_cluster: dict[str, list] = defaultdict(list)
    for r in records:
        cf = r["cf"]
        if cf.topic_cluster:
            by_cluster[cf.topic_cluster].append((cf.publish_hour or 0, r["score"], cf))
    n = 0
    for cluster, items in by_cluster.items():
        if len(items) < 4:
            continue
        items.sort(key=lambda x: x[2].created_at)
        seq = [sc for _h, sc, _cf in items]
        # declining tail: each of the last 3 <= previous
        if all(seq[i] <= seq[i - 1] + 1e-6 for i in range(len(seq) - 3, len(seq))) and seq[-1] < seq[0] * 0.8:
            upsert_memory(session, memory_type="TOPIC", topic_cluster=cluster,
                          dimension="fatigue",
                          statement=f"Topic cluster '{cluster}' 성과가 최근 편에서 지속 하락 → TOPIC_FATIGUE",
                          recommendation={"action": "TOPIC_FATIGUE", "cluster": cluster},
                          confidence=min(0.8, 0.4 + 0.05 * len(items)), sample_size=len(items),
                          evidence_ids=[cf.content_id for _h, _s, cf in items], consistent=True)
            n += 1
    return n


def _creative_diversity(session) -> int:
    feats = (session.query(ContentFeature).order_by(ContentFeature.created_at.desc()).limit(8).all())
    if len(feats) < 4:
        return 0
    sims = []
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            a, b = feats[i], feats[j]
            s = 0.0
            s += 0.3 if a.hook_type == b.hook_type else 0.0
            s += 0.2 if a.cta_type == b.cta_type else 0.0
            s += 0.2 * cosine(a.topic_embedding or [], b.topic_embedding or [])
            s += 0.15 if abs((a.script_length or 0) - (b.script_length or 0)) < 12 else 0.0
            s += 0.15 if abs((a.scene_count or 0) - (b.scene_count or 0)) <= 1 else 0.0
            sims.append(s)
    if sims and statistics.fmean(sims) > 0.75:
        upsert_memory(session, memory_type="FAILURE", dimension="diversity",
                      statement="최근 콘텐츠들이 hook/CTA/구조 측면에서 지나치게 유사 → VARIATION_REQUIRED",
                      recommendation={"action": "VARIATION_REQUIRED"},
                      confidence=0.7, sample_size=len(feats),
                      evidence_ids=[f.content_id for f in feats], consistent=True)
        return 1
    return 0


def _prompt_version_perf(session, records, objective: str) -> int:
    by_ver: dict[tuple[str, str, str], list] = defaultdict(list)
    for r in records:
        cf = r["cf"]
        for slot, ver in (cf.prompt_versions or {}).items():
            by_ver[(r["platform"], slot, ver)].append(r["score"])
    n = 0
    # compare versions within the same (platform, slot)
    slots: dict[tuple[str, str], dict[str, list]] = defaultdict(dict)
    for (platform, slot, ver), scores in by_ver.items():
        slots[(platform, slot)][ver] = scores
    for (platform, slot), vers in slots.items():
        if len(vers) < 2:
            continue
        meds = {v: statistics.median(s) for v, s in vers.items() if len(s) >= 4}
        if len(meds) < 2:
            continue
        best = max(meds, key=meds.get)
        n_best = len(vers[best])
        upsert_memory(session, memory_type="SCRIPT", platform=platform, dimension=f"prompt:{slot}",
                      statement=(f"[{platform}] prompt {slot} 버전별 median score: "
                                 + ", ".join(f"{v}={m:.0f}(n={len(vers[v])})" for v, m in meds.items())
                                 + f" → {best} 우선 고려 (Topic/Platform 편차 주의)"),
                      recommendation={"slot": slot, "prefer": best, "medians": meds,
                                      "objective": objective},
                      confidence=min(0.75, 0.35 + 0.03 * n_best), sample_size=n_best,
                      evidence_ids=[], consistent=True)
        n += 1
    return n
