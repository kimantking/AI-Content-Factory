from __future__ import annotations

from app.config import get_settings
from app.publishing.base import (
    CapabilityCheck,
    PublishRequest,
    PublishResult,
    PublishStatus,
)
from app.publishing.capabilities import (
    PublishingStatus,
    get_capability,
    resolve_publishing_platform,
)
from app.publishing.client import PublisherClient, get_client

_CHUNK = 5 * 1024 * 1024


class BasePublisher:
    platform = "generic"

    def __init__(self, account: dict, client: PublisherClient | None = None):
        self.account = account or {}
        self.client = client or get_client()
        self.cap = get_capability(self.platform)

    # -- capabilities / validation ------------------------------------
    def get_capabilities(self) -> CapabilityCheck:
        reasons: list[str] = []
        can = self.cap.auto_publish_possible
        if not can:
            reasons.append(f"publishing_status={self.cap.publishing_status}")
        if self.client.mode == "REAL":
            reasons.append("real client selected — credentials + verified adapter required")
            can = False
        return CapabilityCheck(
            can_publish=can,
            publishing_status=self.cap.publishing_status,
            integration_status=self.cap.implementation_status,
            reasons=reasons,
        )

    def validate_account(self, account: dict) -> tuple[bool, list[str]]:
        errs: list[str] = []
        if account.get("connection_status") != "CONNECTED":
            errs.append("account not CONNECTED")
        req = (self.cap.account_requirement or "").lower()
        atype = (account.get("account_type") or "").lower()
        if "professional" in req or "business" in req or "creator" in req:
            if atype not in ("business", "creator", "professional"):
                errs.append(f"account_type '{atype}' does not meet: {self.cap.account_requirement}")
        if "page" in req and "page" not in atype and self.platform in ("facebook",):
            errs.append("Facebook publishing requires a Page account")
        return (not errs, errs)

    def validate_media(self, req: PublishRequest) -> tuple[bool, list[str]]:
        errs: list[str] = []
        ct = req.content_type.upper()
        vids = [m for m in req.media if m.kind == "video"]
        imgs = [m for m in req.media if m.kind == "image"]
        if ct in ("SHORT_VIDEO", "LONG_VIDEO", "VIDEO_PIN"):
            if not vids:
                errs.append("video content_type but no video asset")
            elif not self.cap.video_supported:
                errs.append(f"{self.platform} does not support video via official API")
        if ct in ("SINGLE_IMAGE", "IMAGE_PIN"):
            if not imgs:
                errs.append("image content_type but no image asset")
            elif not self.cap.image_supported:
                errs.append(f"{self.platform} does not support image via official API")
        if ct == "CAROUSEL":
            if not self.cap.carousel_supported:
                errs.append(f"{self.platform} has no carousel support")
            if len(req.media) < 2:
                errs.append("carousel needs >= 2 media items")
        for m in req.media:
            from app.providers.media import get_storage

            if not get_storage().exists(m.path):
                errs.append(f"media file missing: {m.asset_id}")
        return (not errs, errs)

    def prepare_publish(self, req: PublishRequest) -> PublishRequest:
        return req

    # -- publish ----------------------------------------------------
    def _blocked_result(self, needs: str, detail: dict | None = None) -> PublishResult:
        return PublishResult(status=PublishStatus.WAITING_PLATFORM_ACTION, provider_mode=self.client.mode,
                             needs=needs, detail=detail or {})

    def _resumable_upload(self, req: PublishRequest) -> None:
        vids = [m for m in req.media if m.kind == "video"]
        if not vids:
            return
        import os

        size = max(_CHUNK, int(os.path.getsize(vids[0].path)))
        sid = self.client.start_upload(self.platform, size)
        sent = 0
        while sent < size:
            st = self.client.put_chunk(sid, _CHUNK)
            sent = st["received"]
            if st.get("complete"):
                break

    def _container_publish(self, req: PublishRequest, payload: dict) -> PublishResult:
        cid = self.client.create_container(self.platform, req.idempotency_key, payload)
        status = self.client.container_status(cid)
        if status != "FINISHED":
            return PublishResult(status=PublishStatus.PROCESSING, remote_container_id=cid,
                                 provider_mode=self.client.mode)
        post = self.client.publish_container(self.platform, cid, req.idempotency_key)
        return PublishResult(status=PublishStatus.VERIFYING, remote_container_id=cid,
                             remote_post_id=post["id"], remote_url=post.get("url"),
                             provider_mode=self.client.mode)

    def publish(self, req: PublishRequest) -> PublishResult:
        cap = self.get_capabilities()
        if not cap.can_publish:
            if self.cap.publishing_status == PublishingStatus.APP_REVIEW_REQUIRED.value:
                return self._blocked_result("APP_REVIEW", {"reasons": cap.reasons})
            if self.cap.publishing_status == PublishingStatus.MANUAL_ONLY.value:
                return PublishResult(status=PublishStatus.WAITING_USER_ACTION,
                                     provider_mode=self.client.mode, needs="MANUAL",
                                     detail={"reasons": cap.reasons})
            if self.cap.publishing_status == PublishingStatus.NOT_SUPPORTED.value:
                return PublishResult(status=PublishStatus.NOT_SUPPORTED,
                                     provider_mode=self.client.mode,
                                     detail={"reason": "no verified official publishing API"})
            return self._blocked_result("CREDENTIAL", {"reasons": cap.reasons})

        if req.dry_run:
            return PublishResult(status=PublishStatus.READY, provider_mode=self.client.mode,
                                 detail={"dry_run": True, "payload": self._payload(req)})
        return self._do_publish(req)

    def _payload(self, req: PublishRequest) -> dict:
        return {"title": req.title, "caption": req.caption, "privacy": req.privacy,
                "hashtags": req.hashtags, "media": [m.asset_id for m in req.media],
                "ai_generated": req.ai_generated}

    def _do_publish(self, req: PublishRequest) -> PublishResult:
        self._resumable_upload(req)
        return self._container_publish(req, self._payload(req))

    def get_publish_status(self, req: PublishRequest, handle: dict) -> PublishResult:
        cid = handle.get("remote_container_id")
        if not cid:
            return self._do_publish(req)
        status = self.client.container_status(cid)
        if status != "FINISHED":
            return PublishResult(status=PublishStatus.PROCESSING, remote_container_id=cid,
                                 provider_mode=self.client.mode)
        post = self.client.publish_container(self.platform, cid, req.idempotency_key)
        return PublishResult(status=PublishStatus.VERIFYING, remote_container_id=cid,
                             remote_post_id=post["id"], remote_url=post.get("url"),
                             provider_mode=self.client.mode)

    def get_remote_post(self, remote_post_id: str) -> dict | None:
        return self.client.get_post(remote_post_id)

    def cancel_if_supported(self, req: PublishRequest, handle: dict) -> bool:
        return False


