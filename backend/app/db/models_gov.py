"""Phase 7 — Copyright / Rights / Policy / Originality / AI-Disclosure / Governance.

Additive. Registered on the shared Base via app.db.models.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import _now, _uuid

# ----- vocabularies ---------------------------------------------------- #

RIGHTS_STATUS = (
    "VERIFIED", "VERIFIED_WITH_ATTRIBUTION", "LICENSED", "USER_OWNED",
    "AI_GENERATED_VERIFIED", "PUBLIC_DOMAIN_VERIFIED", "RESTRICTED", "EXPIRED",
    "UNKNOWN_RIGHTS", "DISPUTED", "BLOCKED",
)
SOURCE_TYPE = (
    "USER_UPLOAD", "AI_GENERATED", "STOCK_LICENSED", "PUBLIC_DOMAIN",
    "OFFICIAL_SOURCE", "SCREENSHOT", "SOCIAL_POST", "NEWS_MEDIA",
    "MUSIC_LIBRARY", "SFX_LIBRARY", "GENERATED_AUDIO", "GENERATED_VIDEO",
    "GENERATED_IMAGE", "INTERNAL_ASSET", "UNKNOWN",
)
GOVERNANCE_STATE = (
    "PENDING", "SCANNING", "PASS", "PASS_WITH_REQUIREMENTS", "FIX_REQUIRED",
    "HUMAN_REVIEW", "BLOCKED", "RESOLVED",
)
GOVERNANCE_DECISION = (
    "ALLOW", "ALLOW_WITH_DISCLOSURE", "ALLOW_WITH_ATTRIBUTION", "FIX_REQUIRED",
    "HUMAN_REVIEW", "BLOCK",
)
SEVERITY = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")
DISCLOSURE_DECISION = (
    "NOT_REQUIRED", "RECOMMENDED", "REQUIRED", "PLATFORM_FIELD_REQUIRED", "HUMAN_REVIEW",
)
ORIGINALITY_LEVEL = (
    "ORIGINAL", "SIMILAR", "HIGH_SIMILARITY", "DUPLICATE",
    "REUSED_WITH_TRANSFORMATION", "REVIEW_REQUIRED",
)


class RightsLedger(Base):
    __tablename__ = "rights_ledger"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36))
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source_type: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    source_provider: Mapped[str] = mapped_column(String(80), default="")
    source_reference: Mapped[str] = mapped_column(Text, default="")
    source_url_or_id: Mapped[str] = mapped_column(Text, default="")
    original_creator: Mapped[str] = mapped_column(String(200), default="")
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # license
    license_type: Mapped[str] = mapped_column(String(48), default="UNKNOWN")
    license_version: Mapped[str] = mapped_column(String(24), default="")
    license_reference: Mapped[str] = mapped_column(Text, default="")
    commercial_use: Mapped[str] = mapped_column(String(12), default="UNKNOWN")  # YES|NO|UNKNOWN
    derivative_use: Mapped[str] = mapped_column(String(12), default="UNKNOWN")
    redistribution_allowed: Mapped[str] = mapped_column(String(12), default="UNKNOWN")
    attribution_required: Mapped[bool] = mapped_column(default=False)
    attribution_text: Mapped[str] = mapped_column(Text, default="")
    territory: Mapped[str] = mapped_column(String(32), default="WORLDWIDE")
    expiration_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    usage_restrictions: Mapped[list] = mapped_column(JSON, default=list)
    platform_restrictions: Mapped[dict] = mapped_column(JSON, default=dict)  # {platform: allowed}
    # provenance
    ai_generated: Mapped[bool] = mapped_column(default=False)
    human_generated: Mapped[bool] = mapped_column(default=False)
    user_supplied: Mapped[bool] = mapped_column(default=False)
    model_generated: Mapped[bool] = mapped_column(default=False)
    model_provider: Mapped[str] = mapped_column(String(80), default="")
    model_name: Mapped[str] = mapped_column(String(120), default="")
    model_terms_reference: Mapped[str] = mapped_column(Text, default="")
    # identity / consent
    person_status: Mapped[str] = mapped_column(String(24), default="")  # REAL_PERSON|FICTIONAL_PERSON|SYNTHETIC_PERSON|UNKNOWN_PERSON
    consent_status: Mapped[str] = mapped_column(String(20), default="")  # UNKNOWN|USER_CONFIRMED|DOCUMENTED|NOT_REQUIRED|REVOKED
    voice_kind: Mapped[str] = mapped_column(String(20), default="")  # GENERIC_TTS|LICENSED_VOICE|USER_VOICE|CLONED_VOICE|UNKNOWN
    watermark_detected: Mapped[bool] = mapped_column(default=False)
    trademark_flag: Mapped[str] = mapped_column(String(28), default="")
    content_id_risk: Mapped[bool] = mapped_column(default=False)
    rights_status: Mapped[str] = mapped_column(String(28), default="UNKNOWN_RIGHTS", index=True)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=_now)


class RightsEvidence(Base):
    __tablename__ = "rights_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    rights_id: Mapped[str | None] = mapped_column(String(36), index=True)
    type: Mapped[str] = mapped_column(String(40))  # LICENSE_PAGE|RECEIPT|PROVIDER_TERMS|MODEL_TERMS|CONSENT|SCREENSHOT_META|...
    provider: Mapped[str] = mapped_column(String(80), default="")
    reference: Mapped[str] = mapped_column(Text, default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    verified_by: Mapped[str] = mapped_column(String(80), default="system")
    status: Mapped[str] = mapped_column(String(16), default="RECORDED")


class AssetLineage(Base):
    __tablename__ = "asset_lineage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_asset_id: Mapped[str | None] = mapped_column(String(36), index=True)
    operation: Mapped[str] = mapped_column(String(40))  # ACQUIRE|SMART_CROP|COLOR_MATCH|SUBTITLE_OVERLAY|RENDER|...
    tool: Mapped[str] = mapped_column(String(60), default="")
    version: Mapped[str] = mapped_column(String(24), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RightsManifest(Base):
    __tablename__ = "rights_manifests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36))
    channel_id: Mapped[str | None] = mapped_column(String(36))
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), index=True)
    publication_id: Mapped[str | None] = mapped_column(String(36), index=True)
    render_asset_id: Mapped[str | None] = mapped_column(String(36))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)     # full JSON (§6)
    governance_decision: Mapped[str] = mapped_column(String(28), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    is_published_snapshot: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LicenseRegistry(Base):
    __tablename__ = "license_registry"
    __table_args__ = (UniqueConstraint("key", name="uq_license_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(64), index=True)      # CC0|CC-BY|CC-BY-SA|PUBLIC_DOMAIN|COMMERCIAL_STOCK|USER_OWNED|...
    kind: Mapped[str] = mapped_column(String(20), default="CONTENT_LICENSE")  # SOFTWARE|MODEL|CONTENT|ASSET
    name: Mapped[str] = mapped_column(String(120), default="")
    commercial_allowed: Mapped[str] = mapped_column(String(12), default="UNKNOWN")
    derivative_allowed: Mapped[str] = mapped_column(String(12), default="UNKNOWN")
    attribution_required: Mapped[bool] = mapped_column(default=False)
    share_alike: Mapped[bool] = mapped_column(default=False)
    territory_limit: Mapped[str] = mapped_column(String(32), default="")
    expiration_possible: Mapped[bool] = mapped_column(default=False)
    redistribution_limit: Mapped[str] = mapped_column(String(24), default="")
    reference: Mapped[str] = mapped_column(Text, default="")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    notes: Mapped[str] = mapped_column(Text, default="")


class PolicyRegistry(Base):
    __tablename__ = "policy_registry"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    policy_type: Mapped[str] = mapped_column(String(40))  # CONTENT|MONETIZATION|SYNTHETIC_MEDIA|COPYRIGHT|SPAM|ADVERTISING|API_PUBLISHING
    policy_version_or_reference: Mapped[str] = mapped_column(String(120), default="")
    content_type: Mapped[str] = mapped_column(String(24), default="ANY")
    rule_id: Mapped[str] = mapped_column(String(60), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(12), default="MEDIUM")
    automatable: Mapped[bool] = mapped_column(default=True)
    requires_disclosure: Mapped[bool] = mapped_column(default=False)
    requires_human_review: Mapped[bool] = mapped_column(default=False)
    action: Mapped[str] = mapped_column(String(28), default="FIX_REQUIRED")  # ALLOW|DISCLOSE|FIX_REQUIRED|HUMAN_REVIEW|BLOCK
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    source_reference: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")


class PolicySnapshot(Base):
    __tablename__ = "policy_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    publication_id: Mapped[str | None] = mapped_column(String(36), index=True)
    platform: Mapped[str] = mapped_column(String(40))
    policy_snapshot_version: Mapped[str] = mapped_column(String(60))
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    stale: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GovernanceCase(Base):
    __tablename__ = "governance_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36))
    channel_id: Mapped[str | None] = mapped_column(String(36))
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), index=True)
    asset_id: Mapped[str | None] = mapped_column(String(36))
    case_type: Mapped[str] = mapped_column(String(40))  # RIGHTS|POLICY|ORIGINALITY|DISCLOSURE|LIKENESS|TRADEMARK|CLAIM|PRIVACY|COMMERCIAL
    severity: Mapped[str] = mapped_column(String(12), default="MEDIUM")
    state: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    decision: Mapped[str] = mapped_column(String(28), default="")
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    policy_version: Mapped[str] = mapped_column(String(60), default="")
    hard_block: Mapped[bool] = mapped_column(default=False)   # cannot be UI-overridden
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by: Mapped[str | None] = mapped_column(String(80), default=None)
    resolution_note: Mapped[str] = mapped_column(Text, default="")


class GovernanceEvent(Base):
    __tablename__ = "governance_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # STATE_CHANGE|DECISION|OVERRIDE|ASSET_REPLACED|DISCLOSURE_ADDED|BLOCKED|UNBLOCKED|CLAIM|CORRECTION
    from_state: Mapped[str] = mapped_column(String(24), default="")
    to_state: Mapped[str] = mapped_column(String(24), default="")
    actor: Mapped[str] = mapped_column(String(80), default="system")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimProvenance(Base):
    __tablename__ = "claim_provenance"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), index=True)
    fact_id: Mapped[str | None] = mapped_column(String(36))
    claim_text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(24), default="FACT")  # FACT|STATISTIC|QUOTE|OPINION|PREDICTION|ESTIMATE|ALLEGATION|ADVERTISEMENT|PERSONAL_EXPERIENCE
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    script_location: Mapped[str] = mapped_column(String(80), default="")
    scene_ids: Mapped[list] = mapped_column(JSON, default=list)
    visual_ids: Mapped[list] = mapped_column(JSON, default=list)
    numeric_value: Mapped[str | None] = mapped_column(String(40), default=None)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    event_status: Mapped[str] = mapped_column(String(16), default="")  # DEVELOPING|CONFIRMED|CORRECTED|RETRACTED|UNKNOWN
    status: Mapped[str] = mapped_column(String(20), default="OK")      # OK|UNSUPPORTED|MISMATCH|STALE|OPINION_AS_FACT
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentFingerprint(Base):
    __tablename__ = "content_fingerprints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36))
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), index=True)
    asset_id: Mapped[str | None] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # SCRIPT|HOOK|TITLE|THUMBNAIL|IMAGE|VIDEO|AUDIO|FINAL_VIDEO|SCENE_SEQ|STRUCTURE
    exact_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    norm_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    phash: Mapped[str] = mapped_column(String(64), default="")            # hex perceptual hash
    sim_vector: Mapped[list] = mapped_column(JSON, default=list)          # cheap embedding
    tokens: Mapped[list] = mapped_column(JSON, default=list)             # for n-gram / jaccard
    profile: Mapped[dict] = mapped_column(JSON, default=dict)            # duration/scene-count/etc
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SimilarityResult(Base):
    __tablename__ = "similarity_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    content_id: Mapped[str | None] = mapped_column(String(36), index=True)
    against_content_id: Mapped[str | None] = mapped_column(String(36))
    against_brand_id: Mapped[str | None] = mapped_column(String(36))
    against_channel_id: Mapped[str | None] = mapped_column(String(36))
    scope: Mapped[str] = mapped_column(String(20), default="INTERNAL")  # INTERNAL|CROSS_BRAND|CROSS_CHANNEL|CROSS_PLATFORM|EXTERNAL
    level: Mapped[str] = mapped_column(String(28), default="ORIGINAL")
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)         # per-dim similarity
    transformation_score: Mapped[float] = mapped_column(Float, default=0.0)
    reused_content_risk: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CopyrightClaim(Base):
    __tablename__ = "copyright_claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    platform: Mapped[str] = mapped_column(String(40))
    publication_id: Mapped[str | None] = mapped_column(String(36), index=True)
    asset_id: Mapped[str | None] = mapped_column(String(36))
    claimant: Mapped[str] = mapped_column(String(200), default="")
    claimed_segment: Mapped[str] = mapped_column(String(80), default="")
    claim_type: Mapped[str] = mapped_column(String(40), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(24), default="RECEIVED")  # RECEIVED|REVIEWING|CONTENT_HELD|ACTION_REQUIRED|RESOLVED
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    dispute_package: Mapped[dict] = mapped_column(JSON, default=dict)


class CorrectionCase(Base):
    __tablename__ = "correction_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), index=True)
    publication_id: Mapped[str | None] = mapped_column(String(36), index=True)
    trigger: Mapped[str] = mapped_column(String(40), default="")  # SOURCE_RETRACTED|FACT_CORRECTED|LICENSE_EXPIRED|CLAIM
    status: Mapped[str] = mapped_column(String(24), default="REVIEW")  # REVIEW|UPDATE_METADATA|POST_CORRECTION|UNPUBLISH_RECOMMENDED|NO_ACTION
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


GOV_TABLES = [
    "license_registry", "policy_registry", "rights_ledger", "rights_evidence",
    "asset_lineage", "rights_manifests", "policy_snapshots", "governance_cases",
    "governance_events", "claim_provenance", "content_fingerprints",
    "similarity_results", "copyright_claims", "correction_cases",
]

GOV_ALTERS = [
    # governance state on the content row (NULLABLE)
    "ALTER TABLE platform_contents ADD COLUMN IF NOT EXISTS governance_state VARCHAR(24)",
    "ALTER TABLE platform_contents ADD COLUMN IF NOT EXISTS governance_decision VARCHAR(28)",
    "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS governance_decision VARCHAR(28)",
    "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS disclosure_meta JSON",
    "CREATE INDEX IF NOT EXISTS ix_rights_ledger_asset ON rights_ledger (asset_id)",
    "CREATE INDEX IF NOT EXISTS ix_fingerprint_lookup ON content_fingerprints (kind, norm_hash)",
    "CREATE INDEX IF NOT EXISTS ix_gov_case_state ON governance_cases (workspace_id, state, severity)",
]
