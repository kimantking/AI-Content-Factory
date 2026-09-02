from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

from app.providers.errors import NON_RETRYABLE, ProviderError

T = TypeVar("T")

# Dedicated RNG so backoff jitter never perturbs the global `random` sequence
# (which app.learning.experiment falls back to when unseeded).
_JITTER = random.Random()


def call_with_retry(fn: Callable[[], T], *, attempts: int = 3, base_delay: float = 0.05,
                    on_retry: Callable[[int, Exception], None] | None = None) -> T:
    """Retry a provider call on transient errors only.

    AUTH_ERROR / BUDGET_EXCEEDED (NON_RETRYABLE) are raised immediately — retrying
    them would be meaningless (spec: Retry section).
    """
    last: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except ProviderError as e:
            if getattr(e, "error_type", "PROVIDER_ERROR") in NON_RETRYABLE:
                raise
            last = e
            if on_retry:
                on_retry(i, e)
            if i < attempts:
                # exponential-ish backoff + full jitter (AWS "Exponential Backoff
                # and Jitter") to avoid synchronised retry storms against a real API.
                time.sleep(_JITTER.uniform(0, base_delay * (2 ** (i - 1))))
    assert last is not None
    raise last
