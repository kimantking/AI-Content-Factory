"""ReferenceFetcher + adapters.

Adapters:
  http     — stdlib urllib, follows redirects manually and re-validates every hop.
  browser  — JS-rendering adapter (Playwright etc.). OPT-IN, off by default
             (`browser_fetch_enabled`, install policy D67). The stub raises
             AdapterUnavailable rather than faking a render.

Forbidden for every adapter: CAPTCHA / paywall / login / DRM / anti-bot bypass.
Tests register deterministic responses on the mock client.
"""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass, field

from app.config import get_settings
from app.intel.url_security import validate_url

_MAX_REDIRECTS = 5


class AdapterUnavailable(RuntimeError):
    pass


class FetchBlocked(RuntimeError):
    pass


@dataclass
class FetchResult:
    ok: bool
    status: int
    final_url: str
    content_type: str = ""
    body: bytes = b""
    redirects: list[str] = field(default_factory=list)
    adapter: str = "http"
    error: str = ""

    @property
    def text(self) -> str:
        try:
            return self.body.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return ""


# --------------------------------------------------------------------- #
#  clients (swappable, like app.providers)
# --------------------------------------------------------------------- #

class MockReferenceClient:
    """Deterministic offline client. `register(url, ...)` before use."""

    def __init__(self):
        self._responses: dict[str, dict] = {}

    def register(self, url: str, *, body: str | bytes = "", status: int = 200,
                 content_type: str = "text/html; charset=utf-8",
                 redirects: list[str] | None = None):
        from app.intel.url_security import canonicalize
        key = canonicalize(url)
        self._responses[key] = {
            "body": body.encode("utf-8") if isinstance(body, str) else body,
            "status": status, "content_type": content_type, "redirects": redirects or [],
        }
        self._responses[url] = self._responses[key]

    def reset(self):
        self._responses.clear()

    def fetch(self, url: str, *, adapter: str = "http") -> FetchResult:
        from app.intel.url_security import canonicalize
        r = self._responses.get(url) or self._responses.get(canonicalize(url))
        if r is None:
            return FetchResult(ok=False, status=404, final_url=url, adapter=adapter,
                               error="no mock registered for url")
        # re-validate any registered redirect chain
        for hop in r["redirects"]:
            v = validate_url(hop)
            if not v.ok:
                return FetchResult(ok=False, status=0, final_url=hop, adapter=adapter,
                                   error=f"redirect blocked: {v.reason}", redirects=r["redirects"])
        return FetchResult(ok=r["status"] < 400, status=r["status"],
                           final_url=r["redirects"][-1] if r["redirects"] else url,
                           content_type=r["content_type"], body=r["body"],
                           redirects=r["redirects"], adapter=adapter)


class HttpReferenceClient:
    """Real stdlib fetch. Manual redirect handling with per-hop SSRF re-validation."""

    def fetch(self, url: str, *, adapter: str = "http") -> FetchResult:
        s = get_settings()
        current = url
        redirects: list[str] = []
        for _ in range(_MAX_REDIRECTS + 1):
            v = validate_url(current)
            if not v.ok:
                return FetchResult(ok=False, status=0, final_url=current, adapter=adapter,
                                   error=f"blocked: {v.reason}", redirects=redirects)
            req = urllib.request.Request(current, headers={
                "User-Agent": "ACF-ReferenceFetcher/1.0 (+learning; respects robots/ToS)",
                "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain,*/*",
            })
            try:
                opener = urllib.request.build_opener(_NoRedirect())
                resp = opener.open(req, timeout=20)
            except _Redirected as rd:
                redirects.append(rd.location)
                current = rd.location
                continue
            except Exception as e:  # noqa: BLE001
                return FetchResult(ok=False, status=0, final_url=current, adapter=adapter,
                                   error=str(e)[:300], redirects=redirects)
            with resp:
                body = resp.read(s.max_reference_bytes + 1)
            if len(body) > s.max_reference_bytes:
                return FetchResult(ok=False, status=resp.status, final_url=current, adapter=adapter,
                                   error=f"exceeds max_reference_bytes ({s.max_reference_bytes})",
                                   redirects=redirects)
            return FetchResult(ok=resp.status < 400, status=resp.status, final_url=current,
                               content_type=resp.headers.get("Content-Type", ""), body=body,
                               redirects=redirects, adapter=adapter)
        return FetchResult(ok=False, status=0, final_url=current, adapter=adapter,
                           error="too many redirects", redirects=redirects)


class _Redirected(Exception):
    def __init__(self, location):
        self.location = location


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise _Redirected(newurl)


class BrowserFetchAdapter:
    """JS-rendering adapter — OPT-IN. Not wired to a browser engine (install
    policy D67: Playwright is a project-scoped dependency pending approval).
    Never bypasses CAPTCHA / paywall / login / DRM / anti-bot."""

    available = False

    def fetch(self, url: str, *, adapter: str = "browser") -> FetchResult:
        raise AdapterUnavailable(
            "browser fetch adapter not enabled — set browser_fetch_enabled and "
            "install an approved headless-browser dependency"
        )


_client = MockReferenceClient()


def set_client(client) -> None:
    global _client
    _client = client


def get_client():
    return _client


def fetch(url: str, *, prefer_browser: bool = False) -> FetchResult:
    """ReferenceFetcher entry point. Validates the URL, chooses an adapter, and
    re-validates redirects (mock + http clients both do per-hop checks)."""
    v = validate_url(url)
    if not v.ok:
        return FetchResult(ok=False, status=0, final_url=url, error=f"blocked: {v.reason}")
    s = get_settings()
    if prefer_browser and s.browser_fetch_enabled:
        try:
            return BrowserFetchAdapter().fetch(v.url)
        except AdapterUnavailable as e:
            return FetchResult(ok=False, status=0, final_url=v.url, adapter="browser", error=str(e))
    return get_client().fetch(v.url, adapter="http")
