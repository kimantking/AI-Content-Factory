from __future__ import annotations

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db.base import engine, session_scope

_DOMAIN_TABLES = [
    # Phase 11 — provider credential vault
    "provider_credentials",
    # Cross-Phase Intelligence Upgrade — child tables first
    "model_routing_events", "model_performance",
    "reference_chunks", "reference_analysis", "reference_feedback", "dataset_records",
    "prompt_blueprint_evidence", "prompt_blueprints", "learned_skill_notes",
    "creative_recipes", "reference_sources", "learning_jobs", "learning_collections",
    "campaign_platform_selections", "platform_presets",
    # Phase 7 (content governance) — child tables first; registries re-seeded per test
    "rights_evidence", "asset_lineage", "rights_manifests", "policy_snapshots",
    "governance_events", "governance_cases", "claim_provenance", "similarity_results",
    "content_fingerprints", "copyright_claims", "correction_cases", "rights_ledger",
    "policy_registry", "license_registry",
    # Phase 6 (multi-brand) — child tables first
    "asset_usage_history", "content_routing_decisions", "portfolio_reports",
    "channel_reports", "portfolio_decisions", "portfolio_snapshots",
    "channel_operating_plans", "channel_health_snapshots", "budget_reservations",
    "budget_allocations", "affiliate_links", "affiliate_programs", "sponsor_deals",
    "offers", "content_pillars", "channels", "brands", "workspace_members",
    "workspaces", "users",
    # Phase 5
    "dead_letters", "audit_log", "ops_alerts", "backup_manifests", "job_leases",
    "workers", "config_change_log", "runtime_settings",
    # Phase 4
    "topic_rejections", "autopilot_decisions", "autopilot_config_versions",
    "topic_candidates", "raw_trend_events", "autopilot_runs", "trend_sources",
    # Phase 3
    "period_reports", "daily_learning_runs", "experiment_results", "experiments",
    "content_recipes", "learning_memories", "cost_allocations", "revenue_entries",
    "performance_scores", "content_features", "analytics_jobs", "analytics_snapshots",
    "metric_catalog",
    # Phase 2
    "publication_events", "publish_audits", "publications", "publish_jobs",
    "oauth_states", "platform_accounts",
    # Phase 1-B
    "media_tasks", "assets", "scenes", "platform_contents",
    # Phase 1-A
    "cost_logs", "errors", "agent_runs", "hooks", "scripts", "strategies",
    "verified_facts", "research_sources", "prompt_versions", "campaigns",
]


@pytest.fixture(autouse=True)
def _clean_db():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(_DOMAIN_TABLES) + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(autouse=True)
def _base_settings():
    s = get_settings()
    saved = {k: getattr(s, k) for k in (
        "app_env",
        "mock_mode", "llm_provider", "search_provider", "run_inline",
        "anthropic_api_key", "anthropic_model", "anthropic_workspace_id", "tavily_api_key",
        "image_provider", "video_provider", "tts_provider",
        "image_api_key", "video_api_key", "tts_api_key",
        "google_api_key", "google_ai_enabled", "google_image_model", "google_video_model",
        "google_video_max_wait_seconds", "google_video_poll_seconds",
        "elevenlabs_api_key", "elevenlabs_model", "elevenlabs_voice_id",
        "checkpointer_kind", "fact_score_threshold", "research_fix_max",
        "campaign_budget_usd", "daily_budget_usd", "monthly_budget_usd",
        "max_ai_slop_score", "natural_writing_enabled",
        "media_budget_usd", "max_ai_video_ratio", "alignment_provider",
        "storage_root", "output_root", "asset_cache_enabled",
        "dry_run", "publish_mode", "platform_client", "naver_browser_assist",
        "x_cost_per_post_usd", "webhook_secret", "publish_max_attempts",
        "analytics_client", "default_objective", "objective_config_version",
        "exploration_ratio", "max_memory_items", "max_memory_tokens",
        "memory_min_moderate_sample", "memory_min_strong_sample",
        "memory_injection_enabled", "learning_enabled", "analytics_currency",
        "governance_enforce", "policy_max_age_days", "autopilot_respect_channel_capacity",
        "url_learning_enabled", "browser_fetch_enabled", "auto_promote_learned_prompts",
        "max_learning_items_per_job", "max_daily_learning_items", "max_learning_cost_usd",
        "max_reference_bytes", "learning_deep_analysis_top_k", "max_learned_skills",
        "max_prompt_blueprints", "max_learned_context_tokens",
        "learning_min_blueprint_sample", "reference_similarity_fix_threshold",
        "learning_single_source_max_status", "prompt_composer_enabled",
        "ollama_enabled", "ollama_base_url", "ollama_default_model", "allow_cloud_fallback",
        "local_model_max_concurrency", "local_model_timeout_seconds", "model_router_enabled",
        "quality_preset", "ui_mode_default", "model_routing_min_sample",
        "model_routing_autotune_enabled", "content_library_page_size",
    )}
    # A developer's real .env must never change test results (config-capability
    # and support-snapshot assertions key off these). Pin a clean baseline; tests
    # that need a provider key / a non-test env set it explicitly.
    s.app_env = "test"
    s.anthropic_api_key = ""
    s.anthropic_workspace_id = ""
    s.tavily_api_key = ""
    s.google_api_key = ""
    s.elevenlabs_api_key = ""
    s.mock_mode = True
    s.llm_provider = "mock"
    s.search_provider = "mock"
    s.run_inline = True
    s.checkpointer_kind = "memory"
    # Tests must be deterministic and fast: never route to a real local model.
    # (The running app legitimately uses Ollama; the test suite must not, or the
    #  router sends standard-tier tasks to gemma3:4b — slow + non-deterministic +
    #  concurrent telemetry-table deadlocks.)  Tests that specifically exercise
    #  Ollama re-enable it locally.
    s.ollama_enabled = False
    s.allow_cloud_fallback = True
    yield s
    for k, v in saved.items():
        setattr(s, k, v)


@pytest.fixture(autouse=True)
def _clear_faults():
    from app.providers.faults import faults

    faults.clear()
    yield
    faults.clear()


@pytest.fixture
def make_campaign():
    import uuid

    from app.db.models import Campaign

    created: list[str] = []

    def _make(topic="테스트 주제", goal="BALANCED", platforms=None):
        cid = str(uuid.uuid4())
        with session_scope() as s:
            s.add(Campaign(id=cid, topic=topic, audience_goal=goal,
                           platforms=platforms or ["YouTube"], status="WAITING"))
        created.append(cid)
        return cid

    return _make
