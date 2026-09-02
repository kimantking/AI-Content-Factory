"""URLSecurityValidator + URLClassifier.

Security reuses the Phase 5 SSRF guard (`app.ops.ssrf`). External URL *content* is
always UNTRUSTED_EXTERNAL_CONTENT (see `app.intel.injection`). Redirects are
re-validated by the fetcher after every hop.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse, urlunparse

from app.config import get_settings
from app.ops.ssrf import SSRFBlocked, _ip_is_dangerous, is_safe_url

_BLOCKED_SCHEMES = {"file", "gopher", "ftp", "data", "ws", "wss", "javascript", "about"}
_ALLOWED_SCHEMES = {"http", "https"}

# host / path hints -> (source_type, support_level)
_GITHUB_REPO = re.compile(r"^https?://github\.com/[^/]+/[^/]+/?$", re.I)
_GITHUB_FILE = re.compile(r"^https?://github\.com/[^/]+/[^/]+/(blob|tree|raw)/", re.I)
_YOUTUBE = re.compile(r"^https?://(www\.)?(youtube\.com/(watch|shorts|embed)|youtu\.be/)", re.I)
_PDF = re.compile(r"\.pdf($|\?)", re.I)
_NEWS_HINT = re.compile(r"(news|/article/|/story/|reuters|bbc|nytimes|bloomberg|yna\.co\.kr|hani\.co\.kr)", re.I)
_BLOG_HINT = re.compile(r"(blog\.|/blog/|medium\.com|substack\.com|tistory\.com|velog\.io|brunch\.co\.kr|wordpress)", re.I)
_DOC_HINT = re.compile(r"(docs\.|/docs/|developer\.|/reference/|readthedocs|/whitepaper|gov\.|\.go\.kr|/policy)", re.I)
_PRODUCT_HINT = re.compile(r"(/product/|/dp/|/p/|/item/|amazon\.|/shop/|/store/|coupang\.com)", re.I)
_SOCIAL_HINT = re.compile(r"(twitter\.com|x\.com/[^/]+/status|instagram\.com/p/|tiktok\.com/@|threads\.net|facebook\.com/.+/posts)", re.I)
_VIDEO_HINT = re.compile(r"(vimeo\.com|\.mp4($|\?)|/video/|player\.)", re.I)
_AUTH_HINT = re.compile(r"(/login|/signin|accounts\.|/subscribe|paywall|members\.)", re.I)


class URLValidationResult:
    __slots__ = ("ok", "url", "reason", "source_type", "support_level")

    def __init__(self, ok, url, reason, source_type, support_level):
        self.ok, self.url, self.reason = ok, url, reason
        self.source_type, self.support_level = source_type, support_level

    def as_dict(self) -> dict:
        return {"ok": self.ok, "url": self.url, "reason": self.reason,
                "source_type": self.source_type, "support_level": self.support_level}


def canonicalize(url: str) -> str:
    """Drop tracking params + fragments for dedup / canonical_url."""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url.strip()
    drop = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "gclid", "fbclid", "ref", "ref_src", "igshid", "si", "feature"}
    q = "&".join(kv for kv in (p.query or "").split("&")
                 if kv and kv.split("=")[0].lower() not in drop)
    host = (p.netloc or "").lower()
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), host, path, "", q, ""))


def classify_url(url: str) -> tuple[str, str]:
    """URLClassifier — (source_type, support_level). Never guesses AVAILABLE."""
    u = (url or "").strip()
    if _GITHUB_FILE.search(u):
        return "GITHUB_FILE", "SUPPORTED"
    if _GITHUB_REPO.search(u):
        return "GITHUB_REPOSITORY", "SUPPORTED"
    if _YOUTUBE.search(u):
        return "YOUTUBE", "LIMITED"          # metadata + provided profile only; no scraping
    if _PDF.search(u):
        return "PDF", "SUPPORTED"
    if _AUTH_HINT.search(u):
        return "WEB_PAGE", "AUTH_REQUIRED"
    if _SOCIAL_HINT.search(u):
        return "SOCIAL_POST", "LIMITED"
    if _VIDEO_HINT.search(u):
        return "VIDEO_PAGE", "LIMITED"
    if _PRODUCT_HINT.search(u):
        return "PRODUCT_PAGE", "SUPPORTED"
    if _DOC_HINT.search(u):
        return "OFFICIAL_DOCUMENT", "SUPPORTED"
    if _NEWS_HINT.search(u):
        return "NEWS_ARTICLE", "SUPPORTED"
    if _BLOG_HINT.search(u):
        return "BLOG", "SUPPORTED"
    if u.startswith(("http://", "https://")):
        return "WEB_PAGE", "SUPPORTED"
    return "UNKNOWN", "UNSUPPORTED"


def validate_url(url: str, *, extra_allow_hosts: list[str] | None = None) -> URLValidationResult:
    """URLSecurityValidator. Blocks bad schemes + SSRF targets (localhost, private
    IP, metadata endpoints, internal docker services, redis/postgres, file://,
    gopher://). Safe to call again on every redirect hop."""
    raw = (url or "").strip()
    if not raw:
        return URLValidationResult(False, raw, "empty url", "UNKNOWN", "UNSUPPORTED")
    scheme = (urlparse(raw).scheme or "").lower()
    if scheme in _BLOCKED_SCHEMES:
        return URLValidationResult(False, raw, f"blocked scheme {scheme!r}", "UNKNOWN", "UNSUPPORTED")
    if scheme not in _ALLOWED_SCHEMES:
        return URLValidationResult(False, raw, f"unsupported scheme {scheme or '(none)'}", "UNKNOWN", "UNSUPPORTED")
    st, sup = classify_url(raw)
    if get_settings().is_production:
        # full check incl. DNS-rebinding protection (resolves every A/AAAA record)
        ok, reason = is_safe_url(raw, extra_allow_hosts=extra_allow_hosts)
        if not ok:
            return URLValidationResult(False, raw, f"ssrf: {reason}", st, "UNSUPPORTED")
        return URLValidationResult(True, canonicalize(raw), "ok", st, sup)

    # non-production: literal checks only (no blocking DNS lookup). localhost /
    # IP-literals / metadata / *.internal are still rejected; a hostname that does
    # not resolve simply cannot reach an internal service.
    ok, reason = _literal_ssrf_check(raw, extra_allow_hosts=extra_allow_hosts)
    if not ok:
        return URLValidationResult(False, raw, f"ssrf: {reason}", st, "UNSUPPORTED")
    return URLValidationResult(True, canonicalize(raw), "ok", st, sup)


_METADATA_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}


def _literal_ssrf_check(url: str, *, extra_allow_hosts: list[str] | None = None) -> tuple[bool, str]:
    from app.config import get_settings as _gs

    p = urlparse(url)
    host = (p.hostname or "").lower()
    if not host:
        return False, "no host"
    allow = {h.lower() for h in ((_gs().ssrf_allow_hosts or []) + (extra_allow_hosts or []))}
    if host in allow:
        return True, "host allowlisted"
    if host in _METADATA_HOSTS or host.endswith(".internal") or host.endswith(".local"):
        return False, "metadata/internal host blocked"
    if host in ("localhost", "0.0.0.0", "ip6-localhost", "ip6-loopback"):
        return False, "localhost blocked"
    try:
        addr = ipaddress.ip_address(host)
        if _ip_is_dangerous(str(addr)):
            return False, f"blocked address {host}"
    except ValueError:
        pass   # a hostname, not an IP literal — fine without a lookup
    return True, "ok"


def require_safe_url(url: str, *, extra_allow_hosts: list[str] | None = None) -> str:
    r = validate_url(url, extra_allow_hosts=extra_allow_hosts)
    if not r.ok:
        raise SSRFBlocked(f"blocked url {url!r}: {r.reason}")
    return r.url
