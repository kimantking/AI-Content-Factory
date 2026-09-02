"""Phase 11 — provider credential vault (additive).

One encrypted API key per (provider, workspace). The ciphertext uses the SAME
Fernet box as SNS OAuth tokens (`app.publishing.crypto`), keyed by
`ACF_MASTER_KEY`. Nothing here is ever returned to the frontend except `last4`
and the health metadata. `workspace_id == ""` is the instance-level credential
(single-tenant / dev), used as the fallback when a workspace has none of its own.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# providers that authenticate with a bare API key (Ollama has no key)
KEYED_PROVIDERS = ("anthropic", "tavily", "google", "elevenlabs")


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"

    provider: Mapped[str] = mapped_column(String(24), primary_key=True)
    # "" == instance-level; a real workspace id scopes the credential to it
    workspace_id: Mapped[str] = mapped_column(String(36), primary_key=True, default="")

    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last4: Mapped[str] = mapped_column(String(8), default="")
    # NOT_CONFIGURED | CONFIGURED | CONNECTED | AUTH_FAILED | RATE_LIMITED |
    # BILLING | MODEL_UNAVAILABLE | QUOTA | BLOCKED | ERROR
    status: Mapped[str] = mapped_column(String(20), default="NOT_CONFIGURED")

    configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str] = mapped_column(String(48), default="")

    # non-secret extras only: probe detail, capability checks, chosen voice, etc.
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str] = mapped_column(String(64), default="user")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


P11_TABLES = ["provider_credentials"]
