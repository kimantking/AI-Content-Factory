from __future__ import annotations

from app.publishing.publishers import BasePublisher


def verify_published(publisher: BasePublisher, remote_post_id: str | None) -> tuple[bool, str | None, dict]:
    """A 200 is not enough — confirm the platform's final state + a permalink."""
    if not remote_post_id:
        return False, None, {"reason": "no remote_post_id to verify"}
    post = publisher.get_remote_post(remote_post_id)
    if not post:
        return False, None, {"reason": "remote post not found on platform"}
    state = str(post.get("state", "")).upper()
    url = post.get("url")
    ok = state in ("PUBLISHED", "LIVE", "ACTIVE") and bool(url)
    return ok, url, {"remote_state": state}
