"""Unit tests for the free-tier rate limiter.

All tests run on virtual time using ``FakeClock``.
"""

import pytest

from include.openaq.ratelimit import OPENAQ_FREE_TIER, SlidingWindowLimiter, Window
from tests.openaq_fakes import FakeClock


def _limiter(*windows: Window) -> tuple[SlidingWindowLimiter, FakeClock]:
    clock = FakeClock()
    return (
        SlidingWindowLimiter(windows or OPENAQ_FREE_TIER, clock=clock, sleep=clock.sleep),
        clock,
    )


def test_requests_under_the_limit_never_sleep() -> None:
    limiter, clock = _limiter(Window(max_requests=5, seconds=60.0))

    for _ in range(5):
        assert limiter.acquire() == 0.0

    assert clock.slept == []


def test_limiter_sleeps_until_the_oldest_request_ages_out() -> None:
    limiter, clock = _limiter(Window(max_requests=3, seconds=60.0))

    for _ in range(3):
        limiter.acquire()
    slept = limiter.acquire()

    # The first request landed at t=0, so its slot frees at t=60.
    assert slept == pytest.approx(60.0)
    assert clock.now == pytest.approx(60.0)


def _assert_window_never_exceeded(sent_at: list[float], window: Window) -> None:
    for index, moment in enumerate(sent_at):
        in_window = [t for t in sent_at[: index + 1] if t > moment - window.seconds]
        assert len(in_window) <= window.max_requests, (
            f"request {index + 1} at t={moment} sits in a {window.seconds}s span "
            f"holding {len(in_window)} requests, over the cap of {window.max_requests}"
        )


def test_pacing_holds_the_per_minute_rate_over_many_requests() -> None:
    window = Window(max_requests=60, seconds=60.0)
    limiter, clock = _limiter(window)

    sent_at = []
    for _ in range(180):
        limiter.acquire()
        sent_at.append(clock.now)

    _assert_window_never_exceeded(sent_at, window)
    # 180 requests need two further windows beyond the opening burst of 60.
    assert clock.now == pytest.approx(120.0)


def test_hourly_ceiling_binds_even_when_the_minute_window_has_room() -> None:
    limiter, clock = _limiter(*OPENAQ_FREE_TIER)

    for _ in range(2001):
        limiter.acquire()

    # The 2001st request has to wait for the first to leave the hourly window.
    assert clock.now >= 3600.0


def test_both_windows_are_enforced_together() -> None:
    limiter, clock = _limiter(
        Window(max_requests=2, seconds=10.0),
        Window(max_requests=3, seconds=100.0),
    )

    for _ in range(3):
        limiter.acquire()
    limiter.acquire()

    # The longer window is now the limiting factor.
    assert clock.now == pytest.approx(100.0)


def test_slots_are_reusable_once_the_window_slides_past() -> None:
    limiter, clock = _limiter(Window(max_requests=2, seconds=10.0))

    limiter.acquire()
    limiter.acquire()
    clock.now = 11.0  # both entries are now older than the window

    assert limiter.acquire() == 0.0


def test_free_tier_matches_the_documented_limits() -> None:
    assert {(w.max_requests, w.seconds) for w in OPENAQ_FREE_TIER} == {
        (60, 60.0),
        (2000, 3600.0),
    }


@pytest.mark.parametrize(
    ("max_requests", "seconds"),
    [(0, 60.0), (-1, 60.0), (60, 0.0), (60, -5.0)],
)
def test_nonsensical_windows_are_rejected(max_requests: int, seconds: float) -> None:
    with pytest.raises(ValueError):
        Window(max_requests=max_requests, seconds=seconds)


def test_limiter_requires_at_least_one_window() -> None:
    with pytest.raises(ValueError, match="at least one Window"):
        SlidingWindowLimiter(())