# --------------------------------------------------------------------------- #
# concrete publishers
# --------------------------------------------------------------------------- #

class YouTubePublisher(BasePublisher):
    platform = "youtube"

    def _do_publish(self, req: PublishRequest) -> PublishResult:
        self._resumable_upload(req)                      # official resumable protocol
        payload = {**self._payload(req), "kind": "youtube_video",
                   "tags": req.hashtags, "description": req.description}
        cid = self.client.create_container(self.platform, req.idempotency_key, payload)
        post = self.client.publish_container(self.platform, cid, req.idempotency_key)
        return PublishResult(status=PublishStatus.VERIFYING, remote_container_id=cid,
                             remote_post_id=post["id"], remote_url=post.get("url"),
                             provider_mode=self.client.mode,
                             detail={"note": "unverified API projects upload as PRIVATE until audit"})


class TikTokPublisher(BasePublisher):
    platform = "tiktok"

    def publish(self, req: PublishRequest) -> PublishResult:
        if req.dry_run:
            return PublishResult(status=PublishStatus.READY, provider_mode=self.client.mode,
                                 detail={"dry_run": True, "flow": self._flow(req)})
        # Direct Post needs an audited app -> gate it
        if self._flow(req) == "direct_post":
            return self._blocked_result("APP_REVIEW",
                                        {"reason": "video.publish (Direct Post) requires app audit"})
        # video.upload flow: lands in the user's TikTok inbox for confirmation
        self._resumable_upload(req)
        cid = self.client.create_container(self.platform, req.idempotency_key,
                                           {**self._payload(req), "flow": "inbox_upload"})
        return PublishResult(status=PublishStatus.WAITING_USER_ACTION, remote_container_id=cid,
                             provider_mode=self.client.mode, needs="USER_ACTION",
                             detail={"reason": "content sent to TikTok inbox; user confirms in-app"})

    def _flow(self, req: PublishRequest) -> str:
        return "direct_post" if req.platform_settings.get("direct_post") else "inbox_upload"


