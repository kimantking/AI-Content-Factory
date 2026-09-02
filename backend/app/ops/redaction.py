from __future__ import annotations

import re

# Keys whose VALUES must never appear in logs / errors / API responses.
_SECRET_KEYS = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"authorization|cookie|session|encryption[_-]?key|client[_-]?secret|"
    r"webhook[_-]?secret|private[_-]?key|bearer|credential)",
    re.I,
)

# Value patterns that look like secrets even under an innocent key.
_VALUE_PATTERNS = [
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}", re.I),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bsk-(ant-)?[A-Za-z0-9_\-]{16,}"),          # OpenAI / Anthropic style
    re.compile(r"\bsk_(live|test)_[A-Za-z0-9]{16,}"),         # Stripe style
    re.compile(r"\bya29\.[A-Za-z0-9._\-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}"),  # JWT
    re.compile(r"gAAAAA[A-Za-z0-9_\-]{40,}"),  # Fernet token
    re.compile(r"postgres(ql)?://[^\s\"']*:[^\s\"'@/]+@", re.I),  # DSN with password
]

_MASK = "***REDACTED***"


def _mask_value(v: str) -> str:
    if len(v) <= 8:
        return _MASK
    return f"{v[:3]}…{v[-3:]}⟨redacted⟩"


def redact_text(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _VALUE_PATTERNS:
        out = pat.sub(_MASK, out)
    return out


def redact(obj, _depth: int = 0):
    """Recursively redact secrets from dicts/lists/strings. Safe for logging."""
    if _depth > 12:
        return obj
    if isinstance(obj, dict):
        red = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEYS.search(k):
                red[k] = _MASK if v is not None else None
            else:
                red[k] = redact(v, _depth + 1)
        return red
    if isinstance(obj, (list, tuple)):
        return type(obj)(redact(x, _depth + 1) for x in obj)
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


class SecretRedactionFilter:
    """logging.Filter that scrubs message + args before emit."""

    def filter(self, record) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = redact(record.args)
                else:
                    record.args = tuple(redact(a) for a in record.args)
        except Exception:  # noqa: BLE001 — never break logging
            pass
        return True
