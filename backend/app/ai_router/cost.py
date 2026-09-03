"""Cost Estimator — expected cost BEFORE a run starts.

Categories: LLM / Search / Image / Video / TTS / Stock / Storage / Other. Each
line carries a state: KNOWN (verified price), ESTIMATED (public list price), or
UNKNOWN (no verified price — shown as such, never a fake number). Local (Ollama)
LLM work is API cost 0 but labelled "LOCAL PROCESSING", not "free".

Shared assets (master script, master video, thumbnail) are counted once, not per
platform (spec §25).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai_router.pricing import USD_KRW
from app.ai_router.router import ModelRouter
from app.config import get_settings

# agent-tasks a single campaign runs once (master), with a rough token budget
_MASTER_TASKS = [
    ("Research Agent", "research_summary", 1200, 500),
    ("Fact Checker", "fact_extract", 900, 350),
    ("Strategist", "strategy", 1400, 500),
    ("Hook Agent", "hook", 900, 300),
    ("Script Agent", "final_script", 2000, 1400),
    ("Video Director", "creative_direction", 1600, 900),
]
# per selected media platform (adaptation)
_PER_PLATFORM_TASKS = [("Platform Adapter", "platform_adapt", 900, 500)]

_MEDIA_PLATFORMS = {"youtube_shorts", "youtube_long", "tiktok", "instagram_reel",
                    "instagram_feed", "instagram_carousel", "facebook_reel", "naver_clip"}
_QUALITY_MEDIA_UNITS = {"fast": 4, "balanced": 6, "high": 9, "max": 12}   # AI image/video units


def _llm_line(db: Session | None, router: ModelRouter, tasks, *, quality: str,
              privacy: str, budget_state: str) -> dict:
    total_usd = 0.0
    any_unknown = any_local = False
    per_task = []
    for agent, task, itok, otok in tasks:
        d = router.select(agent_type=agent, task_type=task, quality_required=quality,
                          privacy=privacy, budget_state=budget_state,
                          context_size=itok, est_output_tokens=otok)
        c = d.estimated_cost or {"usd": None, "state": "UNKNOWN"}
        per_task.append({"agent": agent, "task": task, "model": d.selected_model,
                         "tier": d.tier, "usd": c.get("usd"), "state": c.get("state")})
        if c.get("state") == "UNKNOWN":
            any_unknown = True
        elif c.get("usd") is not None:
            total_usd += c["usd"]
            if c.get("local"):
                any_local = True
    state = "UNKNOWN" if any_unknown else ("KNOWN" if all(
        t["state"] == "KNOWN" for t in per_task) else "ESTIMATED")
    return {"usd": round(total_usd, 4), "state": state, "local_processing": any_local,
            "tasks": per_task}


def estimate_campaign_cost(db: Session | None, *, selection: dict, quality_preset: str | None = None,
                           execution_mode: str = "CREATE_AND_LEARN",
                           reference_count: int = 0, privacy: str = "normal",
                           budget_state: str = "ok") -> dict:
    s = get_settings()
    quality = quality_preset or s.quality_preset
    router = ModelRouter()

    from app.intel.platform_selection import normalize_selection

    canon = normalize_selection(selection or {})
    gen_platforms = [p for p, cts in canon.items() if any(m != "DISABLED" for m in cts.values())]
    pub_platforms = [p for p, cts in canon.items()
                     if any(m == "GENERATE_AND_PUBLISH" for m in cts.values())]
    media_platforms = [p for p in gen_platforms if p in _MEDIA_PLATFORMS]
    learn_only = execution_mode in ("LEARN_ONLY", "REFERENCE_ONLY")

    categories: dict[str, dict] = {}

    # ---- LLM (master runs once; per-platform adaptation) ----
    if not learn_only:
        master = _llm_line(db, router, _MASTER_TASKS, quality=quality, privacy=privacy,
                           budget_state=budget_state)
        adapt = _llm_line(db, router, _PER_PLATFORM_TASKS * max(1, len(gen_platforms)),
                          quality=quality, privacy=privacy, budget_state=budget_state) \
            if gen_platforms else {"usd": 0.0, "state": "KNOWN", "tasks": []}
        llm_usd = (master["usd"] or 0) + (adapt["usd"] or 0)
        llm_state = "UNKNOWN" if "UNKNOWN" in (master["state"], adapt["state"]) else \
            ("KNOWN" if master["state"] == adapt["state"] == "KNOWN" else "ESTIMATED")
        categories["LLM"] = {"usd": round(llm_usd, 4), "state": llm_state,
                             "local_processing": master["local_processing"],
                             "detail": {"master": master["tasks"], "adaptation_platforms": len(gen_platforms)}}
    # ---- reference learning LLM (cheap-first) ----
    if execution_mode in ("CREATE_AND_LEARN", "LEARN_ONLY") and reference_count:
        # stage-1/2 are local/deterministic; only the top-K get a standard call
        deep = min(reference_count, s.learning_deep_analysis_top_k)
        d = router.select(agent_type="Dataset Analyzer", task_type="reference_analysis",
                          quality_required=quality, privacy=privacy, context_size=1500,
                          est_output_tokens=600)
        c = d.estimated_cost or {}
        per = c.get("usd")
        categories["LLM_learning"] = {
            "usd": round((per or 0) * deep, 4) if per is not None else None,
            "state": c.get("state", "UNKNOWN"), "local_processing": bool(c.get("local")),
            "detail": {"references": reference_count, "deep_analysed": deep,
                       "per_reference_model": d.selected_model}}

    # ---- Search ----
    if not learn_only:
        categories["Search"] = ({"usd": 0.0, "state": "KNOWN", "local_processing": False}
                                if s.search_is_mock
                                else {"usd": None, "state": "UNKNOWN"})

    # ---- Media (Image / Video / TTS / Stock) — providers are MOCK -> UNKNOWN $ ----
    media_known = not s.media_provider_is_mock("video")
    if media_platforms and not learn_only:
        units = _QUALITY_MEDIA_UNITS.get(quality, 6)
        for cat in ("Image", "Video", "TTS", "Stock"):
            categories[cat] = {
                "usd": (0.0 if media_known else None),
                "state": ("ESTIMATED" if media_known else "UNKNOWN"),
                "local_processing": False,
                "detail": {"shared_master": 1, "platform_variants": len(media_platforms),
                           "quality_units": units}}
    # ---- Storage / Other ----
    categories["Storage"] = {"usd": 0.0, "state": "KNOWN", "local_processing": True,
                             "detail": {"note": "local disk"}}

    knowns = [v["usd"] for v in categories.values() if v.get("state") in ("KNOWN", "ESTIMATED") and v.get("usd") is not None]
    any_unknown = any(v.get("state") == "UNKNOWN" for v in categories.values())
    total_usd = round(sum(knowns), 4)
    return {
        "quality_preset": quality,
        "execution_mode": execution_mode,
        "generate_platforms": gen_platforms,
        "publish_platforms": pub_platforms,
        "categories": categories,
        "total_known_usd": total_usd,
        "total_known_krw": round(total_usd * USD_KRW),
        "has_unknown": any_unknown,
        "total_state": "UNKNOWN" if any_unknown else ("KNOWN" if all(
            v.get("state") == "KNOWN" for v in categories.values()) else "ESTIMATED"),
        "note": ("일부 항목은 실제 단가가 확인되지 않아 UNKNOWN으로 표시됩니다. "
                 "로컬(Ollama) 작업은 API 비용 0이지만 컴퓨터 자원을 사용합니다."),
    }
