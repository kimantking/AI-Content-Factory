from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# list[str] settings that may arrive from an env var / .env as a bare '*', a
# comma/space list, or JSON. NoDecode stops pydantic-settings from JSON-decoding
# them first (which crashed on `TRUSTED_HOSTS=*`); `_coerce_list` then normalises.
StrList = Annotated[list[str], NoDecode]


def _as_list(v):
    """Accept a JSON array, a comma/space list, or a bare '*' from an env var /
    .env line for a list[str] field. (pydantic-settings otherwise requires JSON
    and crashes on `TRUSTED_HOSTS=*`.)"""
    if v is None or isinstance(v, (list, tuple)):
        return list(v) if v is not None else v
    s = str(v).strip()
    if not s:
        return []
    if s.startswith("["):
        import json
        try:
            return json.loads(s)
        except ValueError:
            pass
    if s == "*":
        return ["*"]
    return [x.strip() for x in s.replace(",", " ").split() if x.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("trusted_hosts", "cors_allow_origins", "ssrf_allow_hosts",
                     "autopilot_blocked_topics", "autopilot_blocked_keywords", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        return _as_list(v)

    # Infrastructure
    database_url: str = "postgresql+psycopg://acf:acf@localhost:5433/acf"
    # Sync DSN for alembic / langgraph checkpointer (psycopg3, no SQLAlchemy prefix)
    sync_database_url: str = "postgresql://acf:acf@localhost:5433/acf"
    redis_url: str = "redis://localhost:6379/0"
    checkpointer_kind: str = "postgres"   # postgres | memory

    # Providers
    llm_provider: str = "mock"          # mock | anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    # only needed for an identity-linked / workspace-scoped Anthropic Console key
    anthropic_workspace_id: str = ""
    search_provider: str = "mock"       # mock | tavily
    tavily_api_key: str | None = None

    # Mode
    mock_mode: bool = True
    run_inline: bool = False   # if true, API runs the pipeline in-process (no worker)

    # Budget guard (USD)
    campaign_budget_usd: float = 2.0
    daily_budget_usd: float = 20.0
    monthly_budget_usd: float = 300.0

    # Pipeline guards
    research_fix_max: int = 2
    fact_score_threshold: float = 0.6

    # Natural Content Engine (Design Amendment)
    max_ai_slop_score: int = 20
    default_brand: str = "default"
    natural_writing_enabled: bool = True

    # Phase 1-B — Media Production
    image_provider: str = "mock"        # mock | google
    video_provider: str = "mock"        # mock | google
    tts_provider: str = "mock"          # mock | elevenlabs
    stock_provider: str = "mock"
    music_provider: str = "mock"
    image_api_key: str | None = None
    video_api_key: str | None = None
    tts_api_key: str | None = None
    stock_api_key: str | None = None

    # Phase 11 — Google AI (image / video) + ElevenLabs (voice). Backend only —
    # never exposed to the frontend. Model names live HERE, not in adapter code.
    google_api_key: str | None = None          # canonical: GOOGLE_API_KEY
    google_ai_enabled: bool = False
    google_api_base: str = "https://generativelanguage.googleapis.com"
    google_image_model: str = "imagen-3.0-generate-002"   # verify current model before enabling
    google_video_model: str = "veo-3.0-generate-001"      # Veo — verify current model before enabling
    google_timeout_seconds: int = 60
    google_video_max_wait_seconds: int = 600              # bounded synchronous poll for a Veo operation
    google_video_poll_seconds: int = 10
    elevenlabs_api_key: str | None = None      # canonical: ELEVENLABS_API_KEY
    elevenlabs_api_base: str = "https://api.elevenlabs.io"
    elevenlabs_model: str = "eleven_multilingual_v2"
    elevenlabs_voice_id: str = ""              # required when tts_provider=elevenlabs (no invented default)
    elevenlabs_timeout_seconds: int = 60

    storage_root: str = "storage"
    output_root: str = "outputs"
    asset_cache_enabled: bool = True

    max_ai_video_ratio: float = 0.0    # 0 in mock; raise when a real VideoProvider is wired
    scene_target_seconds: float = 4.5
    short_video_max_seconds: int = 60
    render_fps: int = 30
    media_budget_usd: float = 1.5      # per-campaign media sub-budget

    alignment_provider: str = "estimator"   # estimator | whisperx

    # Phase 2 — Publishing
    dry_run: bool = True                      # SAFE DEFAULT: never calls a real publish API
    publish_mode: str = "MANUAL"             # MANUAL | SEMI_AUTO | FULL_AUTO | AUTOPILOT
    platform_client: str = "mock"            # mock | http  (http = real; needs credentials)
    acf_master_key: str | None = None        # base64 Fernet key; NOT stored in DB
    naver_browser_assist: bool = False
    publish_default_timezone: str = "Asia/Seoul"
    oauth_redirect_base: str = "http://localhost:8000"
    oauth_client_json: str = "{}"            # {"youtube": {"client_id": "...", "client_secret": "..."}, ...}
    x_cost_per_post_usd: float | None = None  # None => PRICING_UNKNOWN
    webhook_secret: str = "dev-webhook-secret"
    publish_poll_schedule: list[int] = [5, 10, 20, 30, 60]
    publish_poll_max_seconds: int = 900
    publish_max_attempts: int = 5

    # Phase 3 — Analytics / Learning / Memory / Revenue
    analytics_client: str = "mock"           # mock | http (real; needs credentials)
    default_objective: str = "BALANCED"      # VIEWS|WATCH_TIME|RETENTION|ENGAGEMENT|FOLLOWERS|REVENUE|PROFIT|BRAND|BALANCED
    objective_config_version: str = "v1"
    exploration_ratio: float = 0.2           # 80/20 exploit/explore, configurable
    max_memory_items: int = 8
    max_memory_tokens: int = 1200
    memory_min_moderate_sample: int = 6
    memory_min_strong_sample: int = 12
    memory_injection_enabled: bool = True
    learning_enabled: bool = True
    analytics_currency: str = "KRW"

    # Phase 4 — Trend Intelligence / AUTOPILOT
    autopilot_mode: str = "SUGGEST_ONLY"       # OFF | SHADOW | SUGGEST_ONLY | SEMI_AUTO | FULL_AUTO
    trend_client: str = "mock"                 # mock | http
    autopilot_target_country: str = "KR"
    autopilot_language: str = "ko"
    autopilot_objective: str = "BALANCED"
    autopilot_daily_content_min: int = 1
    autopilot_daily_content_max: int = 5
    autopilot_daily_budget_usd: float = 3.0
    autopilot_monthly_budget_usd: float = 60.0
    autopilot_trend_reserve_ratio: float = 0.2
    autopilot_min_opportunity_score: float = 55.0
    autopilot_min_fact_score: float = 0.6
    autopilot_min_naturalness_score: float = 0.0
    autopilot_min_originality_score: float = 0.0
    autopilot_max_risk_level: str = "MEDIUM"   # LOW|MEDIUM|HIGH|CRITICAL — max auto-publishable without human approval
    autopilot_exploration_ratio: float = 0.2
    autopilot_respect_channel_capacity: bool = True   # cap a run by per-channel daily slots (AUDIT-P6-001)
    autopilot_stage1_keep: int = 30
    autopilot_stage2_keep: int = 10
    opportunity_formula_version: str = "opportunity_formula_v1"
    autopilot_config_version: str = "v1"
    autopilot_publish_all_platforms: bool = False
    autopilot_platform_opportunity_threshold: float = 55.0

    # Phase 5 — Production / Security / Backup / Monitoring
    app_env: str = "development"              # development | test | staging | production
    app_version: str = "1.0.0"               # Production V1.0 (Phase 10 release)
    release_name: str = "AI Content Factory v1.0.0"
    secret_key: str | None = None            # session/CSRF signing (required in production)
    trusted_hosts: StrList = ["*"]
    cors_allow_origins: StrList = ["*"]
    public_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    oauth_callback_base_url: str = "http://localhost:8000"
    max_request_bytes: int = 25_000_000
    max_upload_bytes: int = 300_000_000
    rate_limit_enabled: bool = True
    ssrf_allow_hosts: StrList = []
    ssrf_enforce: bool = True

    backup_dir: str = "backups"
    backup_retention_days: int = 7
    backup_destination: str = "local"        # local | s3
    backup_encryption_key: str | None = None
    pg_dump_cmd: str | None = None           # explicit path; else PATH; else docker exec
    pg_restore_cmd: str | None = None
    postgres_container: str = "ai-content-factory-postgres-1"

    render_max_concurrency: int = 2
    provider_breaker_threshold: int = 5
    provider_breaker_cooldown_s: int = 120
    provider_breaker_probes: int = 1
    queue_backpressure_warn: int = 50
    queue_backpressure_hold: int = 200
    worker_heartbeat_stale_s: int = 90
    job_lease_seconds: int = 1800
    disk_warn_pct: float = 85.0
    disk_critical_pct: float = 95.0
    cost_anomaly_factor: float = 4.0        # spend > factor x rolling median => anomaly

    otel_enabled: bool = False
    sentry_dsn: str | None = None
    log_level: str = "INFO"

    # Phase 6 — auth / multi-tenant
    auth_enforce: bool = False          # force auth on /api/ops,/api/admin,/admin outside production
    bootstrap_admin_email: str | None = None   # created on first boot if set
    bootstrap_admin_key: str | None = None     # raw API key for that admin (dev/local only)

    # Phase 7 — content governance
    policy_max_age_days: int = 120       # older policy registry -> POLICY_STALE
    governance_enforce: bool = True      # publisher / autopilot honour governance decisions
    originality_block_threshold: float = 0.9   # >= => DUPLICATE
    originality_review_threshold: float = 0.78  # >= => HIGH_SIMILARITY / review

    # Cross-Phase Intelligence Upgrade — URL learning / dataset / prompt distillation
    url_learning_enabled: bool = True
    browser_fetch_enabled: bool = False       # Playwright adapter is opt-in (D67 review)
    auto_promote_learned_prompts: bool = False  # learned prompts never auto-reach production
    learning_single_source_max_status: str = "EXPERIMENTAL"  # 1 reference can't exceed this
    max_learning_items_per_job: int = 100
    max_daily_learning_items: int = 500
    max_learning_cost_usd: float = 5.0
    max_reference_bytes: int = 5_000_000
    learning_deep_analysis_top_k: int = 20     # cheap-first: only deep-analyse the best K
    max_learned_skills: int = 8               # prompt composer context budget
    max_prompt_blueprints: int = 5
    max_learned_context_tokens: int = 1500
    prompt_composer_enabled: bool = True      # merge learned skills/blueprints into agent prompts in the production path (AUDIT-P8-006)
    learning_min_blueprint_sample: int = 3    # multi-reference floor for CANDIDATE+
    reference_similarity_fix_threshold: float = 0.82  # gen vs reference -> FIX_REQUIRED

    # Phase 8 — Local AI (Ollama) + Model Router + Cost Optimization
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "gemma3:4b"
    allow_cloud_fallback: bool = True         # false => LOCAL_ONLY: never call a cloud model
    local_model_max_concurrency: int = 2
    local_model_timeout_seconds: int = 120
    model_router_enabled: bool = True
    quality_preset: str = "balanced"          # fast | balanced | high | max
    ui_mode_default: str = "BEGINNER"         # BEGINNER | STANDARD | EXPERT
    model_routing_min_sample: int = 8         # below this, don't auto-shift routing policy
    model_routing_autotune_enabled: bool = True  # once telemetry has >= min_sample, let select() prefer proven engines (AUDIT-P8-005)
    content_library_page_size: int = 30

    @property
    def local_only(self) -> bool:
        return not self.allow_cloud_fallback

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def debug(self) -> bool:
        return self.app_env in ("development", "test")

    # HARD RULES — the AI cannot change these (enforced in code, not prompt)
    autopilot_daily_hard_budget_usd: float = 5.0
    autopilot_monthly_hard_budget_usd: float = 120.0
    autopilot_daily_post_limit: int = 12
    autopilot_blocked_topics: StrList = []
    autopilot_blocked_keywords: StrList = []
    autopilot_min_compliance_score: float = 0.7
    autopilot_emergency_stop: bool = False

    @property
    def llm_is_mock(self) -> bool:
        return self.llm_provider == "mock" or self.mock_mode or not self.anthropic_api_key

    @property
    def search_is_mock(self) -> bool:
        return self.search_provider == "mock" or self.mock_mode or not self.tavily_api_key

    def media_provider_key(self, kind: str) -> str | None:
        """The API key for the configured media provider of `kind`, resolving the
        canonical per-vendor name first, then the generic `<kind>_api_key`."""
        prov = getattr(self, f"{kind}_provider", "mock")
        if prov == "google":
            return self.google_api_key or getattr(self, f"{kind}_api_key", None)
        if prov == "elevenlabs":
            return self.elevenlabs_api_key or getattr(self, f"{kind}_api_key", None)
        return getattr(self, f"{kind}_api_key", None)

    def media_provider_is_mock(self, kind: str) -> bool:
        prov = getattr(self, f"{kind}_provider", "mock")
        return self.mock_mode or prov == "mock" or not self.media_provider_key(kind)


@lru_cache
def get_settings() -> Settings:
    return Settings()
