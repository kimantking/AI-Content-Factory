"""Originality Engine V2 (§15-§30) — deterministic multi-signal similarity.

No single metric blocks. Signals: exact hash, normalised hash, token Jaccard,
n-gram overlap, cheap embedding cosine (script/hook/title), image pHash, a
video-fingerprint *abstraction* (duration + scene-count + scene-duration profile
+ per-scene visual-type sequence + audio-energy profile — robust to re-encode /
recolour / subtitle change), plus transformation-score and reused-content-risk.
Real heavy CV fingerprinting is an optional adapter.
"""
from __future__ import annotations

import hashlib
import re
import statistics

from sqlalchemy.orm import Session

from app.analytics.embedding import cosine, embed
from app.config import get_settings
from app.db.models_gov import ContentFingerprint, SimilarityResult
from app.governance import phash as _phash

_WORD = re.compile(r"[\w가-힣]+")
_STOP = {"그리고", "그러나", "하지만", "the", "a", "of", "및", "수", "것", "이", "가", "은", "는", "에", "를", "을"}


def _norm(text: str) -> str:
    toks = [t for t in _WORD.findall((text or "").lower()) if t not in _STOP]
    return " ".join(toks)


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()


def _tokens(text: str) -> list[str]:
    return [t for t in _WORD.findall((text or "").lower()) if t not in _STOP and len(t) > 1]


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _ngrams(tokens: list[str], n: int = 3) -> set[tuple]:
    return {tuple(tokens[i:i + n]) for i in range(max(0, len(tokens) - n + 1))}


# ---- fingerprint building ------------------------------------------- #

def build_text_fingerprint(kind: str, text: str) -> dict:
    toks = _tokens(text)
    return {
        "kind": kind,
        "exact_hash": _hash(text),
        "norm_hash": _hash(_norm(text)),
        "sim_vector": embed(text),
        "tokens": toks[:400],
        "profile": {"n_tokens": len(toks), "n_sentences": len(re.split(r"[.!?…\n]+", text or ""))},
    }


def build_video_fingerprint(scenes: list[dict], *, duration: float | None = None,
                            thumbnail_phash: str = "") -> dict:
    durs = [round(float(s.get("estimated_duration", s.get("duration", 0)) or 0), 1) for s in scenes]
    vtypes = [str(s.get("visual_type", "")) for s in scenes]
    motions = [str(s.get("camera_motion", "")) for s in scenes]
    energy = [str(s.get("music_energy", "")) for s in scenes]
    total = round(duration if duration is not None else sum(durs), 1)
    profile = {
        "total_duration": total,
        "scene_count": len(scenes),
        "scene_durations": durs,
        "visual_type_seq": vtypes,
        "motion_seq": motions,
        "energy_seq": energy,
        "dur_variance": round(statistics.pstdev(durs), 2) if len(durs) > 1 else 0.0,
    }
    seq_hash = _hash("|".join(f"{v}:{m}" for v, m in zip(vtypes, motions)))
    return {
        "kind": "FINAL_VIDEO",
        "exact_hash": "",
        "norm_hash": seq_hash,           # scene/motion sequence fingerprint
        "phash": thumbnail_phash,
        "sim_vector": [],
        "tokens": [],
        "profile": profile,
    }


def video_fp_similarity(a: dict, b: dict) -> float:
    """0..1 similarity between two video-fingerprint profiles — robust to
    re-encode / crop / subtitle-colour / music-swap because it compares structure."""
    pa, pb = a.get("profile", {}), b.get("profile", {})
    if not pa or not pb:
        return 0.0
    sims = []
    # duration
    da, dbb = pa.get("total_duration", 0), pb.get("total_duration", 0)
    if da and dbb:
        sims.append(1.0 - min(1.0, abs(da - dbb) / max(da, dbb)))
    # scene count
    sa, sb = pa.get("scene_count", 0), pb.get("scene_count", 0)
    if sa and sb:
        sims.append(1.0 - min(1.0, abs(sa - sb) / max(sa, sb)))
    # visual-type sequence (order-sensitive LCS ratio)
    va, vb = pa.get("visual_type_seq", []), pb.get("visual_type_seq", [])
    if va and vb:
        sims.append(_seq_ratio(va, vb))
    # scene-duration profile correlation-ish
    ra, rb = pa.get("scene_durations", []), pb.get("scene_durations", [])
    if len(ra) == len(rb) and ra:
        diff = sum(abs(x - y) for x, y in zip(ra, rb)) / (sum(ra) or 1)
        sims.append(max(0.0, 1.0 - diff))
    # exact scene/motion sequence hash
    if a.get("norm_hash") and a["norm_hash"] == b.get("norm_hash"):
        sims.append(1.0)
    return round(sum(sims) / len(sims), 4) if sims else 0.0


