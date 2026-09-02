from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class PublishStatus(str, Enum):
    DRAFT = "DRAFT"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    READY = "READY"
    SCHEDULED = "SCHEDULED"
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    PUBLISHING = "PUBLISHING"
    VERIFYING = "VERIFYING"
    PUBLISHED = "PUBLISHED"
    PARTIALLY_PUBLISHED = "PARTIALLY_PUBLISHED"
    WAITING_PLATFORM_ACTION = "WAITING_PLATFORM_ACTION"
    WAITING_USER_ACTION = "WAITING_USER_ACTION"
    RETRY = "RETRY"
    FAILED = "FAILED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    NOT_SUPPORTED = "NOT_SUPPORTED"


# in-flight states that must never trigger a fresh publish (idempotency)
ACTIVE_OR_DONE = {
    PublishStatus.UPLOADING, PublishStatus.PROCESSING, PublishStatus.PUBLISHING,
    PublishStatus.VERIFYING, PublishStatus.PUBLISHED, PublishStatus.PARTIALLY_PUBLISHED,
}


class PublishErrorType(str, Enum):
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    AUTH_REVOKED = "AUTH_REVOKED"
    PERMISSION_MISSING = "PERMISSION_MISSING"
    MEDIA_INVALID = "MEDIA_INVALID"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    QUOTA = "QUOTA"
    POLICY_REJECTION = "POLICY_REJECTION"
    DUPLICATE = "DUPLICATE"
    PLATFORM_UNAVAILABLE = "PLATFORM_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


# error -> recovery action (engine consults this)
RECOVERY = {
    PublishErrorType.NETWORK_TIMEOUT: "RETRY",
    PublishErrorType.RATE_LIMIT: "RETRY_AFTER",
    PublishErrorType.TOKEN_EXPIRED: "REFRESH_RETRY",
    PublishErrorType.AUTH_REVOKED: "REAUTH_REQUIRED",
    PublishErrorType.PERMISSION_MISSING: "BLOCK",
    PublishErrorType.MEDIA_INVALID: "NORMALIZE_RETRY",
    PublishErrorType.PROCESSING_ERROR: "RETRY",
    PublishErrorType.QUOTA: "RETRY_AFTER",
    PublishErrorType.POLICY_REJECTION: "BLOCKED",
    PublishErrorType.DUPLICATE: "DO_NOT_REPOST",
    PublishErrorType.PLATFORM_UNAVAILABLE: "RETRY_AFTER",
    PublishErrorType.UNKNOWN: "RETRY",
}
TERMINAL_RECOVERY = {"BLOCK", "BLOCKED", "REAUTH_REQUIRED", "DO_NOT_REPOST"}


class PublishError(Exception):
    def __init__(self, error_type: PublishErrorType, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.retry_after = retry_after


class PublisherError(PublishError):
    """alias kept for symmetry with other layers"""


class MediaRef(BaseModel):
    asset_id: str
    path: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    kind: str = "video"          # video | image | thumbnail


class PublishRequest(BaseModel):
    job_id: str
    platform: str
    account_id: str
    content_type: str
    title: str = ""
    description: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    privacy: str = "PRIVATE"
    media: list[MediaRef] = Field(default_factory=list)
    thumbnail: MediaRef | None = None
    platform_settings: dict = Field(default_factory=dict)
    ai_generated: bool = True
    idempotency_key: str = ""
    dry_run: bool = False


class PublishResult(BaseModel):
    status: PublishStatus
    remote_post_id: str | None = None
    remote_container_id: str | None = None
    remote_publish_id: str | None = None
    remote_url: str | None = None
    provider_mode: str = "MOCK"           # REAL | MOCK
    thread_remote_ids: list[str] = Field(default_factory=list)
    needs: str | None = None              # e.g. "APP_REVIEW", "CREDENTIAL", "USER_ACTION"
    detail: dict = Field(default_factory=dict)


class CapabilityCheck(BaseModel):
    can_publish: bool
    publishing_status: str
    integration_status: str
    reasons: list[str] = Field(default_factory=list)


@runtime_checkable
class PublisherProvider(Protocol):
    platform: str
    provider_mode: str

    def get_capabilities(self) -> CapabilityCheck: ...
    def validate_account(self, account: dict) -> tuple[bool, list[str]]: ...
    def validate_media(self, req: PublishRequest) -> tuple[bool, list[str]]: ...
    def prepare_publish(self, req: PublishRequest) -> PublishRequest: ...
    def publish(self, req: PublishRequest) -> PublishResult: ...
    def get_publish_status(self, req: PublishRequest, handle: dict) -> PublishResult: ...
    def get_remote_post(self, remote_post_id: str) -> dict | None: ...
    def cancel_if_supported(self, req: PublishRequest, handle: dict) -> bool: ...
