from __future__ import annotations

import json
import os
import re

from app.agents.media_state import MediaState
from app.config import get_settings
from app.db.base import session_scope
from app.db.models import (
    Asset,
    Campaign,
    Hook,
    PlatformContent,
    Scene,
    Script,
    Strategy,
    VerifiedFact,
)
from app.media.chart import ChartDataError, render_chart
from app.media.draw import placeholder_card
from app.media.image_motion import render_scene_clip
from app.media.images import carousel_pages, render_carousel, render_single
from app.media.media_qa import check_render
from app.media.content_qa import evaluate as content_evaluate
from app.media.compliance import check as compliance_check
from app.media.renderer import RenderPlan, RenderScene, render_video
from app.media.subtitles import (
    build_blocks,
    render_overlays,
    write_ass,
    write_renderer_json,
    write_srt,
)
from app.media.thumbnail import propose_concepts, render_concept
from app.media.visual_director import plan_visuals
from app.media.word_timing import get_alignment_provider
from app.platforms import ContentFamily, get_platform
from app.providers.errors import ProviderError
from app.providers.media import (
    get_image_provider,
    get_music_provider,
    get_stock_provider,
    get_tts_provider,
    get_video_provider,
    get_storage,
)
from app.providers.media.cache import AssetCache, asset_hash
# LLM access goes through app.agents.model_gateway (AUDIT-P8-001) — no direct provider here
from app.schemas.media import ChartSpec, VisualType
from app.services.budget import check_media_budget
from app.services.cost import log_cost
from app.services.prompts import load_prompt, register_prompt

_MEDIA_PROMPTS = ["platform_adapt", "scene_planner", "edit_decision"]
_IMG_COST = {"image": 0.0, "stock": 0.0, "tts": 0.0, "music": 0.0, "render": 0.0}
_HANGUL_RE = re.compile(r"[가-힣]")


def _contains_korean(value: object) -> bool:
    return bool(_HANGUL_RE.search(str(value or "")))


def _require_korean(data: dict, fields: tuple[str, ...], *, task: str) -> None:
    missing = [field for field in fields if not _contains_korean(data.get(field))]
    if missing:
        raise ProviderError(
            f"{task} returned non-Korean output in: {', '.join(missing)}",
            error_type="INVALID_OUTPUT",
        )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _llm_json(task: str, prompt_name: str, context: dict, *, cid: str, session, agent: str):
    """Media-pipeline LLM calls route through the Model Execution Gateway
    (AUDIT-P8-001) — same router / escalation / telemetry as the Phase 1-A agents."""
    from app.agents.model_gateway import routed_complete

    camp = session.get(Campaign, cid)
    wid = camp.workspace_id if camp else None
    prompt = load_prompt(prompt_name)
    resp = routed_complete(agent_name=agent, task=task, system=prompt.body,
                           user=json.dumps(context, ensure_ascii=False), context=context,
                           session=session, campaign_id=cid, workspace_id=wid)
    log_cost(session, campaign_id=cid, agent_name=agent, kind="LLM", provider=resp.provider,
             model=resp.model, input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
             amount_usd=0.0)
    try:
        return json.loads(resp.text)
    except ValueError as e:
        raise ProviderError(f"invalid JSON from LLM (task={task}): {e}", error_type="INVALID_OUTPUT") from e


def _usable_facts(session, cid: str) -> tuple[list[str], dict[str, list[str]]]:
    rows = session.query(VerifiedFact).filter_by(campaign_id=cid).all()
    texts, ids = [], {}
    for r in rows:
        if r.status in ("VERIFIED", "PARTIALLY_VERIFIED"):
            texts.append(r.fact)
            ids[r.fact] = r.source_ids or []
    return texts, ids


def _pick_primary_platform(platforms: list[str]) -> str:
    for p in platforms:
        try:
            spec = get_platform(p)
        except KeyError:
            continue
        if spec.family == ContentFamily.VIDEO:
            return spec.key
    return "youtube_shorts"


def _existing_scene_asset(session, scene_id: str, asset_type: str) -> Asset | None:
    a = (session.query(Asset)
         .filter_by(scene_id=scene_id, asset_type=asset_type, status="SUCCESS")
         .order_by(Asset.created_at.desc()).first())
    if a and get_storage().exists(a.storage_path):
        return a
    return None


def _record_asset(session, *, cid, content_id, scene_id, asset_type, provider, mode,
                  prompt, path, mime, width=None, height=None, duration=None, cost=0.0,
                  meta=None, hash_="") -> Asset:
    row = Asset(campaign_id=cid, content_id=content_id, scene_id=scene_id, asset_type=asset_type,
                provider=provider, provider_mode=mode, prompt=prompt[:2000], hash=hash_,
                storage_path=path, mime_type=mime, width=width, height=height, duration=duration,
                cost=cost, meta=meta or {}, status="SUCCESS")
    session.add(row)
    session.flush()
    return row


# --------------------------------------------------------------------------- #
# nodes
# --------------------------------------------------------------------------- #

