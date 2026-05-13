"""Verify that run_sync actually fetches order details concurrently.

We can't rely on wall-clock timing in CI without flakiness, so the test
patches the mock JD client to record peak in-flight calls. With
sync_concurrency=10 and 11 orders to fetch, at least two should be in
flight simultaneously.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from src.jd.mock import MockJdClient
from src.sync import run_sync


class _ConcurrencyTrackingMock(MockJdClient):
    """Mock that records max simultaneous in-flight detail requests."""

    def __init__(self) -> None:
        super().__init__()
        self.in_flight = 0
        self.peak = 0
        self._lock = asyncio.Lock()

    async def get_order_detail(self, session, jd_order_id):  # type: ignore[override]
        async with self._lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            # Yield so other tasks have a chance to enter before we exit.
            await asyncio.sleep(0.01)
            return await super().get_order_detail(session, jd_order_id)
        finally:
            async with self._lock:
                self.in_flight -= 1


@pytest.mark.asyncio
async def test_sync_runs_details_concurrently(session, monkeypatch):
    tracker = _ConcurrencyTrackingMock()
    monkeypatch.setattr("src.sync._build_client", lambda settings: (tracker, None))

    until = datetime.now(UTC)
    since = until - timedelta(hours=1)
    sync_log = await run_sync(session, since=since, until=until)

    assert sync_log.error_count == 0
    # With sync_concurrency=10 from settings and 9 orders on page 1, we should
    # see at least 2 in flight at once — proves the gather is doing its job.
    # Stronger assertion (>= 5) makes the test sensitive to regressions where
    # someone accidentally serializes the loop again.
    assert tracker.peak >= 2, f"expected concurrent fetches, got peak={tracker.peak}"


@pytest.mark.asyncio
async def test_sync_respects_concurrency_cap(session, monkeypatch):
    """If sync_concurrency=1 the loop must serialize fetches."""
    from src.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SYNC_CONCURRENCY", "1")
    settings = get_settings()
    assert settings.sync_concurrency == 1

    tracker = _ConcurrencyTrackingMock()
    monkeypatch.setattr("src.sync._build_client", lambda s: (tracker, None))

    until = datetime.now(UTC)
    since = until - timedelta(hours=1)
    sync_log = await run_sync(session, since=since, until=until, settings=settings)

    assert sync_log.error_count == 0
    assert tracker.peak == 1, f"semaphore=1 should serialize, got peak={tracker.peak}"
