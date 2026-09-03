from __future__ import annotations

from dataclasses import dataclass, field

from app.publishing.base import PublishError, PublishErrorType

# Offline fake of a generic social platform. Stateful so we can exercise
# container/processing/verify/reconcile flows without touching real accounts.
# A mock result is NEVER reported as a real API pass (callers set provider_mode).

SCENARIOS = {
    "SUCCESS", "PROCESSING", "RATE_LIMIT", "TOKEN_EXPIRED",
    "INVALID_MEDIA", "POLICY_REJECTED", "NETWORK_TIMEOUT",
}


@dataclass
class _Post:
    remote_post_id: str
    url: str
    state: str = "PUBLISHED"
    idempotency_key: str = ""
    thread_ids: list[str] = field(default_factory=list)


@dataclass
class _Container:
    container_id: str
    payload: dict
    idempotency_key: str
    polls_left: int = 0
    published_post_id: str | None = None


class MockPlatformAPI:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._containers: dict[str, _Container] = {}
        self._posts: dict[str, _Post] = {}
        self._by_key: dict[str, _Post] = {}
        self._uploads: dict[str, dict] = {}
        self._scenario: dict[str, str] = {}
        self._seq = 0

    # -- test control -------------------------------------------------------
    def set_scenario(self, scenario: str, platform: str = "*") -> None:
        assert scenario in SCENARIOS, scenario
        self._scenario[platform] = scenario

    def clear_scenarios(self) -> None:
        self._scenario.clear()

    def _sc(self, platform: str) -> str:
        return self._scenario.get(platform) or self._scenario.get("*") or "SUCCESS"

    def _raise_for(self, platform: str) -> None:
        sc = self._sc(platform)
        if sc == "RATE_LIMIT":
            raise PublishError(PublishErrorType.RATE_LIMIT, "mock rate limited", retry_after=1.0)
        if sc == "TOKEN_EXPIRED":
            raise PublishError(PublishErrorType.TOKEN_EXPIRED, "mock token expired")
        if sc == "INVALID_MEDIA":
            raise PublishError(PublishErrorType.MEDIA_INVALID, "mock rejected media spec")
        if sc == "POLICY_REJECTED":
            raise PublishError(PublishErrorType.POLICY_REJECTION, "mock policy rejection")
        if sc == "NETWORK_TIMEOUT":
            raise PublishError(PublishErrorType.NETWORK_TIMEOUT, "mock network timeout")

    def _id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq:06d}"

    # -- resumable upload -------------------------------------------------
    def start_upload(self, platform: str, total_bytes: int) -> str:
        self._raise_for(platform)
        sid = self._id("upl")
        self._uploads[sid] = {"received": 0, "total": total_bytes, "complete": False}
        return sid

    def put_chunk(self, session_id: str, nbytes: int) -> dict:
        u = self._uploads[session_id]
        u["received"] = min(u["total"], u["received"] + nbytes)
        u["complete"] = u["received"] >= u["total"]
        return dict(u)

    def upload_status(self, session_id: str) -> dict:
        return dict(self._uploads.get(session_id, {"received": 0, "total": 0, "complete": False}))

    # -- container flow ------------------------------------------------
    def create_container(self, platform: str, idempotency_key: str, payload: dict) -> str:
        self._raise_for(platform)
        if idempotency_key and idempotency_key in self._by_key:
            # reconciliation: a prior attempt already produced a post
            post = self._by_key[idempotency_key]
            cid = self._id("cnt")
            self._containers[cid] = _Container(cid, payload, idempotency_key, 0, post.remote_post_id)
            return cid
        cid = self._id("cnt")
        polls = 2 if self._sc(platform) == "PROCESSING" else 0
        self._containers[cid] = _Container(cid, payload, idempotency_key, polls)
        return cid

    def container_status(self, container_id: str) -> str:
        c = self._containers[container_id]
        if c.polls_left > 0:
            c.polls_left -= 1
            return "IN_PROGRESS"
        return "FINISHED"

    def publish_container(self, platform: str, container_id: str, idempotency_key: str) -> _Post:
        self._raise_for(platform)
        c = self._containers[container_id]
        if c.published_post_id:                       # already published (reconcile path)
            return self._posts[c.published_post_id]
        if idempotency_key and idempotency_key in self._by_key:
            return self._by_key[idempotency_key]
        pid = self._id(f"{platform}_post")
        post = _Post(remote_post_id=pid,
                     url=f"https://mock.{platform}.example/p/{pid}",
                     idempotency_key=idempotency_key)
        self._posts[pid] = post
        if idempotency_key:
            self._by_key[idempotency_key] = post
        c.published_post_id = pid
        return post

    def reply(self, platform: str, parent_post_id: str, idempotency_key: str) -> _Post:
        self._raise_for(platform)
        if idempotency_key and idempotency_key in self._by_key:
            return self._by_key[idempotency_key]
        pid = self._id(f"{platform}_reply")
        post = _Post(remote_post_id=pid,
                     url=f"https://mock.{platform}.example/p/{pid}",
                     idempotency_key=idempotency_key)
        self._posts[pid] = post
        if idempotency_key:
            self._by_key[idempotency_key] = post
        return post

    # -- verification / reconciliation --------------------------------
    def get_post(self, remote_post_id: str) -> dict | None:
        p = self._posts.get(remote_post_id)
        if not p:
            return None
        return {"id": p.remote_post_id, "url": p.url, "state": p.state}

    def find_by_idempotency(self, idempotency_key: str) -> dict | None:
        p = self._by_key.get(idempotency_key)
        if not p:
            return None
        return {"id": p.remote_post_id, "url": p.url, "state": p.state}


mock_platform = MockPlatformAPI()
