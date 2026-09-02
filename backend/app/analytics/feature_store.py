from __future__ import annotations

import statistics

from sqlalchemy import func

from app.analytics.classify import classify_cta, classify_hook
from app.analytics.embedding import assign_cluster
from app.db.models import (
    Campaign,
    ContentFeature,
    CostLog,
    PlatformContent,
    PublishJob,
    Scene,
    Script,
)


def _cluster_index(session) -> dict[str, list[float]]:
    idx: dict[str, list[float]] = {}
    for cf in session.query(ContentFeature).filter(ContentFeature.topic_cluster.isnot(None)):
        if cf.topic_cluster not in idx and cf.topic_embedding:
            idx[cf.topic_cluster] = cf.topic_embedding
    return idx


def build_features(session, content_id: str) -> ContentFeature:
    """Extract the content-side feature vector for one PlatformContent. Idempotent
    per content_id."""
    content = session.get(PlatformContent, content_id)
    if content is None:
        raise ValueError(f"platform content {content_id} not found")
    campaign = session.get(Campaign, content.campaign_id)
    existing = session.query(ContentFeature).filter_by(content_id=content_id).first()
    row = existing or ContentFeature(content_id=content_id, campaign_id=content.campaign_id,
                                     platform=content.platform)

    scenes = session.query(Scene).filter_by(content_id=content_id).order_by(Scene.scene_order).all()
    durs = [s.estimated_duration for s in scenes if s.estimated_duration]
    vtypes = [s.visual_type for s in scenes]
    n = max(1, len(scenes))
    ratio = lambda v: round(sum(1 for x in vtypes if x == v) / n, 3)  # noqa: E731

    script = session.query(Script).filter_by(campaign_id=content.campaign_id).first()
    nat = (script.naturalness if script else {}) or {}

    job = (session.query(PublishJob)
           .filter_by(campaign_id=content.campaign_id, content_id=content_id).first())
    when = (job.scheduled_at or job.published_at) if job else None

    gen_cost = float(session.query(func.coalesce(func.sum(CostLog.amount_usd), 0.0))
                     .filter(CostLog.campaign_id == content.campaign_id).scalar() or 0.0)

    topic = (campaign.topic if campaign else "") or content.title
    cluster_id, emb = assign_cluster(topic, _cluster_index(session))

    row.campaign_id = content.campaign_id
    row.platform = content.platform
    row.content_type = content.content_type
    row.topic = topic
    row.topic_cluster = cluster_id
    row.topic_embedding = emb
    row.hook_text = content.hook or ""
    row.hook_type = classify_hook(content.hook or content.title)
    row.hook_length = len((content.hook or "").split())
    row.title = content.title or ""
    row.title_length = len(content.title or "")
    row.script_length = len((content.script or "").split())
    row.video_duration = round(sum(durs), 2) if durs else None
    row.scene_count = len(scenes)
    row.avg_scene_duration = round(statistics.fmean(durs), 3) if durs else None
    row.scene_duration_variance = round(statistics.pvariance(durs), 3) if len(durs) > 1 else 0.0
    row.ai_video_ratio = ratio("AI_VIDEO")
    row.ai_image_ratio = ratio("AI_IMAGE")
    row.stock_ratio = ratio("STOCK_VIDEO")
    row.motion_graphic_ratio = ratio("MOTION_GRAPHIC")
    row.subtitle_style = content.subtitle_style
    row.subtitle_highlight_frequency = round(
        sum(len(s.highlight_words or []) for s in scenes) / n, 3)
    row.camera_motion_diversity = len({s.camera_motion for s in scenes}) or None
    row.thumbnail_style = "mock"
    row.cta_type = classify_cta((content.payload or {}).get("cta_type"), content.cta)
    row.publish_weekday = when.weekday() if when else None
    row.publish_hour = when.hour if when else None
    row.generation_cost = round(gen_cost, 6)
    row.prompt_versions = {"script": "v1", "hook": "v1", "platform_adapt": "v1"}
    row.naturalness_score = None
    row.ai_slop_score = nat.get("ai_slop_after")
    row.visual_repetition_score = None
    row.edit_repetition_score = None

    if existing is None:
        session.add(row)
    session.flush()
    return row


def feature_hint(cf: ContentFeature) -> dict:
    """The subset the mock analytics provider uses to bake in signal."""
    return {
        "hook_type": cf.hook_type,
        "video_duration": cf.video_duration,
        "ai_video_ratio": cf.ai_video_ratio,
        "ai_slop_score": cf.ai_slop_score,
        "scene_duration_variance": cf.scene_duration_variance,
        "cta_type": cf.cta_type,
        "publish_hour": cf.publish_hour,
    }
