"""Content routing (§59-§63) + cross-channel cannibalization guard (§38-§39) —
deterministic (reuses the cheap embedding).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.analytics.embedding import cosine, embed
from app.db.models import Campaign, PlatformContent
from app.db.models_mb import Brand, Channel, ContentPillar, ContentRoutingDecision

_ROUTING_WEIGHTS = {
    "audience_fit": .18, "topic_fit": .18, "brand_fit": .16, "historical": .12,
    "channel_health": .10, "capacity": .08, "revenue": .08, "fatigue": .06,
    "competition": .02, "risk": .02,
}


def _topic_fit(topic: str, channel: Channel, pillars: list[ContentPillar]) -> float:
    tv = embed(topic)
    best = 0.0
    for p in pillars:
        for kw in (p.keywords or [p.name]):
            best = max(best, cosine(tv, embed(kw)))
    strat_topics = (channel.content_strategy or {}).get("topics", [])
    for kw in strat_topics:
        best = max(best, cosine(tv, embed(kw)))
    return round(best, 3)


def _brand_fit(topic: str, brand: Brand) -> float:
    risk = brand.risk_policy or {}
    low = topic.lower()
    for blocked in risk.get("blocked_topics", []) + risk.get("blocked_keywords", []):
        if blocked and blocked.lower() in low:
            return 0.0
    prof = brand.profile or {}
    prefs = prof.get("preferred_topics", [])
    if not prefs:
        return 0.6
    tv = embed(topic)
    return round(min(1.0, 0.4 + 0.6 * max((cosine(tv, embed(p)) for p in prefs), default=0.0)), 3)


def _recent_fatigue(db: Session, channel_id: str, topic: str, *, days: int = 21) -> float:
    cut = datetime.now(timezone.utc) - timedelta(days=days)
    camps = (db.query(Campaign)
             .filter(Campaign.channel_id == channel_id, Campaign.created_at >= cut).all())
    if not camps:
        return 0.0
    tv = embed(topic)
    sims = [cosine(tv, embed(getattr(c, "topic", "") or "")) for c in camps]
    return round(max(sims, default=0.0), 3)


def route(db: Session, *, workspace_id: str, topic: str, angle: str = "",
          candidate_id: str | None = None, capacity_by_channel: dict[str, float] | None = None
          ) -> ContentRoutingDecision:
    channels = (db.query(Channel)
                .filter_by(workspace_id=workspace_id, status="ACTIVE").all())
    scores: dict[str, dict] = {}
    for ch in channels:
        brand = db.get(Brand, ch.brand_id)
        if brand is None or brand.status != "ACTIVE":
            continue
        pillars = db.query(ContentPillar).filter_by(brand_id=ch.brand_id, status="ACTIVE").all()
        snap_score = _latest_health(db, ch.id)
        bf = _brand_fit(topic, brand)
        dims = {
            "audience_fit": 0.6,                       # no audience vectors yet
            "topic_fit": _topic_fit(topic, ch, pillars),
            "brand_fit": bf,
            "historical": min(1.0, snap_score / 100.0),
            "channel_health": min(1.0, snap_score / 100.0),
            "capacity": float((capacity_by_channel or {}).get(ch.id, 1.0)),
            "revenue": 0.5,
            "fatigue": max(0.0, 1.0 - _recent_fatigue(db, ch.id, topic)),
            "competition": 0.7,
            "risk": 1.0 if bf > 0 else 0.0,
        }
        total = sum(_ROUTING_WEIGHTS[k] * dims[k] for k in _ROUTING_WEIGHTS)
        if bf == 0.0:
            total = 0.0                                # brand policy block
        scores[ch.id] = {"total": round(total, 4), "dims": {k: round(v, 3) for k, v in dims.items()},
                         "brand_id": ch.brand_id, "platform": ch.platform}

    ranked = sorted(scores.items(), key=lambda kv: kv[1]["total"], reverse=True)
    routed = ranked[0] if ranked and ranked[0][1]["total"] > 0 else None
    cannib = cannibalization_status(db, workspace_id, topic, angle,
                                    exclude_channel=routed[0] if routed else None)
    row = ContentRoutingDecision(
        workspace_id=workspace_id, topic=topic, candidate_id=candidate_id,
        routed_channel_id=routed[0] if routed else None,
        routed_brand_id=routed[1]["brand_id"] if routed else None,
        scores=scores, cannibalization=cannib["status"],
        decision={"ranked": [cid for cid, _ in ranked[:5]],
                  "reason": "top routing score" if routed else "no eligible channel (brand policy / no fit)",
                  "cannibalization": cannib},
    )
    db.add(row)
    db.flush()
    return row


def _latest_health(db: Session, channel_id: str) -> float:
    from app.db.models_mb import ChannelHealthSnapshot
    r = (db.query(ChannelHealthSnapshot).filter_by(channel_id=channel_id)
         .order_by(ChannelHealthSnapshot.created_at.desc()).first())
    return float(r.score) if r else 50.0


def cannibalization_status(db: Session, workspace_id: str, topic: str, angle: str = "",
                           *, exclude_channel: str | None = None, days: int = 3) -> dict:
    """Different revenue channels producing near-identical content at the same time
    is a risk; the SAME brand adapting one topic natively across platforms is fine."""
    cut = datetime.now(timezone.utc) - timedelta(days=days)
    tv = embed(topic)
    av = embed(f"{topic} {angle}")
    recent = (db.query(Campaign)
              .filter(Campaign.workspace_id == workspace_id, Campaign.created_at >= cut).all())
    hits = []
    for c in recent:
        if exclude_channel and c.channel_id == exclude_channel:
            continue
        ct = getattr(c, "topic", "") or ""
        sim = cosine(tv, embed(ct))
        if sim >= 0.82:
            hits.append({"campaign_id": c.id, "channel_id": c.channel_id,
                         "brand_id": c.brand_id, "similarity": round(sim, 3),
                         "angle_similarity": round(cosine(av, embed(ct)), 3)})
    distinct_brands = {h["brand_id"] for h in hits if h["brand_id"]}
    status = "SAFE"
    if hits:
        # same brand / different platform = OK (cross-platform native adaptation)
        if len(distinct_brands) >= 1 and any(h["angle_similarity"] >= 0.8 for h in hits):
            status = "CANNIBALIZATION_RISK" if len(hits) >= 2 else "OVERLAP"
        else:
            status = "OVERLAP"
    return {"status": status, "matches": hits[:8]}
