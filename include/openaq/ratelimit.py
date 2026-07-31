"""Client-side rate limiting for the OpenAQ API.

Enforces the configured request limits using a sliding-window algorithm.
"""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Window:
    """At most ``max_requests`` within any ``seconds``-long span."""

    max_requests: int
    seconds: float

    def __post_init__(self) -> None:
        if self.max_requests < 1:
            raise ValueError(f"max_requests must be >= 1, got {self.max_requests}")
        if self.seconds <= 0:
            raise ValueError(f"seconds must be > 0, got {self.seconds}")


# OpenAQ free-tier rate limits.
# https://docs.openaq.org/using-the-api/rate-limits
OPENAQ_FREE_TIER: tuple[Window, ...] = (
    Window(max_requests=60, seconds=60.0),
    Window(max_requests=2000, seconds=3600.0),
)


class SlidingWindowLimiter:
    """Blocks until a request fits inside every configured window.

    ``clock`` and ``sleep`` are injectable for deterministic testing.
    """

    def __init__(
        self,
        windows: tuple[Window, ...] = OPENAQ_FREE_TIER,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not windows:
            raise ValueError("at least one Window is required")
        self._windows = windows
        self._clock = clock
        self._sleep = sleep
        # One timestamp log per window; each is pruned against its own span.
        self._logs: tuple[deque[float], ...] = tuple(deque() for _ in windows)

    def acquire(self) -> float:
        """Reserve one request slot, sleeping if necessary.

        Returns the total seconds slept — 0.0 when the request went through
        without pacing.
        """
        slept = 0.0
        while True:
            now = self._clock()
            wait = self._longest_wait(now)
            if wait <= 0:
                for log in self._logs:
                    log.append(now)
                return slept
            self._sleep(wait)
            slept += wait

    def _longest_wait(self, now: float) -> float:
        """Return the wait time until every window has capacity."""
        longest = 0.0
        for window, log in zip(self._windows, self._logs, strict=True):
            cutoff = now - window.seconds
            while log and log[0] <= cutoff:
                log.popleft()
            if len(log) >= window.max_requests:
                # The oldest entry is what frees the slot when it ages out.
                longest = max(longest, log[0] + window.seconds - now)
        return longest