def _phase1_ready(camp: Campaign) -> bool:
    """Accept the atomic text-to-media hand-off as well as manual starts."""
    return camp.status == "SUCCESS" or (
        camp.status == "RUNNING" and (camp.current_step or "").startswith("media:")
    )


def load_inputs_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    with session_scope() as session:
        camp = session.get(Campaign, cid)
        if camp is None:
            raise ValueError(f"campaign {cid} not found")
        if not _phase1_ready(camp):
            raise ProviderError(
                f"Phase 1-A not complete for campaign {cid} (status={camp.status})",
                error_type="INSUFFICIENT_RESEARCH",
            )
        for name in _MEDIA_PROMPTS:
            register_prompt(session, name)
        script = session.query(Script).filter_by(campaign_id=cid).first()
        strat = session.query(Strategy).filter_by(campaign_id=cid).first()
        top_hook = (session.query(Hook).filter_by(campaign_id=cid)
                    .order_by(Hook.rank).first())
        texts, ids = _usable_facts(session, cid)
        platforms = state.get("requested_platforms") or camp.platforms or ["youtube_shorts"]
        primary = _pick_primary_platform(platforms)
        camp.current_step = "media:load_inputs"
        return {
            "kp": camp.knowledge_pack or {},
            "usable_fact_texts": texts,
            "fact_source_ids": ids,
            "master_hook": top_hook.text if top_hook else (camp.topic or ""),
            "master_script": script.body if script else "",
            "strategy": {"angle": strat.angle, "key_message": strat.key_message} if strat else {},
            "requested_platforms": platforms,
            "primary_platform": primary,
        }


def platform_adapt_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    kp = state.get("kp", {})
    strat = state.get("strategy", {})
    out_content_id = None
    with session_scope() as session:
        existing = {c.platform: c for c in
                    session.query(PlatformContent).filter_by(campaign_id=cid).all()}
        for pkey in state["requested_platforms"]:
            try:
                spec = get_platform(pkey)
            except KeyError:
                continue
            if spec.key in existing:  # idempotent: keep prior adaptation (resume / scene-regen)
                row = existing[spec.key]
                if spec.key == state["primary_platform"]:
                    out_content_id = row.id
                continue
            data = _llm_json(
                "platform_adapt", "platform_adapt",
                {
                    "output_language": "ko-KR", "target_market": "South Korea",
                    "platform": spec.key, "content_type": spec.content_type.value,
                    "family": spec.family.value, "target_duration_s": spec.target_duration_s,
                    "aspect_ratio": spec.aspect_ratio, "visual_style": spec.visual_style,
                    "subtitle_style": spec.subtitle_style, "voice_style": spec.voice_style,
                    "music_style": spec.music_style,
                    "topic": kp.get("topic", ""), "audience": kp.get("audience", ""),
                    "key_message": strat.get("key_message", ""), "angle": strat.get("angle", ""),
                    "master_hook": state.get("master_hook", ""),
                    "master_script": state.get("master_script", ""),
                    "usable_fact_texts": state.get("usable_fact_texts", []),
                    "recent_cta_types": [],
                },
                cid=cid, session=session, agent="Platform Adaptation Agent",
            )
            _require_korean(data, ("hook", "script", "title", "caption"), task="platform_adapt")
            row = PlatformContent(
                campaign_id=cid, platform=spec.key, content_type=spec.content_type.value,
                hook=data.get("hook", ""), script=data.get("script", ""),
                cta=data.get("cta", ""), title=data.get("title", ""),
                caption=data.get("caption", ""), hashtags=data.get("hashtags", []),
                target_duration=spec.target_duration_s, aspect_ratio=spec.aspect_ratio,
                visual_style=spec.visual_style, subtitle_style=spec.subtitle_style,
                voice_style=spec.voice_style, music_style=spec.music_style,
                thumbnail_required=spec.thumbnail_required, image_count=spec.image_count,
                status="PLANNED", payload={"notes": data.get("notes", ""),
                                           "cta_type": data.get("cta_type", "")},
            )
            session.add(row)
            session.flush()
            if spec.key == state["primary_platform"]:
                out_content_id = row.id
                row.status = "RUNNING"
        camp = session.get(Campaign, cid)
        camp.current_step = "media:platform_adapt"
    return {"content_id": out_content_id}


