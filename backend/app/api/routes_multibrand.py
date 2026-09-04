from __future__ import annotations

import re

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.context import AuthContext
from app.auth.deps import current_user, require_role
from app.auth.service import add_member
from app.db.base import get_db
from app.db.models_mb import (
    Brand,
    Channel,
    ContentPillar,
    Workspace,
)
from app.mb import budget as _budget
from app.mb import channel_manager as _cm
from app.mb import monetization as _mon
from app.mb import portfolio as _pf
from app.mb import routing as _routing
from app.mb.scope import get_brand, get_channel, get_workspace, scoped_query

router = APIRouter(prefix="/api", tags=["multibrand"])


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", s.lower().strip()).strip("-")[:60] or "x"


def _text_list(value, *, limit: int = 30) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(
        str(item).strip()[:120] for item in value if str(item).strip()
    ))[:limit]


def _content_strategy(value: dict | None, current: dict | None = None) -> dict:
    raw = value if isinstance(value, dict) else {}
    return {
        **(current or {}),
        "concept": str(raw.get("concept") or "").strip()[:500],
        "topics": _text_list(raw.get("topics")),
        "blocked_topics": _text_list(raw.get("blocked_topics")),
        "strict_topic_match": bool(raw.get("strict_topic_match", False)),
    }


# ---- workspaces ------------------------------------------------------- #

class NewWorkspace(BaseModel):
    name: str
    slug: str | None = None
    timezone: str = "Asia/Seoul"
    objective: str = "BALANCED"
    daily_hard_budget_usd: float = 0.0
    monthly_hard_budget_usd: float = 0.0


