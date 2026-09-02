from __future__ import annotations

from datetime import datetime, timezone

from app.autopilot.context import build_context
from app.autopilot.health import provider_health, run_allowed
from app.autopilot.pipeline import run_candidate_pipeline
from app.autopilot.portfolio import select_portfolio
from app.autopilot.watchdog import check_watchdog
from app.config import get_settings
from app.db.base import session_scope
from app.db.models import AutopilotRun, TopicCandidate
from app.trends.ingest import ingest_trends
from app.trends.registry import seed_trend_sources

PRODUCTION_MODES = {"SEMI_AUTO", "FULL_AUTO"}


def run_autopilot(mode: str | None = None, *, trigger: str = "manual",
                  resume_run_id: str | None = None) -> dict:
    s = get_settings()
    mode = (mode or s.autopilot_mode).upper()
    objective = s.autopilot_objective

    if mode == "OFF":
        return {"status": "OFF", "reason": "autopilot mode is OFF"}
    from app.ops.runtime_flags import emergency_stop_active, safe_mode_active

    if s.autopilot_emergency_stop or emergency_stop_active():
        return {"status": "STOPPED", "reason": "emergency stop active — resume it first"}
    if safe_mode_active() and mode in PRODUCTION_MODES:
        return {"status": "HOLD", "reason": "SAFE_MODE active — no new autopilot production"}

    # ---- create / load run ----
    with session_scope() as session:
        if resume_run_id:
            run = session.get(AutopilotRun, resume_run_id)
            if run is None:
                return {"status": "MISSING", "reason": "resume run not found"}
            run.status = "RUNNING"
        else:
            run = AutopilotRun(mode=mode, trigger=trigger, objective=objective,
                               country=s.autopilot_target_country, language=s.autopilot_language,
                               config_version=s.autopilot_config_version, stage="health")
            session.add(run)
            session.flush()
        run_id = run.id
        start_stage = run.stage

    # ---- provider health ----
    health = provider_health()
    allowed, down = run_allowed(health)
    if not allowed:
        with session_scope() as session:
            r = session.get(AutopilotRun, run_id)
            r.status = "HOLD"
            r.stage = "health"
            r.summary = {"health": health, "down": down}
            r.finished_at = datetime.now(timezone.utc)
        return {"status": "HOLD", "run_id": run_id, "reason": f"required providers down: {down}",
                "health": health}

    try:
        # ---- scan ----
        if start_stage in ("health", "scan"):
            with session_scope() as session:
                seed_trend_sources(session)
                ingest = ingest_trends(session, run_id,
                                       country=s.autopilot_target_country,
                                       language=s.autopilot_language)
                r = session.get(AutopilotRun, run_id)
                r.stage = "candidates"
                r.raw_candidates = ingest["written"]
                r.summary = {**(r.summary or {}), "ingest": ingest, "health": health}

        # ---- candidate pipeline ----
        if start_stage in ("health", "scan", "candidates"):
            with session_scope() as session:
                pipe = run_candidate_pipeline(session, run_id, objective=objective)
                r = session.get(AutopilotRun, run_id)
                r.stage = "portfolio"
                r.final_candidates = pipe["final"]
                r.summary = {**(r.summary or {}), "pipeline": pipe}

        # ---- portfolio selection ----
        with session_scope() as session:
            selected = select_portfolio(session, run_id, objective=objective,
                                        daily_budget=s.autopilot_daily_budget_usd,
                                        experiment_ratio=s.autopilot_exploration_ratio)
            selected_ids = [c.id for c in selected]
            # AUDIT-P6-001 — cap by per-channel daily capacity (no-op when no
            # channels are configured: falls back to autopilot_daily_content_max).
            capacity = {}
            if s.autopilot_respect_channel_capacity:
                from app.autopilot.capacity import portfolio_capacity

                capacity = portfolio_capacity(
                    session, workspace_id=None,
                    fallback_max=s.autopilot_daily_content_max)
                cap_n = capacity.get("max_new_campaigns", len(selected_ids))
                if cap_n < len(selected_ids):
                    selected = selected[:cap_n]
                    selected_ids = selected_ids[:cap_n]
            est_cost = round(sum(c.estimated_cost for c in selected), 4)
            r = session.get(AutopilotRun, run_id)
            r.stage = "context"
            r.selected_count = len(selected_ids)
            r.estimated_cost = est_cost
            r.summary = {**(r.summary or {}), "capacity": capacity}

        # ---- build contexts ----
        contexts = []
        with session_scope() as session:
            for cid in selected_ids:
                cand = session.get(TopicCandidate, cid)
                ctx = build_context(session, cand, objective=objective)
                contexts.append(ctx)

        # ---- SHADOW / SUGGEST_ONLY: stop here, ZERO production ----
        if mode not in PRODUCTION_MODES:
            with session_scope() as session:
                r = session.get(AutopilotRun, run_id)
                r.status = "SUCCESS"
                r.stage = "preview"
                r.finished_at = datetime.now(timezone.utc)
            return {
                "status": "SUCCESS", "run_id": run_id, "mode": mode,
                "produced": 0, "published": 0,
                "selected": [_ctx_summary(c) for c in contexts],
                "estimated_cost": est_cost,
                "note": ("SHADOW: 계산만 수행, 콘텐츠 생성/게시 0건"
                         if mode == "SHADOW" else "SUGGEST_ONLY: 사용자가 후보를 선택"),
            }

        # ---- production guard (Phase 5 §64): queue backpressure ----
        from app.ops.queue_backpressure import production_allowed

        pa_ok, pa_reason = production_allowed()
        if not pa_ok:
            with session_scope() as session:
                r = session.get(AutopilotRun, run_id)
                r.status = "HOLD"
                r.stage = "backpressure"
                r.pause_reason = pa_reason
                r.finished_at = datetime.now(timezone.utc)
            return {"status": "HOLD", "run_id": run_id, "reason": pa_reason,
                    "selected": [_ctx_summary(c) for c in contexts]}

        # ---- SEMI_AUTO / FULL_AUTO: produce via existing pipelines ----
        from app.autopilot.bridge import produce_from_context

        results = []
        for ctx in contexts:
            with session_scope() as session:
                r = session.get(AutopilotRun, run_id)
                r.stage = "produce"
            results.append(produce_from_context(ctx, run_mode=mode))

        # ---- watchdog ----
        with session_scope() as session:
            r = session.get(AutopilotRun, run_id)
            triggers = check_watchdog(session, r)
            if triggers:
                r.status = "PAUSED"
                r.pause_reason = f"watchdog: {[t['type'] for t in triggers]}"
                r.summary = {**(r.summary or {}), "watchdog": triggers}
            else:
                r.status = "SUCCESS"
            r.stage = "done"
            r.finished_at = datetime.now(timezone.utc)
            status = r.status

        return {
            "status": status, "run_id": run_id, "mode": mode,
            "produced": sum(1 for x in results if x.get("campaign_id")),
            "scheduled": sum(1 for x in results if x.get("scheduled_jobs")),
            "results": results,
            "selected": [_ctx_summary(c) for c in contexts],
            "estimated_cost": est_cost,
        }

    except Exception as e:  # noqa: BLE001
        with session_scope() as session:
            r = session.get(AutopilotRun, run_id)
            if r:
                r.status = "FAILED"
                r.error = str(e)[:2000]
                r.finished_at = datetime.now(timezone.utc)
        raise


def _ctx_summary(ctx) -> dict:
    return {
        "candidate_id": ctx.candidate_id, "topic": ctx.topic, "angle": ctx.angle,
        "opportunity_score": ctx.opportunity_score, "risk_level": ctx.risk_level,
        "production_profile": ctx.production_profile,
        "recommended_platforms": [p["platform"] for p in ctx.recommended_platforms],
        "estimated_cost": ctx.estimated_cost, "reasons": ctx.decision_reason,
        "platform_scores": ctx.platform_scores,
    }