def scene_plan_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    content_id = state["content_id"]
    s = get_settings()
    with session_scope() as session:
        content = session.get(PlatformContent, content_id)
        spec = get_platform(content.platform)
        # resume: reuse existing scenes
        existing = session.query(Scene).filter_by(content_id=content_id).order_by(Scene.scene_order).all()
        if existing:
            scenes = [_scene_to_dict(x) for x in existing]
        else:
            data = _llm_json(
                "scene_plan", "scene_planner",
                {
                    "output_language": "ko-KR", "target_market": "South Korea",
                    "platform": spec.key, "target_duration_s": spec.target_duration_s,
                    "aspect_ratio": spec.aspect_ratio, "script": content.script,
                    "usable_fact_texts": state.get("usable_fact_texts", []),
                    "fact_source_ids": state.get("fact_source_ids", {}),
                    "scene_target_seconds": s.scene_target_seconds,
                },
                cid=cid, session=session, agent="Scene Planner",
            )
            raw = data.get("scenes", [])[:14] or [{"narration": content.script[:120] or "장면",
                                                   "estimated_duration": 4.0}]
            for item in raw:
                if not _contains_korean(item.get("narration")):
                    raise ProviderError(
                        "scene_plan returned non-Korean narration",
                        error_type="INVALID_OUTPUT",
                    )
            # clamp total to platform limit
            total = sum(float(x.get("estimated_duration", 4.0)) for x in raw)
            cap = min(spec.target_duration_s or s.short_video_max_seconds, s.short_video_max_seconds)
            scale = cap / total if total > cap else 1.0
            scenes = []
            t = 0.0
            for i, x in enumerate(raw):
                dur = round(max(1.4, float(x.get("estimated_duration", 4.0)) * scale), 2)
                row = Scene(
                    campaign_id=cid, content_id=content_id, scene_order=i,
                    start_time=round(t, 2), end_time=round(t + dur, 2), estimated_duration=dur,
                    narration=x.get("narration", ""),
                    visual_description=x.get("visual_description", ""),
                    visual_prompt=x.get("visual_prompt", {}),
                    negative_prompt=x.get("visual_prompt", {}).get("negative_prompt", ""),
                    source_ids=x.get("source_ids", []),
                    highlight_words=x.get("highlight_words", []),
                    sound_effect=x.get("sound_effect", ""),
                    music_energy=x.get("music_energy", "mid"),
                    generation_status="PENDING",
                )
                session.add(row)
                session.flush()
                scenes.append(_scene_to_dict(row))
                t += dur
        # Video Studio Upgrade — deterministic creative direction (additive).
        # Enriches each scene dict with story/shot/pacing hints and stores the
        # full VideoCreativePlan on the content payload. No LLM call. Never
        # overwrites camera_motion / duration / visual_type chosen elsewhere.
        creative_plan = None
        try:
            from app.video.director import direct_video
            from app.video.memory import recent_style

            rs = recent_style(session, platform=content.platform)
            profile = (state.get("quality_profile")
                       or (content.payload or {}).get("quality_profile") or "STANDARD")
            plan = direct_video(
                platform=content.platform, content_type=content.content_type,
                scenes=scenes, profile=profile,
                style=(state.get("strategy", {}) or {}).get("style", "EXPLAINER"),
                ai_video_ratio=s.max_ai_video_ratio, recent_style=rs,
            )
            for sc in scenes:
                d = plan.scene(int(sc.get("scene_order", 0)))
                if d:
                    sc.update({
                        "story_beat": d.story_beat, "emotion_intent": d.emotion_intent,
                        "shot_size": d.shot_size, "shot_purpose": d.shot_purpose,
                        "motion_energy": d.motion_energy, "primary_focus": d.primary_focus,
                        "cinematic_motion": d.cinematic_motion,
                        "kinetic_caption": d.kinetic_caption,
                        "visual_evidence_priority": d.visual_evidence,
                    })
            content.payload = {**(content.payload or {}),
                               "creative_plan": plan.to_dict()}
            creative_plan = plan.to_dict()
        except Exception as exc:  # noqa: BLE001 — creative direction is advisory
            creative_plan = {"error": str(exc)}

        camp = session.get(Campaign, cid)
        camp.current_step = "media:scene_plan"
    return {"scenes": scenes, "creative_plan": creative_plan}


def visual_direct_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    s = get_settings()
    scenes = state["scenes"]
    with session_scope() as session:
        try:
            check_media_budget(session, cid)
        except Exception:
            remaining = 0.0
        else:
            from app.services.budget import media_spend

            remaining = max(0.0, s.media_budget_usd - media_spend(session, cid))
        choices = plan_visuals(
            scenes,
            max_ai_video_ratio=s.max_ai_video_ratio,
            video_provider_available=get_video_provider() is not None,
            stock_provider_available=get_stock_provider() is not None,
            remaining_budget_usd=remaining,
        )
        updated = []
        for sc, ch in zip(scenes, choices):
            row = session.get(Scene, sc["id"])
            row.visual_type = ch.visual_type
            if row.motion_effect != "manual":          # respect a hand-set / regenerated motion
                row.camera_motion = ch.camera_motion
                row.motion_effect = ch.reason
            motion = row.camera_motion
            sc = {**sc, "visual_type": ch.visual_type, "camera_motion": motion,
                  "downgraded_from": ch.downgraded_from}
            updated.append(sc)
        camp = session.get(Campaign, cid)
        camp.current_step = "media:visual_direct"
    return {"scenes": updated}