def _seq_ratio(a: list, b: list) -> float:
    # normalised longest-common-subsequence length
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            dp[i + 1][j + 1] = dp[i][j] + 1 if a[i] == b[j] else max(dp[i][j + 1], dp[i + 1][j])
    return dp[m][n] / max(m, n) if max(m, n) else 0.0


# ---- text similarity (multi-metric) ------------------------------- #

def text_similarity(t1: str, t2: str) -> dict:
    if not t1 or not t2:
        return {"exact": 0.0, "norm": 0.0, "jaccard": 0.0, "ngram": 0.0, "embed": 0.0, "combined": 0.0}
    exact = 1.0 if _hash(t1) == _hash(t2) else 0.0
    norm = 1.0 if _hash(_norm(t1)) == _hash(_norm(t2)) else 0.0
    tok1, tok2 = _tokens(t1), _tokens(t2)
    jac = _jaccard(set(tok1), set(tok2))
    ng = _jaccard(_ngrams(tok1), _ngrams(tok2))
    emb = max(0.0, cosine(embed(t1), embed(t2)))
    # combined: embedding + jaccard dominate; exact/norm are strong confirmers
    combined = max(exact, norm, round(0.45 * emb + 0.30 * jac + 0.25 * ng, 4))
    return {"exact": exact, "norm": norm, "jaccard": round(jac, 4), "ngram": round(ng, 4),
            "embed": round(emb, 4), "combined": combined}


# ---- transformation & reuse (§26-§28) --------------------------- #

_TRANSFORM_FEATURES = {
    "original_narration": ("직접 설명", "내레이션", "해설", "정리하면", "분석하면"),
    "new_analysis": ("분석", "해석", "의미는", "왜냐하면", "시사점"),
    "data_visualization": ("차트", "그래프", "데이터 시각화"),
    "commentary": ("제 생각", "코멘트", "짚어보면", "관점"),
    "contextualization": ("배경", "맥락", "역사", "이전에는"),
}


def transformation_score(*, script_body: str, scenes: list[dict], visual_types: list[str]) -> dict:
    body = script_body or ""
    feats: dict[str, bool] = {}
    for name, cues in _TRANSFORM_FEATURES.items():
        feats[name] = any(c in body for c in cues)
    feats["original_graphics"] = any(v in ("CHART", "TEXT_CARD", "MOTION_GRAPHIC") for v in visual_types)
    feats["visual_restructuring"] = len(set(visual_types)) >= 3
    feats["editing_structure"] = len(scenes) >= 4
    score = round(sum(1 for v in feats.values() if v) / len(feats), 3)
    return {"score": score, "features": feats}


def reused_content_risk(*, visual_types: list[str], external_footage_ratio: float,
                        transformation: float) -> dict:
    n = max(1, len(visual_types))
    stock = sum(1 for v in visual_types if v == "STOCK_VIDEO") / n
    ai = sum(1 for v in visual_types if v in ("AI_IMAGE", "AI_VIDEO")) / n
    generic_stock_ratio = stock
    compilation_ratio = external_footage_ratio
    risk = 0.0
    reasons = []
    if compilation_ratio > 0.6:
        risk += 0.4
        reasons.append(f"{compilation_ratio:.0%} external/reused footage")
    if generic_stock_ratio > 0.7:
        risk += 0.25
        reasons.append(f"{generic_stock_ratio:.0%} generic stock")
    if transformation < 0.35:
        risk += 0.35
        reasons.append("low transformation (little original narration/analysis/graphics)")
    risk = round(min(1.0, risk), 3)
    verdict = "BLOCK" if risk >= 0.8 else "HUMAN_REVIEW" if risk >= 0.55 else "OK"
    return {"risk": risk, "verdict": verdict, "stock_ratio": round(stock, 3),
            "ai_ratio": round(ai, 3), "compilation_ratio": round(compilation_ratio, 3),
            "reasons": reasons}