class InstagramPublisher(BasePublisher):
    platform = "instagram"

    def _do_publish(self, req: PublishRequest) -> PublishResult:
        if req.content_type.upper() == "CAROUSEL":
            children = []
            for m in req.media:
                ck = f"{req.idempotency_key}:child:{m.asset_id}"
                child = self.client.create_container(self.platform, ck,
                                                    {"kind": "child", "asset": m.asset_id})
                if self.client.container_status(child) != "FINISHED":
                    return PublishResult(status=PublishStatus.PROCESSING, remote_container_id=child,
                                         provider_mode=self.client.mode,
                                         detail={"waiting_child": m.asset_id})
                children.append(child)
            parent = self.client.create_container(self.platform, req.idempotency_key,
                                                  {"kind": "carousel", "children": children})
            post = self.client.publish_container(self.platform, parent, req.idempotency_key)
            return PublishResult(status=PublishStatus.VERIFYING, remote_container_id=parent,
                                 remote_post_id=post["id"], remote_url=post.get("url"),
                                 provider_mode=self.client.mode,
                                 detail={"children": len(children)})
        return self._container_publish(req, {**self._payload(req), "kind": "ig_media"})


class FacebookPublisher(BasePublisher):
    platform = "facebook"

    def _do_publish(self, req: PublishRequest) -> PublishResult:
        return self._container_publish(req, {**self._payload(req), "surface": "page"})


class ThreadsPublisher(BasePublisher):
    platform = "threads"

    def _do_publish(self, req: PublishRequest) -> PublishResult:
        posts = req.platform_settings.get("thread_posts")
        if not posts:
            return self._container_publish(req, {**self._payload(req), "kind": "threads_text"})
        # root then reply chain, storing every id
        root_c = self.client.create_container(self.platform, f"{req.idempotency_key}:0",
                                              {"text": posts[0]})
        root = self.client.publish_container(self.platform, root_c, f"{req.idempotency_key}:0")
        thread_ids = [root["id"]]
        parent = root["id"]
        for i, text in enumerate(posts[1:], start=1):
            r = self.client.reply(self.platform, parent, f"{req.idempotency_key}:{i}")
            thread_ids.append(r["id"])
            parent = r["id"]
        return PublishResult(status=PublishStatus.VERIFYING, remote_post_id=root["id"],
                             remote_url=root.get("url"), thread_remote_ids=thread_ids,
                             provider_mode=self.client.mode)


class XPublisher(BasePublisher):
    platform = "x"

    def _do_publish(self, req: PublishRequest) -> PublishResult:
        s = get_settings()
        cost = s.x_cost_per_post_usd
        detail = {"api_cost_usd": cost} if cost is not None else {"pricing": "PRICING_UNKNOWN"}
        posts = req.platform_settings.get("thread_posts")
        if not posts:
            c = self.client.create_container(self.platform, req.idempotency_key,
                                             {"text": req.caption or req.title})
            post = self.client.publish_container(self.platform, c, req.idempotency_key)
            return PublishResult(status=PublishStatus.VERIFYING, remote_post_id=post["id"],
                                 remote_url=post.get("url"), provider_mode=self.client.mode, detail=detail)
        c0 = self.client.create_container(self.platform, f"{req.idempotency_key}:0", {"text": posts[0]})
        root = self.client.publish_container(self.platform, c0, f"{req.idempotency_key}:0")
        ids = [root["id"]]
        parent = root["id"]
        for i, text in enumerate(posts[1:], start=1):
            r = self.client.reply(self.platform, parent, f"{req.idempotency_key}:{i}")
            ids.append(r["id"])
            parent = r["id"]
        detail["thread_len"] = len(ids)
        return PublishResult(status=PublishStatus.VERIFYING, remote_post_id=root["id"],
                             remote_url=root.get("url"), thread_remote_ids=ids,
                             provider_mode=self.client.mode, detail=detail)