def gen_images_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    content_id = state["content_id"]
    scenes = state["scenes"]
    with session_scope() as session:
        content = session.get(PlatformContent, content_id)
        spec = get_platform(content.platform)
        w, h = spec.resolution()
        cache = AssetCache()
        img_provider = get_image_provider()
        stock_provider = get_stock_provider()
        kp = state.get("kp", {})
        updated = []
        for sc in scenes:
            scene_id = sc["id"]
            existing = _existing_scene_asset(session, scene_id, "image")
            if existing:
                updated.append({**sc, "still_path": existing.storage_path,
                                "still_asset_id": existing.id})
                continue
            check_media_budget(session, cid, pending_usd=0.0)
            still_dir = get_storage().campaign_dir(cid, spec.storage_dir, "images")
            out_path = os.path.join(still_dir, f"scene_{sc['scene_order']:03d}.png")
            vt = sc["visual_type"]
            prompt = _prompt_text(sc)
            provider_name, mode, cost, meta = "code", "REAL", 0.0, {}

            if vt == VisualType.CHART:
                spec_obj = _chart_from_facts(kp, sc)
                try:
                    render_chart(spec_obj, out_path, width=w, height=h)
                    meta = {"chart": spec_obj.model_dump()}
                except ChartDataError:
                    placeholder_card(w, h, title=sc["narration"][:60], watermark="").save(out_path, "PNG")
                    vt = VisualType.TEXT_CARD
            elif vt in (VisualType.TEXT_CARD, VisualType.BACKGROUND, VisualType.MOTION_GRAPHIC):
                placeholder_card(w, h, title=sc["narration"][:70],
                                 seed=prompt, watermark="").save(out_path, "PNG")
            elif vt == VisualType.STOCK_VIDEO:
                key = asset_hash(provider=stock_provider.name, model="still", prompt=prompt,
                                 settings={"w": w, "h": h}, aspect_ratio=spec.aspect_ratio)
                if not cache.get(key, out_path):
                    item = stock_provider.search(query=sc["visual_description"] or prompt,
                                                 width=w, height=h, want_video=True, out_path=out_path)
                    cache.put(key, out_path)
                    provider_name, mode = item.provider, item.provider_mode.value
                    meta = {"semantic_relevance_score": item.semantic_relevance_score}
                    log_cost(session, campaign_id=cid, agent_name="Stock", kind="STOCK",
                             provider=item.provider, amount_usd=item.cost)
                else:
                    provider_name, mode = stock_provider.name, "MOCK"
            else:  # AI_IMAGE (also AI_VIDEO downgraded here)
                key = asset_hash(provider=img_provider.name, model="img", prompt=prompt,
                                 settings={"w": w, "h": h}, aspect_ratio=spec.aspect_ratio)
                if not cache.get(key, out_path):
                    res = img_provider.generate_image(prompt=prompt, negative_prompt=sc.get("negative_prompt", ""),
                                                      width=w, height=h, out_path=out_path,
                                                      seed=sc["scene_order"])
                    cache.put(key, out_path)
                    provider_name, mode, cost = res.provider, res.provider_mode.value, res.cost
                    log_cost(session, campaign_id=cid, agent_name="Image Agent", kind="IMAGE",
                             provider=res.provider, model=res.provider_mode.value, amount_usd=res.cost)
                else:
                    provider_name, mode = img_provider.name, "MOCK"

            vt_str = vt.value if isinstance(vt, VisualType) else str(vt)
            asset = _record_asset(session, cid=cid, content_id=content_id, scene_id=scene_id,
                                  asset_type="image", provider=provider_name, mode=mode,
                                  prompt=prompt, path=out_path, mime="image/png",
                                  width=w, height=h, cost=cost, meta=meta)
            row = session.get(Scene, scene_id)
            row.asset_id = asset.id
            row.visual_type = vt_str
            row.generation_provider = provider_name
            row.generation_status = "SUCCESS"
            updated.append({**sc, "visual_type": vt_str, "still_path": out_path, "still_asset_id": asset.id})
        camp = session.get(Campaign, cid)
        camp.current_step = "media:images"
    return {"scenes": updated}


def gen_voice_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    content_id = state["content_id"]
    scenes = state["scenes"]
    with session_scope() as session:
        content = session.get(PlatformContent, content_id)
        spec = get_platform(content.platform)
        tts = get_tts_provider()
        audio_dir = get_storage().campaign_dir(cid, spec.storage_dir, "audio")
        updated = []
        t = 0.0
        for sc in scenes:
            scene_id = sc["id"]
            existing = _existing_scene_asset(session, scene_id, "audio")
            if existing:
                dur = existing.duration or sc["estimated_duration"]
                voice_path, voice_id = existing.storage_path, existing.id
            else:
                check_media_budget(session, cid)
                out_path = os.path.join(audio_dir, f"scene_{sc['scene_order']:03d}.wav")
                res = tts.synthesize(text=sc["narration"], voice_id="ko-narrator-1",
                                     language="ko", speed=1.0, emotion="neutral",
                                     style=content.voice_style or "NARRATION", out_path=out_path)
                log_cost(session, campaign_id=cid, agent_name="Voice Director", kind="TTS",
                         provider=res.provider, model=res.provider_mode.value, amount_usd=res.cost)
                asset = _record_asset(session, cid=cid, content_id=content_id, scene_id=scene_id,
                                      asset_type="audio", provider=res.provider,
                                      mode=res.provider_mode.value, prompt=sc["narration"],
                                      path=out_path, mime="audio/wav", duration=res.duration,
                                      cost=res.cost, meta=res.meta)
                dur, voice_path, voice_id = res.duration, out_path, asset.id
            row = session.get(Scene, scene_id)
            row.start_time = round(t, 3)
            row.end_time = round(t + dur, 3)
            row.estimated_duration = round(dur, 3)
            updated.append({**sc, "voice_path": voice_path, "voice_asset_id": voice_id,
                            "start_time": round(t, 3), "end_time": round(t + dur, 3),
                            "estimated_duration": round(dur, 3)})
            t += dur
        camp = session.get(Campaign, cid)
        camp.current_step = "media:voice"
    return {"scenes": updated}


