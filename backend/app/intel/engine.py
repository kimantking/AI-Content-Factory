"""URL Learning Engine orchestrator.

add_urls()        — create a LearningJob + one ReferenceSource per URL (with hard
                    count / byte guards).
run_learning_job() — validate -> fetch -> clean/extract -> injection scan ->
                    cheap quality (Stage 1) -> dedup -> chunk -> deep analysis on
                    the top-K (Stage 2) -> dataset -> distillation -> skill notes
                    -> memory. REFERENCE_ONLY stores only (no dataset/prompt/memory
                    side effects). Never runs production work.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import func as safunc
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models_learn import (
    LearningJob,
    ReferenceAnalysis,
    ReferenceChunk,
    ReferenceSource,
)
from app.intel import analyzers as A
from app.intel import injection, quality
from app.intel.dataset import curate, write_records
from app.intel.distillation import distill
from app.intel.extract import chunk, clean_and_extract, extract_plaintext
from app.intel.fetch import fetch
from app.intel.modes import resolve_execution_mode, writes_learning_output
from app.intel.router import AGENT_FOR_ANALYSIS, analyzers_for, resolve_purpose
from app.intel.skills import derive_skill_notes
from app.intel.url_security import canonicalize, classify_url, validate_url


class LearningGuardError(RuntimeError):
    pass


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "").lower()


def add_urls(db: Session, *, urls: list[str], execution_mode: str = "LEARN_ONLY",
             scope: str = "THIS_CAMPAIGN", workspace_id: str | None = None,
             brand_id: str | None = None, channel_id: str | None = None,
             campaign_id: str | None = None, collection_id: str | None = None,
             purpose: str = "AUTO", topic: str = "",
             video_profiles: dict | None = None) -> LearningJob:
    s = get_settings()
    clean_urls, seen = [], set()
    for u in urls or []:
        u = (u or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        clean_urls.append(u)
    if len(clean_urls) > s.max_learning_items_per_job:
        raise LearningGuardError(
            f"{len(clean_urls)} urls exceeds max_learning_items_per_job ({s.max_learning_items_per_job})")

    # daily guard
    since = datetime.now(timezone.utc) - timedelta(days=1)
    today = db.query(safunc.count(ReferenceSource.id)).filter(
        ReferenceSource.workspace_id == workspace_id,
        ReferenceSource.created_at >= since).scalar() or 0
    if today + len(clean_urls) > s.max_daily_learning_items:
        raise LearningGuardError(
            f"daily learning limit reached ({today}+{len(clean_urls)} > {s.max_daily_learning_items})")

    job = LearningJob(
        workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
        campaign_id=campaign_id, collection_id=collection_id,
        execution_mode=resolve_execution_mode(execution_mode).value, scope=scope,
        status="PENDING", total_urls=len(clean_urls),
        config_snapshot={"topic": topic, "purpose": purpose,
                         "max_reference_bytes": s.max_reference_bytes,
                         "deep_top_k": s.learning_deep_analysis_top_k,
                         "video_profiles": {(canonicalize(k)): v for k, v in (video_profiles or {}).items()}},
    )
    db.add(job)
    db.flush()

    for u in clean_urls:
        v = validate_url(u)
        st, sup = classify_url(u)
        db.add(ReferenceSource(
            workspace_id=workspace_id, brand_id=brand_id, channel_id=channel_id,
            campaign_id=campaign_id, learning_job_id=job.id, collection_id=collection_id,
            url=u, canonical_url=(v.url if v.ok else canonicalize(u)),
            url_hash=hashlib.sha256(canonicalize(u).encode()).hexdigest(),
            source_type=st, support_level=(sup if v.ok else "UNSUPPORTED"),
            purpose=purpose, scope=scope,
            status=("PENDING" if v.ok else "BLOCKED"),
            error=("" if v.ok else v.reason),
        ))
    db.flush()
    return job


# --------------------------------------------------------------------- #

def _extract_doc(res, url: str) -> dict:
    ct = (res.content_type or "").lower()
    txt = res.text
    if "pdf" in ct or url.lower().endswith(".pdf"):
        # no PDF parser dependency — honest LIMITED handling
        if txt.strip().startswith("%PDF") or not txt.strip():
            return {"_limited": True, **extract_plaintext("", url=url)}
        return extract_plaintext(txt, url=url)
    if "html" in ct or "<html" in txt.lower() or "<body" in txt.lower():
        return clean_and_extract(txt, url=url)
    return extract_plaintext(txt, url=url)


def _process_reference(db: Session, ref: ReferenceSource, *, topic: str,
                       existing: list[dict], video_profile: dict | None = None) -> dict:
    v = validate_url(ref.url)
    if not v.ok:
        ref.status, ref.error = "BLOCKED", v.reason
        db.flush()
        return {"status": "BLOCKED"}
    ref.status = "FETCHING"
    db.flush()
    res = fetch(ref.url)
    for hop in res.redirects:
        rv = validate_url(hop)
        if not rv.ok:
            ref.status, ref.error = "BLOCKED", f"redirect blocked: {rv.reason}"
            db.flush()
            return {"status": "BLOCKED"}
    if not res.ok:
        ref.status, ref.error = "FETCH_FAILED", (res.error or f"http {res.status}")[:500]
        db.flush()
        return {"status": "FETCH_FAILED"}

    ref.byte_size = len(res.body)
    doc = _extract_doc(res, res.final_url or ref.url)
    doc["_video_profile"] = video_profile or {}
    text = doc.get("main_text", "")

    inj = injection.scan(text + "\n" + "\n".join(doc.get("headings", [])))
    ref.injection_flag = inj["flag"]
    ref.injection_detail = {"severity": inj["severity"], "kinds": inj["kinds"],
                            "count": len(inj["matches"])}
    safe_text, _ = injection.sanitize(text)
    doc["main_text"] = safe_text        # everything downstream sees sanitized data only

    # metadata
    ref.title = (doc.get("title") or "")[:500]
    ref.author = (doc.get("author") or "")[:200]
    ref.publisher = (doc.get("publisher") or "")[:200]
    ref.published_at = (doc.get("published_at") or "")[:40]
    ref.updated_at_src = (doc.get("updated_at") or "")[:40]
    ref.language = (doc.get("language") or "")[:12]
    ref.content_hash = quality.content_hash(safe_text)
    ref.text_fingerprint = quality.text_fingerprint(safe_text)
    ref.token_count = max(1, round(len(safe_text) / 4))

    # dedup (spec §AG)
    dup = quality.duplicate_of(doc, canonical_url=ref.canonical_url, existing=existing)
    if dup:
        ref.status = "DUPLICATE"
        ref.notes = f"duplicate of {dup['match_id']} via {dup['method']}"
        ref.learning_weight = 0.1
        db.flush()
        return {"status": "DUPLICATE", "dup": dup}

    # Stage-1 cheap quality
    qs = quality.analyze_quality(doc, source_type=ref.source_type, topic=topic,
                                injection_severity=inj["severity"])
    ref.quality_score = qs["aggregate"]
    ref.trust_score = qs["source_quality"]
    ref.relevance_score = qs["relevance"]
    ref.freshness_score = qs["freshness"]
    ref.originality_score = qs["novelty"]
    ref.noise_score = qs["noise"]
    ref.learning_weight = qs["learning_weight"]
    ref.topic_cluster = (topic or ref.title or "").strip()[:60]
    # a video reference's value is in the provided structured profile, not the page
    # text — don't down-rank it just because the landing page is thin
    _is_video = ref.source_type in ("YOUTUBE", "VIDEO_PAGE") or bool(doc.get("_video_profile"))
    ref.status = "EXTRACTED" if (_is_video or not qs["low_value"]) else "LOW_VALUE"

    # chunks
    for ch in chunk(doc):
        db.add(ReferenceChunk(
            reference_id=ref.id, workspace_id=ref.workspace_id, chunk_index=ch["chunk_index"],
            heading=ch["heading"][:400], position=ch["position"],
            content_hash=ch["content_hash"], token_count=ch["token_count"], text=ch["text"]))

    db.add(ReferenceAnalysis(
        reference_id=ref.id, workspace_id=ref.workspace_id, brand_id=ref.brand_id,
        channel_id=ref.channel_id, analysis_kind="QUALITY", data=qs, confidence=1.0))
    db.flush()
    existing.append({"id": ref.id, "canonical_url": ref.canonical_url,
                     "content_hash": ref.content_hash, "text_fingerprint": ref.text_fingerprint,
                     "sim_vector": [], "main_text": safe_text[:6000]})
    return {"status": ref.status, "doc": doc, "quality": qs}


def _deep_analyze(db: Session, ref: ReferenceSource, doc: dict, *, topic: str) -> dict:
    purpose = resolve_purpose(user_purpose=ref.purpose, source_type=ref.source_type, doc=doc)
    ref.resolved_purpose = purpose
    kinds = analyzers_for(purpose)
    text = doc.get("main_text", "")
    produced: dict[str, dict] = {}
    video_profile = (doc.get("_video_profile") or {})    # caller-supplied structure, if any

    for kind in kinds:
        data, conf, unknown = {}, 0.7, []
        if kind == "FACTS":
            data = A.extract_facts(text, source_url=ref.url)
        elif kind == "KNOWLEDGE":
            data = A.extract_knowledge(text)
        elif kind == "WRITING_PROFILE":
            data = A.writing_profile(text)
        elif kind == "VIDEO_OBSERVATION":
            data = A.video_observation(video_profile)
            unknown = data.get("_unknown_fields", [])
            conf = data.get("_coverage", 0.0)
        elif kind in ("HOOK_PATTERN", "STORY_PROFILE", "EDITING_PROFILE", "BROLL_PROFILE",
                      "SUBTITLE_PROFILE", "VOICE_PROFILE", "AUDIO_PROFILE", "GRAPHICS_PROFILE",
                      "THUMBNAIL_PROFILE", "RETENTION_PATTERN"):
            subs = A.video_subprofiles(A.video_observation(video_profile))
            data = subs.get(kind, {})
            conf = 0.0 if all(v == A.UNKNOWN for v in data.values()) else 0.6
        elif kind == "GITHUB_ANALYSIS":
            data = A.github_analysis(text, url=ref.url)
        elif kind == "COMPETITOR_ANALYSIS":
            data = A.competitor_analysis(doc)
        if not data:
            continue
        db.add(ReferenceAnalysis(
            reference_id=ref.id, workspace_id=ref.workspace_id, brand_id=ref.brand_id,
            channel_id=ref.channel_id, analysis_kind=kind, data=data,
            confidence=round(float(conf), 3), unknown_fields=list(unknown)))
        produced[kind] = {"data": data, "confidence": round(float(conf), 3)}
    ref.status = "READY"
    db.flush()
    return produced


def run_learning_job(db: Session, job_id: str) -> dict:
    s = get_settings()
    job = db.get(LearningJob, job_id)
    if job is None:
        return {"ok": False, "error": "job not found"}
    job.status = "RUNNING"
    db.flush()
    mode = resolve_execution_mode(job.execution_mode)
    topic = (job.config_snapshot or {}).get("topic", "")

    video_profiles = (job.config_snapshot or {}).get("video_profiles", {}) or {}
    refs = db.query(ReferenceSource).filter_by(learning_job_id=job.id).all()
    existing = [
        {"id": r.id, "canonical_url": r.canonical_url, "content_hash": r.content_hash,
         "text_fingerprint": r.text_fingerprint, "sim_vector": [],
         "main_text": ""}
        for r in db.query(ReferenceSource).filter(
            ReferenceSource.workspace_id == job.workspace_id,
            ReferenceSource.learning_job_id != job.id,
            ReferenceSource.status.in_(["READY", "EXTRACTED"])).all()
    ]

    docs: dict[str, dict] = {}
    counters = {"fetched": 0, "ready": 0, "blocked": 0, "duplicates": 0, "low_value": 0}
    for ref in refs:
        if ref.status == "BLOCKED":
            counters["blocked"] += 1
            continue
        _vp = video_profiles.get(ref.canonical_url) or video_profiles.get(ref.url)
        r = _process_reference(db, ref, topic=topic, existing=existing, video_profile=_vp)
        st = r["status"]
        if st == "BLOCKED":
            counters["blocked"] += 1
        elif st == "FETCH_FAILED":
            pass
        elif st == "DUPLICATE":
            counters["duplicates"] += 1
        else:
            counters["fetched"] += 1
            if st == "LOW_VALUE":
                counters["low_value"] += 1
            docs[ref.id] = r["doc"]

    # Stage 2 — deep analysis on the top-K by quality (cheap-first, spec §AK)
    ranked = sorted(
        [r for r in refs if r.status in ("EXTRACTED",) and r.id in docs],
        key=lambda r: r.quality_score, reverse=True)
    top_k = ranked[: (job.config_snapshot or {}).get("deep_top_k", s.learning_deep_analysis_top_k)]
    all_analyses: dict[str, list[dict]] = {}     # kind -> [{reference_id, data, source_domain}]
    for ref in top_k:
        produced = _deep_analyze(db, ref, docs[ref.id], topic=topic)
        counters["ready"] += 1
        if not writes_learning_output(mode):
            continue
        for kind, blob in produced.items():
            all_analyses.setdefault(kind, []).append({
                "reference_id": ref.id, "data": blob["data"],
                "confidence": blob["confidence"], "source_domain": _domain(ref.url),
                "observation": f"{kind} observed on {_domain(ref.url)}",
            })

    datasets = blueprints = skills = 0
    if writes_learning_output(mode):
        # dataset records
        for ref in top_k:
            per_ref = {}
            for a in db.query(ReferenceAnalysis).filter_by(reference_id=ref.id).all():
                if a.analysis_kind in ("QUALITY",):
                    continue
                per_ref[a.analysis_kind] = {"data": a.data, "confidence": a.confidence}
            datasets += len(write_records(db, reference=ref, analyses=per_ref,
                                          topic_cluster=ref.topic_cluster, language=ref.language))
        # distillation + skill notes (multi-reference where possible)
        quality_mean = round(sum(r.quality_score for r in top_k) / max(1, len(top_k)), 3)
        for kind, evid in all_analyses.items():
            agent = AGENT_FOR_ANALYSIS.get(kind, "Video Director")
            bp = distill(db, workspace_id=job.workspace_id, brand_id=job.brand_id,
                         channel_id=job.channel_id, agent_type=agent, kind=kind,
                         evidence=evid, topic_clusters=[topic[:64]] if topic else [],
                         quality=quality_mean)
            if bp:
                blueprints += 1
            consistency = 0.6 if len(evid) >= 3 else (0.4 if len(evid) == 2 else 0.2)
            note = derive_skill_notes(db, workspace_id=job.workspace_id, brand_id=job.brand_id,
                                      channel_id=job.channel_id, kind=kind, evidence=evid,
                                      consistency=consistency, topic_cluster=topic[:64])
            if note:
                skills += 1
        # memory writer — FACTS/KNOWLEDGE go in as guidance (never auto-VERIFIED)
        _write_memory(db, all_analyses, workspace_id=job.workspace_id)
        curate(db, workspace_id=job.workspace_id)

    job.fetched = counters["fetched"]
    job.ready = counters["ready"]
    job.blocked = counters["blocked"]
    job.duplicates = counters["duplicates"]
    job.low_value = counters["low_value"]
    job.datasets_written = datasets
    job.blueprints_created = blueprints
    job.skills_created = skills
    job.status = "DONE"
    job.finished_at = datetime.now(timezone.utc)
    job.result = {"counters": counters, "datasets": datasets, "blueprints": blueprints,
                  "skills": skills, "mode": mode.value,
                  "reference_only": mode.value == "REFERENCE_ONLY"}
    db.flush()
    return {"ok": True, "job_id": job.id, **job.result}


def _write_memory(db: Session, all_analyses: dict, *, workspace_id: str | None) -> None:
    try:
        from app.learning.memory import upsert_memory
    except Exception:  # noqa: BLE001
        return
    for kind in ("KNOWLEDGE",):
        for e in all_analyses.get(kind, [])[:10]:
            points = (e["data"].get("main_points") or [])[:1]
            if not points:
                continue
            try:
                upsert_memory(db, memory_type="TOPIC",
                              statement=f"[learned:external] {points[0][:200]}",
                              platform=None, content_type=None, sample_size=1,
                              confidence=0.3, consistent=True)
            except Exception:  # noqa: BLE001
                continue
