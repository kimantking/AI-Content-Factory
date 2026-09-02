from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes_analytics import router as analytics_router
from app.api.routes_autopilot import router as autopilot_router
from app.api.routes_campaigns import router as campaigns_router
from app.api.routes_media import router as media_router
from app.api.routes_meta import router as meta_router
from app.api.routes_ops import health_router, ops_router
from app.api.routes_publishing import router as publishing_router, wh_router as webhooks_router
from app.celery_app import celery_app  # noqa: F401  (registers configured Celery app as current)
from app.config import get_settings
from app.ops import metrics as _metrics
from app.ops.env import validate_environment
from app.ops.logging_config import (
    bind_log_context,
    clear_log_context,
    configure_logging,
    get_correlation_id,
    new_correlation_id,
    set_correlation_id,
)
from app.ops.rate_limit import RateLimited, check as rl_check, classify_path
from app.ops.redaction import redact
from app.ops.runtime_flags import maintenance_mode_active

_s = get_settings()
configure_logging()
validate_environment()  # raises in production on a hard mis-config; warns otherwise

app = FastAPI(title="AI Content Factory", version=_s.app_version,
              docs_url=None if _s.is_production else "/docs",
              redoc_url=None)

# --- security middleware ------------------------------------------------- #
app.add_middleware(
    CORSMiddleware,
    allow_origins=(["*"] if not _s.is_production else _s.cors_allow_origins),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=not _s.is_production,
)
if _s.trusted_hosts and _s.trusted_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_s.trusted_hosts)


class OpsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # request-size guard
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > _s.max_request_bytes:
            return JSONResponse({"detail": "request entity too large"}, status_code=413)

        # maintenance mode (health + ops always pass)
        if maintenance_mode_active() and not path.startswith(("/health", "/metrics", "/api/ops")):
            return JSONResponse({"detail": "maintenance mode"}, status_code=503)

        # Phase 6 — protect admin / ops surfaces. Enforced in production/staging
        # (or when AUTH_ENFORCE=true); a valid API key (X-Api-Key or Bearer) is
        # still honoured everywhere. Health + metrics stay open for scrapers.
        _protected = path.startswith(("/api/ops", "/api/admin", "/admin"))
        _auth_enforced = _s.app_env in ("production", "staging") or bool(getattr(_s, "auth_enforce", False))
        if _protected and _auth_enforced:
            from app.auth.service import authenticate as _authn
            from app.db.base import session_scope as _ss

            raw_auth = request.headers.get("authorization")
            raw_key = request.headers.get("x-api-key")
            ok = False
            try:
                with _ss() as _db:
                    ok = _authn(_db, authorization=raw_auth, x_api_key=raw_key) is not None
            except Exception:  # noqa: BLE001 — auth backend error must not 500 the gate
                ok = False
            if not ok:
                return JSONResponse({"detail": "authentication required"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})

        # rate limiting
        client = (request.client.host if request.client else "unknown")
        try:
            rl_check(classify_path(path, request.method), client)
        except RateLimited as e:
            _metrics.counter("acf_http_rate_limited_total", labels={"path_class": classify_path(path, request.method)})
            return JSONResponse({"detail": "rate limit exceeded", "retry_after": e.retry_after},
                                status_code=429, headers={"Retry-After": str(e.retry_after)})

        # correlation id + structured context
        cid = request.headers.get("x-correlation-id") or new_correlation_id()
        set_correlation_id(cid)
        bind_log_context(request_id=cid, path=path, method=request.method)
        t0 = time.perf_counter()
        try:
            resp = await call_next(request)
        except Exception:
            _metrics.counter("acf_http_requests_total", labels={"path_class": classify_path(path, request.method), "status": "500"})
            clear_log_context()
            raise
        dt = time.perf_counter() - t0
        pc = classify_path(path, request.method)
        _metrics.counter("acf_http_requests_total",
                         labels={"path_class": pc, "status": str(resp.status_code)},
                         help="HTTP requests")
        _metrics.observe("acf_http_request_seconds", dt, labels={"path_class": pc},
                         help="HTTP request duration")
        if resp.status_code >= 500:
            _metrics.counter("acf_http_5xx_total", labels={"path_class": pc})
        resp.headers["x-correlation-id"] = cid
        # security headers
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        if _s.is_production:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        clear_log_context()
        return resp


app.add_middleware(OpsMiddleware)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    import logging

    logging.getLogger("acf.api").exception("unhandled error", extra={"path": request.url.path})
    body = {"detail": "internal error", "correlation_id": get_correlation_id()}
    if not _s.is_production:
        body["error"] = redact(str(exc))
    return JSONResponse(body, status_code=500)


# --- routers ---------------------------------------------------------- #
app.include_router(health_router)
app.include_router(ops_router)
app.include_router(meta_router)
app.include_router(campaigns_router)
app.include_router(media_router)
app.include_router(publishing_router)
app.include_router(webhooks_router)
app.include_router(analytics_router)
app.include_router(autopilot_router)

# Phase 6 — multi-brand / auth
from app.api.routes_admin import bootstrap_admin_if_configured  # noqa: E402
from app.api.routes_admin import router as admin_router  # noqa: E402
from app.api.routes_multibrand import router as multibrand_router  # noqa: E402

app.include_router(admin_router)
app.include_router(multibrand_router)

# Phase 7 — content governance
from app.api.routes_governance import router as governance_router  # noqa: E402
from app.api.routes_intel import router as intel_router  # noqa: E402
from app.api.routes_ai import router as ai_router  # noqa: E402
from app.api.routes_library import router as library_router  # noqa: E402
from app.api.routes_providers import router as providers_router  # noqa: E402
from app.api.routes_support import router as support_router  # noqa: E402

app.include_router(governance_router)
app.include_router(intel_router)
app.include_router(ai_router)
app.include_router(library_router)
app.include_router(providers_router)
app.include_router(support_router)

try:
    bootstrap_admin_if_configured()
except Exception:  # noqa: BLE001 — never block startup on the optional bootstrap
    pass

for _d in ("storage", "outputs"):
    Path(_d).mkdir(exist_ok=True)
    app.mount(f"/files/{_d}", StaticFiles(directory=_d), name=f"files-{_d}")