def timing_subtitle_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    content_id = state["content_id"]
    scenes = state["scenes"]
    aligner = get_alignment_provider()
    all_words: list[dict] = []
    for sc in scenes:
        wt = aligner.align(text=sc["narration"], audio_path=sc.get("voice_path", ""),
                           total_duration=sc["estimated_duration"])
        for w in wt:
            all_words.append({"word": w.word, "start": round(w.start + sc["start_time"], 3),
                              "end": round(w.end + sc["start_time"], 3)})
    from app.schemas.media import WordTiming

    highlight_terms = [h for sc in scenes for h in sc.get("highlight_words", [])]
    blocks = build_blocks([WordTiming(**w) for w in all_words],
                          highlight_terms=highlight_terms, animation="pop")

    with session_scope() as session:
        content = session.get(PlatformContent, content_id)
        spec = get_platform(content.platform)
        sub_dir = get_storage().campaign_dir(cid, spec.storage_dir, "subtitles")
        srt = write_srt(blocks, os.path.join(sub_dir, "captions.srt"))
        ass = write_ass(blocks, os.path.join(sub_dir, "captions.ass"),
                        play_w=spec.resolution()[0], play_h=spec.resolution()[1])
        rjson = write_renderer_json(blocks, os.path.join(sub_dir, "captions.json"))
        session.query(Asset).filter_by(content_id=content_id, asset_type="subtitle").delete()
        session.flush()
        for path, atype in ((srt, "subtitle"), (ass, "subtitle"), (rjson, "subtitle")):
            _record_asset(session, cid=cid, content_id=content_id, scene_id=None,
                          asset_type=atype, provider="code", mode="REAL",
                          prompt="", path=path, mime="text/plain")
        total = sum(sc["estimated_duration"] for sc in scenes) or 1.0
        covered = sum(b.end - b.start for b in blocks)
        camp = session.get(Campaign, cid)
        camp.current_step = "media:subtitles"
    return {
        "word_timings": all_words,
        "subtitle_blocks": [b.model_dump() for b in blocks],
        "subtitle_coverage": round(min(1.0, covered / total), 3),
    }


def edit_decision_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    content_id = state["content_id"]
    scenes = state["scenes"]
    with session_scope() as session:
        content = session.get(PlatformContent, content_id)
        data = _llm_json(
            "edit_decision", "edit_decision",
            {"platform": content.platform, "subtitle_style": content.subtitle_style,
             "scenes": [{"scene_id": s["id"], "scene_order": s["scene_order"],
                         "estimated_duration": s["estimated_duration"],
                         "visual_type": s["visual_type"], "music_energy": s.get("music_energy", "mid"),
                         "sound_effect": s.get("sound_effect", "")} for s in scenes]},
            cid=cid, session=session, agent="Video Editor Agent",
        )
        by_id = {e["scene_id"]: e for e in data.get("edits", [])}
        updated = []
        for s in scenes:
            ed = by_id.get(s["id"], {})
            ed.setdefault("clip_end", s["estimated_duration"])
            row = session.get(Scene, s["id"])
            row.edit_decision = ed
            updated.append({**s, "edit_decision": ed})
        camp = session.get(Campaign, cid)
        camp.current_step = "media:edit_decision"
    return {"scenes": updated}