class PinterestPublisher(BasePublisher):
    platform = "pinterest"

    def validate_media(self, req: PublishRequest) -> tuple[bool, list[str]]:
        ok, errs = super().validate_media(req)
        if not req.platform_settings.get("board_id"):
            errs.append("Pinterest pin requires platform_settings.board_id")
        return (not errs, errs)

    def _do_publish(self, req: PublishRequest) -> PublishResult:
        if any(m.kind == "video" for m in req.media):
            self._resumable_upload(req)                  # /v5/media multi-step
        return self._container_publish(req, {**self._payload(req),
                                             "board_id": req.platform_settings.get("board_id"),
                                             "link": req.platform_settings.get("link", "")})


class LinkedInPublisher(BasePublisher):
    platform = "linkedin"

    def publish(self, req: PublishRequest) -> PublishResult:
        atype = (self.account.get("account_type") or "").lower()
        if "organization" in atype or "page" in atype:
            return self._blocked_result("APP_REVIEW",
                                        {"reason": "organization posting needs Community Management API review"})
        # member share path
        if req.dry_run:
            return PublishResult(status=PublishStatus.READY, provider_mode=self.client.mode,
                                 detail={"dry_run": True})
        return self._container_publish(req, {**self._payload(req), "scope": "w_member_social"})


class NaverBlogPublisher(BasePublisher):
    platform = "naver_blog"

    def publish(self, req: PublishRequest) -> PublishResult:
        s = get_settings()
        package = {
            "type": "NAVER_BLOG_PACKAGE",
            "title": req.title,
            "article_markdown": req.description or req.caption,
            "images": [m.asset_id for m in req.media if m.kind == "image"],
            "tags": req.hashtags,
            "ai_generated": req.ai_generated,
            "browser_assist_enabled": s.naver_browser_assist,
            "note": "No verified official Naver Blog write API. Manual posting required; "
                    "browser assist never bypasses CAPTCHA / identity / security verification.",
        }
        return PublishResult(status=PublishStatus.WAITING_USER_ACTION, provider_mode=self.client.mode,
                             needs="MANUAL", detail=package)


class NaverClipPublisher(BasePublisher):
    platform = "naver_clip"

    def publish(self, req: PublishRequest) -> PublishResult:
        return PublishResult(
            status=PublishStatus.NOT_SUPPORTED, provider_mode=self.client.mode,
            detail={"type": "NAVER_CLIP_MANUAL_PACKAGE",
                    "video_asset_ids": [m.asset_id for m in req.media if m.kind == "video"],
                    "reason": "No verified official Naver Clip publishing API; upload is mobile-app only."},
        )


_REGISTRY: dict[str, type[BasePublisher]] = {
    "youtube": YouTubePublisher, "tiktok": TikTokPublisher, "instagram": InstagramPublisher,
    "facebook": FacebookPublisher, "threads": ThreadsPublisher, "x": XPublisher,
    "pinterest": PinterestPublisher, "linkedin": LinkedInPublisher,
    "naver_blog": NaverBlogPublisher, "naver_clip": NaverClipPublisher,
}


def get_publisher(platform: str, account: dict | None = None,
                  client: PublisherClient | None = None) -> BasePublisher:
    key = resolve_publishing_platform(platform)
    if key not in _REGISTRY:
        raise KeyError(f"no publisher for platform {platform!r}")
    return _REGISTRY[key](account or {}, client)


def all_publisher_platforms() -> list[str]:
    return list(_REGISTRY)
