from __future__ import annotations

import hashlib
import hmac

from app.config import get_settings
from app.db.models import Publication, PublicationEvent

# Only platforms whose official API offers webhooks (see capabilities.json).
WEBHOOK_PLATFORMS = {"meta", "instagram", "facebook", "threads", "tiktok"}


def verify_signature(raw_body: bytes, signature_header: str | None, *, secret: str | None = None) -> bool:
    if not signature_header:
        return False
    secret = secret or get_settings().webhook_secret
    sig = signature_header.split("=", 1)[-1].strip()
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def sign(raw_body: bytes, *, secret: str | None = None) -> str:
    secret = secret or get_settings().webhook_secret
    return "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def apply_webhook(session, platform: str, payload: dict, *, verified: bool) -> dict:
    """Advance a Publication ONLY when the signature verified. An unsigned / forged
    webhook can never move a job to PUBLISHED."""
    if not verified:
        return {"accepted": False, "reason": "signature verification failed"}
    remote_id = payload.get("remote_post_id") or payload.get("media_id") or payload.get("id")
    new_state = str(payload.get("status", "")).upper()
    if not remote_id or not new_state:
        return {"accepted": False, "reason": "missing remote_post_id / status"}
    pub = session.query(Publication).filter_by(remote_post_id=str(remote_id)).first()
    if not pub:
        return {"accepted": True, "matched": False}

    # replay / duplicate-delivery protection: a signed webhook delivered twice
    # must not fire the same state transition twice.
    dup = (session.query(PublicationEvent)
           .filter_by(publish_job_id=pub.publish_job_id, event=f"WEBHOOK_{new_state}")
           .first())
    if dup is not None:
        return {"accepted": True, "matched": True, "duplicate": True,
                "publication_id": pub.id, "status": pub.status}

    pub.status = new_state
    session.add(PublicationEvent(publish_job_id=pub.publish_job_id, publication_id=pub.id,
                                 event=f"WEBHOOK_{new_state}", detail={"platform": platform}))
    session.flush()
    return {"accepted": True, "matched": True, "publication_id": pub.id, "status": new_state}