def render_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    content_id = state["content_id"]
    scenes = state["scenes"]
    s = get_settings()
    with session_scope() as session:
        content = session.get(PlatformContent, content_id)
        spec = get_platform(content.platform)
        w, h = spec.resolution()
        stg = get_storage()
        render_dir = stg.campaign_dir(cid, spec.storage_dir, "render")
        clips_dir = stg.campaign_dir(cid, spec.storage_dir, "render", "clips")

        render_scenes: list[RenderScene] = []
        for sc in scenes:
            clip = os.path.join(clips_dir, f"scene_{sc['scene_order']:03d}.mp4")
            if not stg.exists(clip):
                render_scene_clip(sc["still_path"], clip, duration=sc["estimated_duration"],
                                  width=w, height=h, fps=s.render_fps,
                                  motion=sc.get("camera_motion", "SLOW_ZOOM_IN"))
            render_scenes.append(RenderScene(clip_path=clip, voice_path=sc.get("voice_path"),
                                             duration=sc["estimated_duration"]))

        # BGM for full duration
        total = sum(sc["estimated_duration"] for sc in scenes)
        bgm_path = os.path.join(render_dir, "bgm.wav")
        music = get_music_provider()
        mres = music.get_track(mood=content.music_style or "AMBIENT", duration=total + 1, out_path=bgm_path)
        log_cost(session, campaign_id=cid, agent_name="Music", kind="MUSIC",
                 provider=mres.provider, amount_usd=mres.cost)
        session.query(Asset).filter_by(content_id=content_id, asset_type="music").delete()
        session.flush()
        _record_asset(session, cid=cid, content_id=content_id, scene_id=None, asset_type="music",
                      provider=mres.provider, mode=mres.provider_mode.value, prompt=content.music_style,
                      path=bgm_path, mime="audio/wav", duration=mres.duration, meta=mres.meta)

        # subtitle overlays
        from app.schemas.media import SubtitleBlock

        blocks = [SubtitleBlock(**b) for b in state.get("subtitle_blocks", [])]
        overlays = render_overlays(blocks, width=w, height=h,
                                   out_dir=os.path.join(render_dir, "sub"),
                                   style=content.subtitle_style)

        avg_ed = {}
        for sc in scenes:
            ed = sc.get("edit_decision", {})
            avg_ed.setdefault("music_volume", ed.get("music_volume", 0.16))
        plan = RenderPlan(
            scenes=render_scenes, width=w, height=h, fps=s.render_fps,
            bgm_path=bgm_path, music_volume=float(avg_ed.get("music_volume", 0.16)),
            overlays=overlays, work_dir=os.path.join(render_dir, "_work"),
        )
        out_mp4 = os.path.join(render_dir, "final.mp4")
        render_video(plan, out_mp4)
        log_cost(session, campaign_id=cid, agent_name="FFmpeg Renderer", kind="RENDER",
                 provider="ffmpeg", amount_usd=0.0)
        session.query(Asset).filter_by(content_id=content_id, asset_type="render").delete()
        session.flush()
        asset = _record_asset(session, cid=cid, content_id=content_id, scene_id=None,
                              asset_type="render", provider="ffmpeg", mode="REAL",
                              prompt="", path=out_mp4, mime="video/mp4",
                              width=w, height=h, duration=round(total, 2),
                              meta={"platform": spec.key})
        render_asset_id = asset.id
        camp = session.get(Campaign, cid)
        camp.current_step = "media:render"
    return {"render_path": out_mp4, "render_asset_id": render_asset_id}


def thumbnail_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    content_id = state["content_id"]
    with session_scope() as session:
        content = session.get(PlatformContent, content_id)
        spec = get_platform(content.platform)
        if not spec.thumbnail_required:
            return {"thumbnail_ids": []}
        kp = state.get("kp", {})
        strat = state.get("strategy", {})
        concepts = propose_concepts(kp.get("topic", ""), strat.get("key_message", ""),
                                    content.hook or state.get("master_hook", ""))
        thumb_dir = get_storage().campaign_dir(cid, spec.storage_dir, "thumbnail")
        session.query(Asset).filter_by(content_id=content_id, asset_type="thumbnail").delete()
        session.flush()
        ids = []
        for i, c in enumerate(concepts):
            path = os.path.join(thumb_dir, f"concept_{i + 1}.png")
            render_concept(c, path, mock=True)
            a = _record_asset(session, cid=cid, content_id=content_id, scene_id=None,
                              asset_type="thumbnail", provider="code+mock", mode="MOCK",
                              prompt=c.headline, path=path, mime="image/png",
                              meta={"concept": c.model_dump()})
            ids.append(a.id)
        camp = session.get(Campaign, cid)
        camp.current_step = "media:thumbnail"
    return {"thumbnail_ids": ids}


def platform_images_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    kp = state.get("kp", {})
    strat = state.get("strategy", {})
    facts = state.get("usable_fact_texts", [])
    ids: list[str] = []
    with session_scope() as session:
        contents = session.query(PlatformContent).filter_by(campaign_id=cid).all()
        for content in contents:
            spec = get_platform(content.platform)
            if spec.family not in (ContentFamily.IMAGE, ContentFamily.MIXED):
                continue
            w, h = spec.resolution()
            session.query(Asset).filter(
                Asset.content_id == content.id, Asset.asset_type.in_(["image", "carousel"])
            ).delete(synchronize_session=False)
            session.flush()
            base = get_storage().campaign_dir(cid, spec.storage_dir, "images")
            if spec.content_type.value == "CAROUSEL":
                pages = carousel_pages(kp.get("topic", ""), strat.get("key_message", ""),
                                       facts, content.cta)
                paths = render_carousel(pages, base, w=w, h=h)
                content.payload = {**(content.payload or {}), "pages": [p.model_dump() for p in pages]}
            else:
                count = max(1, spec.image_count)
                paths = []
                for i in range(count):
                    headline = (content.title if i == 0 else f"{kp.get('topic','')} · {i}")
                    body = facts[i - 1][:160] if 0 < i <= len(facts) else strat.get("key_message", "")
                    p = os.path.join(base, f"{spec.storage_dir}_{i + 1:02d}.png")
                    render_single(p, w=w, h=h, headline=headline or kp.get("topic", ""), body=body,
                                  seed=f"{spec.key}:{i}")
                    paths.append(p)
            for p in paths:
                a = _record_asset(session, cid=cid, content_id=content.id, scene_id=None,
                                  asset_type="carousel" if spec.content_type.value == "CAROUSEL" else "image",
                                  provider="code+mock", mode="MOCK", prompt=content.title,
                                  path=p, mime="image/png", width=w, height=h)
                ids.append(a.id)
            content.status = "PLANNED" if content.platform != state["primary_platform"] else content.status
        camp = session.get(Campaign, cid)
        camp.current_step = "media:platform_images"
    return {"platform_image_ids": ids}


