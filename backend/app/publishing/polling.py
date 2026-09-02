from __future__ import annotations

import time
from collections.abc import Callable

from app.config import get_settings


class PollingManager:
    """Bounded polling for platform processing states. Never polls forever."""

    def __init__(self, schedule: list[int] | None = None, max_seconds: int | None = None):
        s = get_settings()
        self.schedule = schedule or list(s.publish_poll_schedule)
        self.max_seconds = max_seconds if max_seconds is not None else s.publish_poll_max_seconds

    def intervals(self):
        for v in self.schedule:
            yield v
        while True:                       # hold at the last interval
            yield self.schedule[-1]

    def run(self, step: Callable[[], object], done: Callable[[object], bool],
            *, sleep: Callable[[float], None] = time.sleep) -> tuple[bool, object]:
        elapsed = 0.0
        it = self.intervals()
        last = step()
        if done(last):
            return True, last
        while elapsed < self.max_seconds:
            wait = float(next(it))
            sleep(min(wait, max(0.0, self.max_seconds - elapsed)))
            elapsed += wait
            last = step()
            if done(last):
                return True, last
        return False, last