@router.get("/workspaces")
def list_workspaces(db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    rows = scoped_query(db, Workspace, ctx).order_by(Workspace.created_at).all() \
        if not ctx.is_system_admin else db.query(Workspace).all()
    return [{"id": w.id, "name": w.name, "slug": w.slug, "status": w.status,
             "objective": w.objective, "role": ctx.role_in(w.id)} for w in rows]


@router.post("/workspaces", status_code=201)
def create_workspace(body: NewWorkspace, db: Session = Depends(get_db),
                     ctx: AuthContext = Depends(current_user)):
    slug = _slug(body.slug or body.name)
    if db.query(Workspace).filter_by(slug=slug).first():
        raise HTTPException(409, "slug taken")
    w = Workspace(name=body.name, slug=slug, timezone=body.timezone, objective=body.objective,
                  daily_hard_budget_usd=body.daily_hard_budget_usd,
                  monthly_hard_budget_usd=body.monthly_hard_budget_usd)
    db.add(w)
    db.flush()
    # creator becomes OWNER (system admin creating on behalf still gets a membership)
    add_member(db, workspace_id=w.id, user_id=ctx.user_id, role="OWNER")
    ctx.memberships[w.id] = "OWNER"
    db.commit()   # AUDIT-P8-004 — wizard persistence: survive the request session
    return {"id": w.id, "slug": w.slug}


@router.get("/workspaces/{workspace_id}")
def get_workspace_ep(workspace_id: str, db: Session = Depends(get_db),
                     ctx: AuthContext = Depends(current_user)):
    w = get_workspace(db, ctx, workspace_id)
    problems = _budget.validate_hierarchy(db, w.id)
    return {"id": w.id, "name": w.name, "slug": w.slug, "status": w.status,
            "objective": w.objective, "timezone": w.timezone,
            "daily_hard_budget_usd": w.daily_hard_budget_usd,
            "brands": db.query(Brand).filter_by(workspace_id=w.id).count(),
            "channels": db.query(Channel).filter_by(workspace_id=w.id).count(),
            "budget_hierarchy_problems": problems}


@router.post("/workspaces/{workspace_id}/emergency-stop")
def workspace_emergency_stop(workspace_id: str, enabled: bool = Body(True, embed=True),
                             db: Session = Depends(get_db),
                             ctx: AuthContext = Depends(require_role("workspace.manage"))):
    w = get_workspace(db, ctx, workspace_id)
    w.status = "EMERGENCY_STOP" if enabled else "ACTIVE"
    return {"workspace_id": w.id, "status": w.status}


# ---- brands -------------------------------------------------------- #

class NewBrand(BaseModel):
    workspace_id: str
    name: str
    slug: str | None = None
    category: str = ""
    primary_objective: str = "BALANCED"
    daily_hard_budget_usd: float = 0.0


@router.get("/brands")
def list_brands(workspace_id: str | None = None, db: Session = Depends(get_db),
                ctx: AuthContext = Depends(current_user)):
    q = scoped_query(db, Brand, ctx, workspace_id=workspace_id)
    return [{"id": b.id, "workspace_id": b.workspace_id, "name": b.name, "slug": b.slug,
             "category": b.category, "status": b.status,
             "channels": db.query(Channel).filter_by(brand_id=b.id).count()}
            for b in q.order_by(Brand.created_at).all()]


@router.post("/brands", status_code=201)
def create_brand(body: NewBrand, db: Session = Depends(get_db),
                 ctx: AuthContext = Depends(current_user)):
    get_workspace(db, ctx, body.workspace_id)
    ctx.workspace_id = body.workspace_id
    ctx.role = ctx.role_in(body.workspace_id)
    ctx.require("brand.write")
    slug = _slug(body.slug or body.name)
    if db.query(Brand).filter_by(workspace_id=body.workspace_id, slug=slug).first():
        raise HTTPException(409, "slug taken in workspace")
    b = Brand(workspace_id=body.workspace_id, name=body.name, slug=slug, category=body.category,
              primary_objective=body.primary_objective,
              daily_hard_budget_usd=body.daily_hard_budget_usd)
    db.add(b)
    db.flush()
    db.commit()   # AUDIT-P8-004 — wizard persistence: survive the request session
    return {"id": b.id, "slug": b.slug}


@router.patch("/brands/{brand_id}")
def update_brand(brand_id: str, patch: dict = Body(...), db: Session = Depends(get_db),
                 ctx: AuthContext = Depends(current_user)):
    b = get_brand(db, ctx, brand_id)
    ctx.workspace_id = b.workspace_id
    ctx.role = ctx.role_in(b.workspace_id)
    ctx.require("brand.write")
    for k in ("name", "description", "category", "target_audience", "primary_objective",
              "status", "daily_hard_budget_usd", "monthly_hard_budget_usd",
              "profile", "voice_profile", "visual_identity", "risk_policy", "disclosure_policy"):
        if k in patch:
            setattr(b, k, patch[k])
    return {"id": b.id, "status": b.status}


@router.post("/brands/{brand_id}/pause")
def pause_brand(brand_id: str, enabled: bool = Body(True, embed=True), db: Session = Depends(get_db),
                ctx: AuthContext = Depends(current_user)):
    b = get_brand(db, ctx, brand_id)
    ctx.workspace_id = b.workspace_id
    ctx.role = ctx.role_in(b.workspace_id)
    ctx.require("brand.write")
    b.status = "PAUSED" if enabled else "ACTIVE"
    return {"id": b.id, "status": b.status}


# ---- channels ---------------------------------------------------- #

class NewChannel(BaseModel):
    brand_id: str
    name: str
    platform: str
    channel_type: str = "YOUTUBE_SHORTS"
    primary_objective: str = "BALANCED"
    daily_budget_usd: float = 0.0
    daily_max_posts: int = 2
    platform_account_id: str | None = None
    content_strategy: dict = Field(default_factory=dict)


@router.get("/channels")
def list_channels(workspace_id: str | None = None, brand_id: str | None = None,
                  db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    q = scoped_query(db, Channel, ctx, workspace_id=workspace_id)
    if brand_id:
        q = q.filter(Channel.brand_id == brand_id)
    return [{"id": c.id, "workspace_id": c.workspace_id, "brand_id": c.brand_id,
             "name": c.name, "platform": c.platform, "channel_type": c.channel_type,
             "lifecycle": c.lifecycle, "status": c.status,
             "autopilot_mode": c.autopilot_mode, "daily_budget_usd": c.daily_budget_usd,
             "target_audience": c.target_audience,
             "content_strategy": _content_strategy(c.content_strategy)}
            for c in q.order_by(Channel.created_at).all()]


@router.post("/channels", status_code=201)
def create_channel(body: NewChannel, db: Session = Depends(get_db),
                   ctx: AuthContext = Depends(current_user)):
    b = get_brand(db, ctx, body.brand_id)
    ctx.workspace_id = b.workspace_id
    ctx.role = ctx.role_in(b.workspace_id)
    ctx.require("channel.write")
    c = Channel(workspace_id=b.workspace_id, brand_id=b.id, name=body.name,
                platform=body.platform, channel_type=body.channel_type,
                primary_objective=body.primary_objective, daily_budget_usd=body.daily_budget_usd,
                daily_max_posts=body.daily_max_posts, platform_account_id=body.platform_account_id,
                content_strategy=_content_strategy(body.content_strategy),
                lifecycle="WARMUP")
    db.add(c)
    db.flush()
    return {"id": c.id, "lifecycle": c.lifecycle}


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: str, patch: dict = Body(...), db: Session = Depends(get_db),
                   ctx: AuthContext = Depends(current_user)):
    c = get_channel(db, ctx, channel_id)
    ctx.workspace_id = c.workspace_id
    ctx.role = ctx.role_in(c.workspace_id)
    for k in ("name", "target_audience", "primary_objective", "content_strategy",
              "production_profile", "daily_min_posts", "daily_max_posts", "daily_budget_usd",
              "monthly_budget_usd", "lifecycle", "status", "schedule", "brand_safety", "meta"):
        if k in patch:
            ctx.require("channel.write")
            value = (_content_strategy(patch[k], c.content_strategy)
                     if k == "content_strategy" else patch[k])
            setattr(c, k, value)
    if "autopilot_mode" in patch:
        ctx.require("autopilot.write")
        c.autopilot_mode = patch["autopilot_mode"]
    return {"id": c.id, "lifecycle": c.lifecycle, "status": c.status, "autopilot_mode": c.autopilot_mode}


@router.post("/channels/{channel_id}/pause")
def pause_channel(channel_id: str, enabled: bool = Body(True, embed=True), db: Session = Depends(get_db),
                  ctx: AuthContext = Depends(current_user)):
    c = get_channel(db, ctx, channel_id)
    ctx.workspace_id = c.workspace_id
    ctx.role = ctx.role_in(c.workspace_id)
    ctx.require("channel.write")
    c.status = "PAUSED" if enabled else "ACTIVE"
    return {"id": c.id, "status": c.status}


@router.get("/channels/{channel_id}/health")
def channel_health(channel_id: str, db: Session = Depends(get_db),
                   ctx: AuthContext = Depends(current_user)):
    c = get_channel(db, ctx, channel_id)
    snap = _cm.health_score(db, c)
    return {"channel_id": c.id, "score": snap.score, "components": snap.components,
            "scale_status": snap.scale_status, "sample_size": snap.sample_size,
            "lifecycle": snap.lifecycle}


@router.get("/channels/{channel_id}/plan")
def channel_plan(channel_id: str, db: Session = Depends(get_db),
                 ctx: AuthContext = Depends(current_user)):
    c = get_channel(db, ctx, channel_id)
    row = _cm.operating_plan(db, c)
    return {"channel_id": c.id, "plan": row.plan, "evidence": row.evidence}


@router.get("/channels/{channel_id}/monetization")
def channel_monetization(channel_id: str, db: Session = Depends(get_db),
                         ctx: AuthContext = Depends(current_user)):
    c = get_channel(db, ctx, channel_id)
    return _mon.monetization_agent(db, c)


@router.get("/channels/{channel_id}/revenue")
def channel_revenue(channel_id: str, days: int = 30, db: Session = Depends(get_db),
                    ctx: AuthContext = Depends(current_user)):
    c = get_channel(db, ctx, channel_id)
    return _mon.profit_center(db, channel_id=c.id, days=days)


# ---- content pillars ---------------------------------------------- #

@router.post("/brands/{brand_id}/pillars", status_code=201)
def add_pillar(brand_id: str, name: str = Body(..., embed=True),
               target_share: float = Body(0.25, embed=True),
               keywords: list = Body(default_factory=list, embed=True),
               db: Session = Depends(get_db), ctx: AuthContext = Depends(current_user)):
    b = get_brand(db, ctx, brand_id)
    ctx.workspace_id = b.workspace_id
    ctx.role = ctx.role_in(b.workspace_id)
    ctx.require("brand.write")
    p = ContentPillar(brand_id=b.id, workspace_id=b.workspace_id, name=name,
                      target_share=target_share, keywords=keywords)
    db.add(p)
    db.flush()
    return {"id": p.id, "name": p.name}


# ---- portfolio ------------------------------------------------- #

@router.get("/portfolio")
def portfolio(workspace_id: str, db: Session = Depends(get_db),
              ctx: AuthContext = Depends(current_user)):
    get_workspace(db, ctx, workspace_id)
    snap = _pf.snapshot(db, workspace_id)
    return {"workspace_id": workspace_id, "objective": snap.objective,
            "channels": snap.channels, "totals": snap.totals}


@router.get("/portfolio/recommendations")
def portfolio_recs(workspace_id: str, db: Session = Depends(get_db),
                   ctx: AuthContext = Depends(current_user)):
    get_workspace(db, ctx, workspace_id)
    recs = _pf.recommendations(db, workspace_id)
    return [{"channel_id": r.channel_id, "action": r.action, "detail": r.detail,
             "confidence": r.confidence, "sample_size": r.sample_size,
             "evidence": r.evidence} for r in recs]


@router.post("/portfolio/budget")
def portfolio_budget(workspace_id: str = Body(..., embed=True),
                     objective: str | None = Body(None, embed=True),
                     total_usd: float | None = Body(None, embed=True),
                     db: Session = Depends(get_db),
                     ctx: AuthContext = Depends(current_user)):
    get_workspace(db, ctx, workspace_id)
    ctx.workspace_id = workspace_id
    ctx.role = ctx.role_in(workspace_id)
    ctx.require("budget.write")
    return _pf.allocate_budget(db, workspace_id, objective=objective, total_usd=total_usd)


@router.post("/portfolio/route")
def route_topic(workspace_id: str = Body(..., embed=True), topic: str = Body(..., embed=True),
                angle: str = Body("", embed=True), db: Session = Depends(get_db),
                ctx: AuthContext = Depends(current_user)):
    get_workspace(db, ctx, workspace_id)
    d = _routing.route(db, workspace_id=workspace_id, topic=topic, angle=angle)
    return {"routed_channel_id": d.routed_channel_id, "routed_brand_id": d.routed_brand_id,
            "routed_channels": d.decision.get("routed_channels", {}),
            "cannibalization": d.cannibalization, "scores": d.scores, "decision": d.decision}
