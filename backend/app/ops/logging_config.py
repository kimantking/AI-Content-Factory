from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import uuid

from app.config import get_settings
from app.ops.redaction import SecretRedactionFilter, redact

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)
_context: contextvars.ContextVar[dict] = contextvars.ContextVar("log_context", default={})

_STD = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "taskName",
}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, env: str):
        super().__init__()
        self.service = service
        self.env = env

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "service": self.service,
            "environment": self.env,
            "logger": record.name,
            "event": record.getMessage(),
        }
        cid = _correlation_id.get()
        if cid:
            base["correlation_id"] = cid
        ctx = _context.get()
        if ctx:
            base.update({k: v for k, v in ctx.items() if v is not None})
        for k, v in record.__dict__.items():
            if k not in _STD and not k.startswith("_"):
                base[k] = v
        if record.exc_info:
            base["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            base["exc"] = self.formatException(record.exc_info)[-2000:]
        return json.dumps(redact(base), ensure_ascii=False, default=str)


_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    s = get_settings()
    root = logging.getLogger()
    root.handlers.clear()
    h = logging.StreamHandler(sys.stdout)
    if s.is_production or s.app_env == "staging":
        h.setFormatter(JsonFormatter("acf-backend", s.app_env))
    else:
        h.setFormatter(logging.Formatter("%(levelname)-5s %(name)s: %(message)s"))
    h.addFilter(SecretRedactionFilter())
    root.addHandler(h)
    root.setLevel(getattr(logging, (s.log_level or "INFO").upper(), logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _CONFIGURED = True


def new_correlation_id() -> str:
    cid = uuid.uuid4().hex[:16]
    _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str | None) -> None:
    _correlation_id.set(cid)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def bind_log_context(**kw) -> None:
    cur = dict(_context.get())
    cur.update(kw)
    _context.set(cur)


def clear_log_context() -> None:
    _context.set({})