# ---- top-level check ------------------------------------------- #

def persist_fingerprints(db: Session, *, campaign_id: str, content_id: str | None,
                         workspace_id: str | None, brand_id: str | None, channel_id: str | None,
                         fps: list[dict]) -> None:
    for fp in fps:
        db.add(ContentFingerprint(
            workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
            campaign_id=campaign_id, content_id=content_id, kind=fp["kind"],
            exact_hash=fp.get("exact_hash", ""), norm_hash=fp.get("norm_hash", ""),
            phash=fp.get("phash", ""), sim_vector=fp.get("sim_vector", []),
            tokens=fp.get("tokens", []), profile=fp.get("profile", {}),
        ))
    db.flush()


def check_originality(db: Session, *, campaign_id: str, workspace_id: str | None,
                      brand_id: str | None, channel_id: str | None,
                      script_body: str, hook: str, title: str,
                      scenes: list[dict], visual_types: list[str],
                      thumbnail_phash: str = "", video_duration: float | None = None,
                      external_footage_ratio: float = 0.0,
                      platform_variants: dict | None = None) -> dict:
    """Compare this campaign's fingerprints against recent ones in the workspace
    (own + other brands + other channels). Returns level + dimensions + risks."""
    s = get_settings()
    script_fp = build_text_fingerprint("SCRIPT", script_body)
    hook_fp = build_text_fingerprint("HOOK", hook)
    title_fp = build_text_fingerprint("TITLE", title)
    video_fp = build_video_fingerprint(scenes, duration=video_duration, thumbnail_phash=thumbnail_phash)

    persist_fingerprints(db, campaign_id=campaign_id, content_id=None, workspace_id=workspace_id,
                         brand_id=brand_id, channel_id=channel_id,
                         fps=[script_fp, hook_fp, title_fp, video_fp])

    prior = (db.query(ContentFingerprint)
             .filter(ContentFingerprint.workspace_id == workspace_id,
                     ContentFingerprint.campaign_id != campaign_id)
             .order_by(ContentFingerprint.created_at.desc()).limit(400).all())
    by_campaign: dict[str, dict] = {}
    for p in prior:
        by_campaign.setdefault(p.campaign_id, {})[p.kind] = p

    best = {"campaign_id": None, "combined": 0.0, "scope": "INTERNAL", "dims": {}}
    for cid, kinds in by_campaign.items():
        dims: dict[str, float] = {}
        if "SCRIPT" in kinds:
            st = text_similarity(script_body, _reconstruct(kinds["SCRIPT"]))
            dims["script"] = st["combined"]
            dims["script_norm"] = st["norm"]
        if "HOOK" in kinds:
            dims["hook"] = text_similarity(hook, _reconstruct(kinds["HOOK"]))["combined"]
        if "TITLE" in kinds:
            dims["title"] = text_similarity(title, _reconstruct(kinds["TITLE"]))["combined"]
        if "FINAL_VIDEO" in kinds:
            dims["video"] = video_fp_similarity(video_fp, {"profile": kinds["FINAL_VIDEO"].profile,
                                                           "norm_hash": kinds["FINAL_VIDEO"].norm_hash})
        combined = round(0.5 * dims.get("script", 0) + 0.2 * dims.get("video", 0)
                         + 0.15 * dims.get("hook", 0) + 0.15 * dims.get("title", 0), 4)
        if combined > best["combined"]:
            other = kinds.get("SCRIPT") or kinds.get("FINAL_VIDEO") or next(iter(kinds.values()))
            scope = "INTERNAL"
            if other.brand_id and other.brand_id != brand_id:
                scope = "CROSS_BRAND"
            elif other.channel_id and other.channel_id != channel_id:
                scope = "CROSS_CHANNEL"
            best = {"campaign_id": cid, "combined": combined, "scope": scope, "dims": dims,
                    "against_brand_id": other.brand_id, "against_channel_id": other.channel_id}

    transform = transformation_score(script_body=script_body, scenes=scenes, visual_types=visual_types)
    reuse = reused_content_risk(visual_types=visual_types,
                                external_footage_ratio=external_footage_ratio,
                                transformation=transform["score"])

    # platform-native check (§24-§26)
    native = _platform_native_check(script_body, hook, platform_variants or {})

    combined = best["combined"]
    if combined >= s.originality_block_threshold:
        level = "DUPLICATE" if transform["score"] < 0.4 else "REUSED_WITH_TRANSFORMATION"
    elif combined >= s.originality_review_threshold:
        level = "HIGH_SIMILARITY"
    elif combined >= 0.58:
        level = "SIMILAR"
    else:
        level = "ORIGINAL"
    if reuse["verdict"] == "BLOCK" or native["verdict"] == "BLOCK":
        level = "REVIEW_REQUIRED" if level in ("ORIGINAL", "SIMILAR") else level

    decision = {
        "DUPLICATE": "BLOCK", "REUSED_WITH_TRANSFORMATION": "HUMAN_REVIEW",
        "HIGH_SIMILARITY": "HUMAN_REVIEW", "SIMILAR": "ALLOW", "ORIGINAL": "ALLOW",
        "REVIEW_REQUIRED": "HUMAN_REVIEW",
    }[level]
    if reuse["verdict"] == "BLOCK":
        decision = "BLOCK"
    elif reuse["verdict"] == "HUMAN_REVIEW" and decision == "ALLOW":
        decision = "HUMAN_REVIEW"
    if native["verdict"] in ("FIX_REQUIRED", "BLOCK") and decision == "ALLOW":
        decision = "FIX_REQUIRED"

    row = SimilarityResult(
        workspace_id=workspace_id, campaign_id=campaign_id,
        against_content_id=best["campaign_id"],
        against_brand_id=best.get("against_brand_id"),
        against_channel_id=best.get("against_channel_id"),
        scope=best["scope"], level=level, dimensions=best["dims"],
        transformation_score=transform["score"], reused_content_risk=reuse["risk"],
        reasons=(reuse["reasons"] + native.get("reasons", []) +
                 ([f"{best['scope']} similarity {combined:.0%} vs campaign {best['campaign_id']}"]
                  if best["campaign_id"] else [])),
    )
    db.add(row)
    db.flush()
    return {
        "level": level, "decision": decision, "combined_similarity": combined,
        "scope": best["scope"], "against_campaign_id": best["campaign_id"],
        "dimensions": best["dims"], "transformation": transform, "reuse": reuse,
        "platform_native": native, "result_id": row.id,
    }


def _reconstruct(fp: ContentFingerprint) -> str:
    return " ".join(fp.tokens or [])


def _platform_native_check(script: str, hook: str, variants: dict) -> dict:
    """variants: {platform: {"script": ..., "hook": ..., "cta": ...}} — flag if
    versions are near-identical copy-paste rather than native adaptations (§25)."""
    if len(variants) < 2:
        return {"verdict": "OK", "reasons": []}
    keys = list(variants)
    reasons = []
    high = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = variants[keys[i]], variants[keys[j]]
            s = text_similarity(a.get("script", ""), b.get("script", ""))["combined"]
            h = text_similarity(a.get("hook", ""), b.get("hook", ""))["combined"]
            if s >= 0.92 and h >= 0.9:
                high += 1
                reasons.append(f"{keys[i]} and {keys[j]} are near-identical (script {s:.0%}, hook {h:.0%}) — not natively adapted")
    verdict = "FIX_REQUIRED" if high else "OK"
    return {"verdict": verdict, "reasons": reasons, "identical_pairs": high}