def media_qa_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    content_id = state["content_id"]
    s = get_settings()
    scenes = state["scenes"]
    with session_scope() as session:
        content = session.get(PlatformContent, content_id)
        spec = get_platform(content.platform)
        w, h = spec.resolution()
        total = sum(sc["estimated_duration"] for sc in scenes)
        rep = check_render(state["render_path"], expect_duration=total, expect_w=w, expect_h=h,
                           expect_fps=s.render_fps, scene_count=len(scenes),
                           subtitle_coverage=state.get("subtitle_coverage", 0.0))
        assets = [{"id": a.id, "asset_type": a.asset_type, "provider_mode": a.provider_mode,
                   "meta": a.meta, "source_ids": None}
                  for a in session.query(Asset).filter_by(campaign_id=cid).all()]
        distinct_motions = len({sc.get("camera_motion") for sc in scenes})
        ai_video = sum(1 for sc in scenes if sc["visual_type"] == "AI_VIDEO")
        stock = sum(1 for sc in scenes if sc["visual_type"] == "STOCK_VIDEO")
        cqa = content_evaluate(
            scenes=scenes, subtitle_coverage=state.get("subtitle_coverage", 0.0),
            ai_video_ratio=ai_video / max(1, len(scenes)),
            stock_ratio=stock / max(1, len(scenes)), distinct_motions=distinct_motions,
            usable_fact_texts=state.get("usable_fact_texts", []), media_qa_passed=rep.passed,
        )
        comp = compliance_check(
            scenes=scenes, assets=assets,
            usable_fact_texts=state.get("usable_fact_texts", []),
            screen_texts=[b["text"] for b in state.get("subtitle_blocks", [])],
        )
        # Video Studio Upgrade — Video Quality Score V2 + bad-scene detection.
        # Advisory: never blocks persist (that stays media_qa + compliance).
        video_qa: dict = {}
        try:
            from app.video import quality as _vquality
            from app.video import retention as _vret
            from app.video import shots as _vshots
            from app.video import story as _vstory
            from app.video import voice_plan as _vvoice
            from app.video import audio_plan as _vaudio

            narrs = [sc.get("narration", "") for sc in scenes]
            beats, emos, arc = _vstory.build_story_arc(narrs)
            shot_plan = _vshots.plan_shots(narrs, beats, emos)
            from app.video.schema import SceneDirection

            dirs = [SceneDirection(scene_order=int(sc.get("scene_order", i)),
                                   story_beat=beats[i], emotion_intent=emos[i],
                                   shot_size=shot_plan.shot_size[i],
                                   motion_energy=shot_plan.motion_energy[i],
                                   cinematic_motion=shot_plan.cinematic_motion[i])
                    for i, sc in enumerate(scenes)]
            ret = _vret.analyze(scenes, dirs, is_short=(spec.target_duration_s or 60) <= 90)
            vplan = _vvoice.plan_voice(scenes, dirs)
            aplan = _vaudio.plan_audio(scenes, beats)

            class _SR:  # tiny shim so quality.score can read .story_arc / .first_second_strength
                story_arc = arc
            vscore = _vquality.score(
                story_report=_SR(), retention_report=ret, pacing_report=type(
                    "P", (), {"visual_refresh_flag": "OK", "visual_refresh_avg": 0.0})(),
                shot_plan=shot_plan, voice_plan=vplan, audio_plan=aplan,
                content_qa={"scores": cqa.scores}, media_qa={"passed": rep.passed},
                ai_video_ratio=ai_video / max(1, len(scenes)),
            )
            bad = _vquality.detect_bad_scenes(scenes, dirs, weak_scenes=cqa.weak_scenes,
                                              boredom_spans=ret.boredom_spans)
            from app.video import creative_qa as _vcreative
            from app.video import cuts as _vcuts
            from app.video import technical_qa as _vtech

            creq = _vcreative.evaluate(scenes, dirs, voice_plan=vplan,
                                       music_style=content.music_style or "AMBIENT")
            cut_pts = _vcuts.score_cuts(scenes, dirs)
            cut_rhythm = _vcuts.cut_rhythm_report(cut_pts)
            techq = _vtech.run(
                state.get("render_path", ""), expect_w=w, expect_h=h,
                expect_fps=s.render_fps, expect_duration=total,
                loudness_target_lufs=aplan.loudness_target_lufs,
            )
            video_qa = {
                "overall": vscore.overall, "overall_100": _vquality.score_100(vscore)["overall"],
                "passed": vscore.passed,
                "dimensions": vscore.dimensions, "weak": vscore.weak,
                "boredom_risk": ret.boredom_risk,
                "first_second_strength": ret.first_second_strength,
                "early_payoff": ret.early_payoff,
                "continuity_score": _vquality.continuity_score(shot_plan),
                "bad_scenes": [{"scene_order": b.scene_order, "flags": b.flags,
                                "strategies": b.strategies} for b in bad],
                "repair_plan": _vquality.plan_repairs(bad),
                "creative_qa": {"passed": creq.passed, "score": creq.score,
                                "checks": creq.checks, "notes": creq.notes},
                "cut_rhythm": cut_rhythm,
                "technical_qa": {"verdict": techq.verdict, "passes": techq.passes,
                                 "notes": techq.notes},
                "notes": vscore.notes + ret.notes + shot_plan.issues,
            }
        except Exception as exc:  # noqa: BLE001
            video_qa = {"error": str(exc)}

        # persist video_qa on the content payload so the Studio dashboard can read it
        try:
            content.payload = {**(content.payload or {}), "video_qa": video_qa}
        except Exception:  # noqa: BLE001
            pass
        camp = session.get(Campaign, cid)
        camp.current_step = "media:qa"
    return {
        "media_qa": {"passed": rep.passed, "checks": rep.checks, "issues": rep.issues, "facts": rep.facts},
        "content_qa": {"passed": cqa.passed, "overall": cqa.overall, "scores": cqa.scores,
                       "weak_scenes": cqa.weak_scenes, "notes": cqa.notes},
        "compliance": {"verdict": comp.verdict, "findings": comp.findings, "fix_scenes": comp.fix_scenes},
        "video_qa": video_qa,
    }


