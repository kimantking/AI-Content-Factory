"""Content Library read model + one write action (add a platform to an existing
campaign, generating only that platform's adaptation/media)."""
from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import func as safunc
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    AnalyticsSnapshot,
    Asset,
    Campaign,
    CostLog,
    PlatformContent,
    Publication,
    PublishJob,
    RevenueEntry,
    Scene,
    Script,
)

_MEDIA_ASSET_TYPES = ("render", "video", "image", "thumbnail", "audio", "subtitle", "carousel", "chart")


def _is_legacy(camp: Campaign, contents: list[PlatformContent]) -> bool:
    """Pre-Phase-6/7/8 content: no tenant scope AND no execution mode. A campaign
    created by the current product always carries at least one of those."""
    return camp.workspace_id is None and getattr(camp, "execution_mode", None) is None


def _render_asset(assets: list[Asset]) -> Asset | None:
    for a in assets:
        if a.asset_type == "render":
            return a
    for a in assets:
        if a.asset_type == "video":
            return a
    return None


def _file_exists(path: str | None) -> bool:
    return bool(path) and os.path.isfile(path)


def _publish_state(pubs: list[Publication], jobs: list[PublishJob]) -> str:
    if any(p.status in ("PUBLISHED", "VERIFYING") for p in pubs):
        return "PUBLISHED"
    if any(j.status == "BLOCKED" for j in jobs):
        return "BLOCKED"
    if any(j.status in ("SCHEDULED", "QUEUED", "READY", "WAITING_APPROVAL") for j in jobs):
        return "SCHEDULED"
    if jobs:
        return "DRAFT"
    return "NOT_PUBLISHED"


def _views(db: Session, campaign_id: str) -> int | None:
    rows = (db.query(AnalyticsSnapshot.views)
            .filter(AnalyticsSnapshot.campaign_id == campaign_id,
                    AnalyticsSnapshot.views.isnot(None))
            .order_by(AnalyticsSnapshot.collected_at.desc()).limit(20).all())
    vals = [r[0] for r in rows if r[0] is not None]
    return max(vals) if vals else None


def _money(db: Session, campaign_id: str) -> dict:
    rev = db.query(RevenueEntry).filter_by(campaign_id=campaign_id).all()
    actual = round(sum(r.amount for r in rev if not r.is_estimate), 2) if rev else None
    est = round(sum(r.amount for r in rev if r.is_estimate), 2) if rev else None
    cost_usd = db.query(safunc.coalesce(safunc.sum(CostLog.amount_usd), 0.0)).filter(
        CostLog.campaign_id == campaign_id).scalar() or 0.0
    asset_cost = db.query(safunc.coalesce(safunc.sum(Asset.cost), 0.0)).filter(
        Asset.campaign_id == campaign_id).scalar() or 0.0
    return {"revenue_actual": actual, "revenue_estimated": est,
            "cost_usd": round(cost_usd + asset_cost, 4),
            "currency": rev[0].currency if rev else "KRW"}


# --------------------------------------------------------------------- #
#  list
# --------------------------------------------------------------------- #

