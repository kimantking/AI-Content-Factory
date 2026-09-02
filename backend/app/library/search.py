"""AUDIT-P8-003 — one ranked global search across the entities a user actually
looks for by name: campaigns, per-platform content, channels, brands, learning
references and publications. Deterministic scoring (exact > prefix > word > sub-
string), small capped result set, workspace-scoped when a workspace is given.
"""
from __future__ import annotations

from sqlalchemy import func as safunc
from sqlalchemy.orm import Session

from app.db.models import Campaign, PlatformContent, Publication, Script
from app.db.models_learn import ReferenceSource
from app.db.models_mb import Brand, Channel

_KINDS = ("campaign", "platform_content", "channel", "brand", "reference", "publication")


def _score(text: str, q: str) -> float:
    t = (text or "").lower().strip()
    ql = q.lower().strip()
    if not t or not ql:
        return 0.0
    if t == ql:
        return 1.0
    if t.startswith(ql):
        return 0.85
    if ql in t.split():
        return 0.7
    if ql in t:
        return 0.55
    # all query words present somewhere
    if all(w in t for w in ql.split() if w):
        return 0.4
    return 0.0


def global_search(db: Session, *, q: str, workspace_id: str | None = None,
                  kinds: list[str] | None = None, limit: int = 20) -> dict:
    q = (q or "").strip()
    kinds = [k for k in (kinds or _KINDS) if k in _KINDS]
    limit = max(1, min(limit, 50))
    if len(q) < 2:
        return {"query": q, "count": 0, "results": [], "note": "query too short (min 2 chars)"}

    like = f"%{q.lower()}%"
    hits: list[dict] = []

    def add(kind, _id, title, subtitle, ref, extra=None, *, min_score=0.0):
        sc = max(_score(title, q), 0.9 * _score(subtitle or "", q), min_score)
        if sc <= 0:
            return
        hits.append({"kind": kind, "id": _id, "title": title, "subtitle": subtitle,
                     "ref": ref, "score": round(sc, 3), **(extra or {})})

    if "campaign" in kinds:
        cq = db.query(Campaign)
        if workspace_id:
            cq = cq.filter(Campaign.workspace_id == workspace_id)
        script_ids = {r[0] for r in db.query(Script.campaign_id).filter(Script.body.ilike(like))}
        for c in cq.filter(safunc.lower(Campaign.topic).like(like) |
                           Campaign.id.in_(script_ids)).limit(limit * 2):
            body_hit = c.id in script_ids and q.lower() not in (c.topic or "").lower()
            add("campaign", c.id, c.topic, "스크립트 본문 일치" if body_hit else (c.status or ""),
                f"/library/{c.id}", {"workspace_id": c.workspace_id, "brand_id": c.brand_id},
                min_score=0.5 if body_hit else 0.0)

    if "platform_content" in kinds:
        pq = db.query(PlatformContent).join(Campaign, PlatformContent.campaign_id == Campaign.id)
        if workspace_id:
            pq = pq.filter(Campaign.workspace_id == workspace_id)
        for pc in pq.filter(safunc.lower(safunc.coalesce(PlatformContent.title, "")).like(like) |
                            safunc.lower(safunc.coalesce(PlatformContent.caption, "")).like(like)
                            ).limit(limit * 2):
            add("platform_content", pc.id, pc.title or f"{pc.platform} 콘텐츠",
                f"{pc.platform} · {pc.content_type}", f"/library/{pc.campaign_id}",
                {"campaign_id": pc.campaign_id, "platform": pc.platform})

    if "channel" in kinds:
        chq = db.query(Channel)
        if workspace_id:
            chq = chq.filter(Channel.workspace_id == workspace_id)
        for ch in chq.filter(safunc.lower(Channel.name).like(like)).limit(limit):
            add("channel", ch.id, ch.name, f"{ch.platform} · {ch.channel_type}",
                f"/channels/{ch.id}", {"brand_id": ch.brand_id})

    if "brand" in kinds:
        bq = db.query(Brand)
        if workspace_id:
            bq = bq.filter(Brand.workspace_id == workspace_id)
        for b in bq.filter(safunc.lower(Brand.name).like(like) |
                           safunc.lower(Brand.slug).like(like)).limit(limit):
            add("brand", b.id, b.name, b.category or "", f"/brands/{b.id}")

    if "reference" in kinds:
        rq = db.query(ReferenceSource)
        if workspace_id:
            rq = rq.filter(ReferenceSource.workspace_id == workspace_id)
        for r in rq.filter(safunc.lower(safunc.coalesce(ReferenceSource.title, "")).like(like) |
                           safunc.lower(ReferenceSource.url).like(like)).limit(limit * 2):
            add("reference", r.id, r.title or r.url, f"{r.source_type} · {r.status}",
                "/references", {"url": r.url})

    if "publication" in kinds:
        pubq = db.query(Publication).join(Campaign, Publication.campaign_id == Campaign.id)
        if workspace_id:
            pubq = pubq.filter(Campaign.workspace_id == workspace_id)
        for p in pubq.filter(safunc.lower(safunc.coalesce(Publication.remote_url, "")).like(like)
                             ).limit(limit):
            add("publication", p.id, p.remote_url or f"{p.platform} 게시물",
                f"{p.platform} · {p.status}", f"/library/{p.campaign_id}",
                {"campaign_id": p.campaign_id})

    hits.sort(key=lambda h: (-h["score"], h["kind"], h["title"]))
    by_kind: dict[str, int] = {}
    for h in hits:
        by_kind[h["kind"]] = by_kind.get(h["kind"], 0) + 1
    return {"query": q, "count": len(hits[:limit]), "by_kind": by_kind,
            "results": hits[:limit]}