def persist_media_node(state: MediaState) -> dict:
    cid = state["campaign_id"]
    content_id = state["content_id"]
    stg = get_storage()
    media_qa = state.get("media_qa", {})
    comp = state.get("compliance", {})
    ok = media_qa.get("passed") and comp.get("verdict") != "BLOCK"
    with session_scope() as session:
        content = session.get(PlatformContent, content_id)
        spec = get_platform(content.platform)
        # copy primary render + subtitles to outputs/
        import shutil

        if state.get("render_path") and stg.exists(state["render_path"]):
            dst = stg.output_dir(cid, spec.storage_dir, "final.mp4")
            shutil.copyfile(state["render_path"], dst)
        for a in session.query(Asset).filter_by(campaign_id=cid).all():
            if a.asset_type in ("thumbnail", "image", "carousel", "subtitle") and stg.exists(a.storage_path):
                sub = get_platform(
                    session.get(PlatformContent, a.content_id).platform
                ).storage_dir if a.content_id else "master"
                dst = stg.output_dir(cid, sub, os.path.basename(a.storage_path))
                try:
                    shutil.copyfile(a.storage_path, dst)
                except OSError:
                    pass
        content.status = "SUCCESS" if ok else "FIX_REQUIRED"
        for c in session.query(PlatformContent).filter(
            PlatformContent.campaign_id == cid, PlatformContent.id != content_id
        ):
            if c.status == "RUNNING":
                c.status = "PLANNED"
        camp = session.get(Campaign, cid)
        camp.current_step = "media:done"
        camp.status = "SUCCESS" if ok else "FAILED"
        camp.error_message = None if ok else f"media QA: {comp.get('verdict')}, {media_qa.get('issues')}"
    return {"status": "SUCCESS" if ok else "FIX_REQUIRED"}


# --------------------------------------------------------------------------- #
# small utils
# --------------------------------------------------------------------------- #

def _scene_to_dict(row: Scene) -> dict:
    return {
        "id": row.id, "scene_order": row.scene_order, "narration": row.narration,
        "estimated_duration": row.estimated_duration, "start_time": row.start_time,
        "end_time": row.end_time, "visual_type": row.visual_type,
        "visual_description": row.visual_description, "visual_prompt": row.visual_prompt or {},
        "negative_prompt": row.negative_prompt, "source_ids": row.source_ids or [],
        "camera_motion": row.camera_motion, "highlight_words": row.highlight_words or [],
        "sound_effect": row.sound_effect, "music_energy": row.music_energy,
        "edit_decision": row.edit_decision or {},
    }


def _prompt_text(scene: dict) -> str:
    vp = scene.get("visual_prompt") or {}
    parts = [vp.get("subject"), vp.get("action"), vp.get("environment"), vp.get("background"),
             vp.get("composition"), vp.get("camera"), vp.get("lighting"), vp.get("style"), vp.get("mood")]
    text = ", ".join(p for p in parts if p)
    return text or scene.get("visual_description") or scene.get("narration", "")[:80]


def _chart_from_facts(kp: dict, scene: dict) -> ChartSpec:
    import re

    stats = kp.get("statistics", []) or []
    labels, values, src = [], [], scene.get("source_ids", [])
    for stt in stats:
        m = re.search(r"(\d+(?:\.\d+)?)", stt)
        if m:
            labels.append(stt.split(":")[0][:16] if ":" in stt else stt[:16])
            values.append(float(m.group(1)))
    return ChartSpec(chart_type="bar", title=scene.get("visual_description", "")[:40],
                     labels=labels[:5], values=values[:5], source_ids=src or ["kp"])