def list_content(db: Session, *, workspace_id: str | None = None, brand_id: str | None = None,
                 channel_id: str | None = None, platform: str | None = None,
                 content_type: str | None = None, status: str | None = None,
                 governance: str | None = None, publish_state: str | None = None,
                 query: str | None = None, sort: str = "newest",
                 page: int = 1, page_size: int | None = None) -> dict:
    s = get_settings()
    page_size = min(page_size or s.content_library_page_size, 100)
    q = db.query(Campaign)
    if workspace_id:
        q = q.filter(Campaign.workspace_id == workspace_id)
    if brand_id:
        q = q.filter(Campaign.brand_id == brand_id)
    if channel_id:
        q = q.filter(Campaign.channel_id == channel_id)
    if status:
        q = q.filter(Campaign.status == status)
    if query:
        like = f"%{query.strip()}%"
        sub = db.query(Script.campaign_id).filter(Script.body.ilike(like))
        q = q.filter(safunc.lower(Campaign.topic).like(like.lower()) | Campaign.id.in_(sub))

    order = {
        "newest": Campaign.created_at.desc(), "oldest": Campaign.created_at.asc(),
    }.get(sort, Campaign.created_at.desc())
    q = q.order_by(order)

    # Fast path: no child-row filter and no metric sort -> paginate in the DB and
    # only enrich the current page. Falls back to the full scan when a python-only
    # filter (platform / content_type / governance / publish_state) or a metric
    # sort is active, where every candidate must be materialised for correctness.
    _py_filter = any((platform, content_type, governance, publish_state))
    _metric_sort = sort in ("views", "revenue", "profit", "performance")
    if not _py_filter and not _metric_sort:
        grand_total = q.with_entities(safunc.count(Campaign.id)).order_by(None).scalar() or 0
        start = (max(1, page) - 1) * page_size
        all_ids = [c.id for c in q.offset(start).limit(page_size).all()]
        cards = [_card(db, cid) for cid in all_ids]
        return {"total": grand_total, "page": page, "page_size": page_size,
                "pages": (grand_total + page_size - 1) // page_size, "items": cards}

    all_ids = [c.id for c in q.all()]

    # platform/content_type/governance/publish filters need the child rows -> filter in python
    cards: list[dict] = []
    for cid in all_ids:
        card = _card(db, cid)
        if platform and platform not in card["platforms"]:
            continue
        if content_type and content_type not in card["content_types"]:
            continue
        if governance and card["governance"] != governance:
            continue
        if publish_state and card["publish_state"] != publish_state:
            continue
        cards.append(card)

    # metric sorts after enrichment
    if sort in ("views", "revenue", "profit", "performance"):
        keyf = {
            "views": lambda c: (c["views"] or -1),
            "revenue": lambda c: (c["revenue_actual"] or c["revenue_estimated"] or -1),
            "profit": lambda c: ((c["revenue_actual"] or 0) - (c["cost_usd"] or 0)),
            "performance": lambda c: (c["views"] or 0),
        }[sort]
        cards.sort(key=keyf, reverse=True)

    total = len(cards)
    start = (max(1, page) - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            "items": cards[start:start + page_size]}


def _card(db: Session, cid: str) -> dict:
    """Build one library card for a campaign (child-row enrichment)."""
    camp = db.get(Campaign, cid)
    contents = db.query(PlatformContent).filter_by(campaign_id=cid).all()
    assets = db.query(Asset).filter_by(campaign_id=cid).all()
    jobs = db.query(PublishJob).filter_by(campaign_id=cid).all()
    pubs = db.query(Publication).filter_by(campaign_id=cid).all()
    generated = {c.platform for c in contents}
    plats = sorted(generated | set(camp.platforms or []))
    gov = _gov_summary(contents)
    pstate = _publish_state(pubs, jobs)
    render = _render_asset(assets)
    thumb = next((a for a in assets if a.asset_type == "thumbnail"), None)
    return {
        "campaign_id": cid, "topic": camp.topic,
        "workspace_id": camp.workspace_id, "brand_id": camp.brand_id,
        "channel_id": camp.channel_id,
        "created_at": camp.created_at.isoformat() if camp.created_at else None,
        "status": camp.status, "execution_mode": getattr(camp, "execution_mode", None),
        "legacy": _is_legacy(camp, contents),
        "platforms": plats, "platform_count": len(plats),
        "generated_platforms": sorted(generated),
        "content_types": sorted({c.content_type for c in contents}),
        "governance": gov,
        "publish_state": pstate,
        "has_video": bool(render), "video_playable": _file_exists(render.storage_path if render else None),
        "duration": render.duration if render else None,
        "thumbnail_path": thumb.storage_path if thumb else (render.storage_path if render else None),
        "is_demo": _is_demo(assets),
        "views": _views(db, cid),
        **_money(db, cid),
    }


def _gov_summary(contents: list[PlatformContent]) -> str:
    states = {getattr(c, "governance_decision", None) or getattr(c, "governance_state", None)
              for c in contents}
    states.discard(None)
    if not states:
        return "NOT_APPLICABLE" if contents else "NONE"
    if any(x in ("BLOCK", "BLOCKED") for x in states):
        return "BLOCKED"
    if any(x in ("FIX_REQUIRED", "HUMAN_REVIEW") for x in states):
        return "REVIEW"
    return "OK"


_DEMO_NAMES = ("advanced_short", "advanced_trend_short", "advanced_explainer", "sample", "demo")


def _is_demo(assets: list[Asset]) -> bool:
    for a in assets:
        p = (a.storage_path or "").lower()
        if any(n in p for n in _DEMO_NAMES):
            return True
        if (a.meta or {}).get("demo") or a.provider_mode == "MOCK" and a.asset_type == "render" \
                and "sample" in p:
            return True
    return False


# --------------------------------------------------------------------- #
#  detail
# --------------------------------------------------------------------- #

def content_detail(db: Session, campaign_id: str) -> dict | None:
    camp = db.get(Campaign, campaign_id)
    if camp is None:
        return None
    contents = db.query(PlatformContent).filter_by(campaign_id=campaign_id).all()
    assets = db.query(Asset).filter_by(campaign_id=campaign_id).all()
    scenes = db.query(Scene).filter_by(campaign_id=campaign_id).order_by(Scene.scene_order).all()
    scripts = db.query(Script).filter_by(campaign_id=campaign_id).all()
    jobs = db.query(PublishJob).filter_by(campaign_id=campaign_id).all()
    pubs = db.query(Publication).filter_by(campaign_id=campaign_id).all()
    render = _render_asset(assets)

    master_script = next((s for s in scripts if s.platform in ("MASTER", "master")), scripts[0] if scripts else None)

    return {
        "overview": {
            "campaign_id": campaign_id, "topic": camp.topic, "status": camp.status,
            "audience_goal": camp.audience_goal,
            "workspace_id": camp.workspace_id, "brand_id": camp.brand_id, "channel_id": camp.channel_id,
            "execution_mode": getattr(camp, "execution_mode", None),
            "legacy": _is_legacy(camp, contents),
            "created_at": camp.created_at.isoformat() if camp.created_at else None,
            "platforms": sorted({c.platform for c in contents}),
            "governance": _gov_summary(contents),
            "publish_state": _publish_state(pubs, jobs),
            "is_demo": _is_demo(assets),
            **_money(db, campaign_id),
            "views": _views(db, campaign_id),
        },
        "preview": {
            "video_path": render.storage_path if render else None,
            "video_playable": _file_exists(render.storage_path if render else None),
            "duration": render.duration if render else None,
            "width": render.width if render else None, "height": render.height if render else None,
            "fps": (render.meta or {}).get("fps") if render else None,
            "size_bytes": (os.path.getsize(render.storage_path)
                           if _file_exists(render.storage_path if render else None) else None),
            "version": (render.meta or {}).get("version") if render else None,
        },
        "script": {
            "master": {"body": master_script.body, "word_count": master_script.word_count,
                       "qa_passed": master_script.qa_passed} if master_script else None,
            "platform_scripts": [{"platform": s.platform, "body": s.body,
                                  "word_count": s.word_count} for s in scripts
                                 if s.platform not in ("MASTER", "master")],
        },
        "platform_versions": [
            {"platform": c.platform, "content_type": c.content_type, "title": c.title,
             "hook": c.hook, "status": c.status,
             "governance_state": getattr(c, "governance_state", None),
             "governance_decision": getattr(c, "governance_decision", None),
             "generated": True}
            for c in contents
        ] or [{"platform": "—", "generated": False, "note": "NOT GENERATED"}],
        "media": [
            {"asset_type": a.asset_type, "provider": a.provider, "provider_mode": a.provider_mode,
             "path": a.storage_path, "exists": _file_exists(a.storage_path),
             "mime_type": a.mime_type, "width": a.width, "height": a.height,
             "duration": a.duration, "status": a.status}
            for a in assets if a.asset_type in _MEDIA_ASSET_TYPES
        ],
        "references": _references(db, campaign_id),
        "learning": _learning_evidence(db, campaign_id),
        "governance": _governance_detail(db, campaign_id, contents),
        "publishing": [
            {"platform": j.platform, "status": j.status, "run_mode": j.run_mode,
             "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
             "last_error_type": j.last_error_type,
             "remote_url": next((p.remote_url for p in pubs if p.publish_job_id == j.id), None)}
            for j in jobs
        ],
        "analytics": _analytics(db, campaign_id),
        "revenue": _revenue(db, campaign_id),
        "history": _history(db, campaign_id, scripts, assets, contents),
    }


def _references(db: Session, campaign_id: str) -> list[dict]:
    try:
        from app.db.models_learn import ReferenceSource
        rows = db.query(ReferenceSource).filter_by(campaign_id=campaign_id).all()
    except Exception:  # noqa: BLE001
        return []
    return [{"url": r.url, "source_type": r.source_type, "status": r.status,
             "resolved_purpose": r.resolved_purpose, "quality_score": r.quality_score,
             "rights_status": r.rights_status, "injection_flag": r.injection_flag} for r in rows]


def _learning_evidence(db: Session, campaign_id: str) -> dict:
    try:
        from app.db.models_learn import (
            DatasetRecord,
            PromptBlueprintEvidence,
            ReferenceSource,
        )
        ref_ids = [r.id for r in db.query(ReferenceSource.id)
                   .filter(ReferenceSource.campaign_id == campaign_id).all()]
        ds = (db.query(DatasetRecord).filter(DatasetRecord.reference_id.in_(ref_ids or ["__none__"]))
              .count()) if ref_ids else 0
        bp_ev = db.query(PromptBlueprintEvidence).filter_by(campaign_id=campaign_id).count()
    except Exception:  # noqa: BLE001
        return {"dataset_records": 0, "blueprint_evidence": 0}
    return {"dataset_records": ds, "blueprint_evidence": bp_ev}


def _governance_detail(db: Session, campaign_id: str, contents: list[PlatformContent]) -> dict:
    out = {"summary": _gov_summary(contents), "cases": [], "manifests": 0}
    try:
        from app.db.models_gov import GovernanceCase, RightsManifest
        out["cases"] = [
            {"case_type": c.case_type, "severity": c.severity, "decision": c.decision,
             "reason_codes": c.reason_codes, "hard_block": c.hard_block}
            for c in db.query(GovernanceCase).filter_by(campaign_id=campaign_id).limit(50).all()
        ]
        out["manifests"] = db.query(RightsManifest).filter_by(campaign_id=campaign_id).count()
    except Exception:  # noqa: BLE001
        pass
    return out


def _analytics(db: Session, campaign_id: str) -> list[dict]:
    rows = (db.query(AnalyticsSnapshot).filter_by(campaign_id=campaign_id)
            .order_by(AnalyticsSnapshot.collected_at.desc()).limit(30).all())
    return [{"platform": r.platform, "window": r.window_label, "views": r.views,
             "collected_at": r.collected_at.isoformat() if r.collected_at else None}
            for r in rows]


def _revenue(db: Session, campaign_id: str) -> dict:
    rows = db.query(RevenueEntry).filter_by(campaign_id=campaign_id).all()
    return {
        "actual": round(sum(r.amount for r in rows if not r.is_estimate), 2) if rows else None,
        "estimated": round(sum(r.amount for r in rows if r.is_estimate), 2) if rows else None,
        "entries": [{"source": r.source, "amount": r.amount, "currency": r.currency,
                     "is_estimate": r.is_estimate, "platform": r.platform} for r in rows],
    }


def _history(db: Session, campaign_id: str, scripts, assets, contents) -> list[dict]:
    events: list[dict] = []
    for s in scripts:
        events.append({"kind": "SCRIPT", "label": f"script[{s.platform}] v", "at": None,
                       "word_count": s.word_count})
    by_type: dict[str, list] = {}
    for a in assets:
        by_type.setdefault(a.asset_type, []).append(a)
    for t, rows in by_type.items():
        rows.sort(key=lambda a: a.created_at or datetime.min)
        for i, a in enumerate(rows):
            events.append({"kind": t.upper(), "label": f"{t} version {i + 1}",
                           "at": a.created_at.isoformat() if a.created_at else None,
                           "role": "ORIGINAL" if i == 0 else "REVISION",
                           "current": i == len(rows) - 1})
    try:
        from app.db.models_gov import GovernanceEvent
        for e in db.query(GovernanceEvent).filter_by(campaign_id=campaign_id).limit(50).all():
            events.append({"kind": "GOVERNANCE", "label": f"{e.kind} -> {e.to_state}",
                           "at": e.created_at.isoformat() if e.created_at else None})
    except Exception:  # noqa: BLE001
        pass
    events.sort(key=lambda x: (x.get("at") or ""))
    return events


# --------------------------------------------------------------------- #
#  stats + add platform
# --------------------------------------------------------------------- #

def library_stats(db: Session, *, workspace_id: str | None = None) -> dict:
    q = db.query(Campaign)
    if workspace_id:
        q = q.filter(Campaign.workspace_id == workspace_id)
    camps = q.all()
    total = len(camps)
    legacy = sum(1 for c in camps
                 if c.workspace_id is None and getattr(c, "execution_mode", None) is None)
    with_video = db.query(safunc.count(safunc.distinct(Asset.campaign_id))).filter(
        Asset.asset_type.in_(("render", "video"))).scalar() or 0
    published = db.query(safunc.count(safunc.distinct(Publication.campaign_id))).filter(
        Publication.status.in_(("PUBLISHED", "VERIFYING"))).scalar() or 0
    return {"total_campaigns": total, "legacy_campaigns": legacy,
            "campaigns_with_video": with_video, "published_campaigns": published}


def add_platform_to_campaign(db: Session, *, campaign_id: str, platform: str,
                             mode: str = "GENERATE_AND_PUBLISH") -> dict:
    """Add a platform to an existing campaign. Generates ONLY that platform's
    adaptation + media — existing platforms are never regenerated."""
    from app.intel.platform_selection import CONTENT_TYPES, resolve_selection, set_selection

    camp = db.get(Campaign, campaign_id)
    if camp is None:
        return {"ok": False, "error": "campaign not found"}
    if platform not in CONTENT_TYPES:
        return {"ok": False, "error": f"unknown platform {platform}"}
    existing = {c.platform for c in db.query(PlatformContent).filter_by(campaign_id=campaign_id)}
    existing |= set(camp.platforms or [])            # already selected, even if not yet built
    if platform in existing:
        return {"ok": False, "error": f"{platform} already generated / selected",
                "existing": sorted(existing)}

    cur = resolve_selection(db, campaign_id)
    cur[platform] = {CONTENT_TYPES[platform][0]: mode}
    set_selection(db, campaign_id=campaign_id, selection=cur,
                  workspace_id=camp.workspace_id, brand_id=camp.brand_id,
                  channel_id=camp.channel_id, user_explicit=True)
    new_platforms = sorted(set(camp.platforms or []) | {platform})
    camp.platforms = new_platforms
    db.flush()
    return {"ok": True, "campaign_id": campaign_id, "added": platform,
            "generate_now": [platform], "unchanged": sorted(existing),
            "note": "run the media pipeline for this campaign; only the new platform is built"}
