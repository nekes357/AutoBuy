"""End-to-end sync test using the mock JD client and fixture data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.models import JdOrder, SyncLog
from src.sync import run_sync


@pytest.mark.asyncio
async def test_sync_pulls_orders_from_mock(session):
    until = datetime.now(timezone.utc)
    since = until - timedelta(hours=1)

    sync_log = await run_sync(session, since=since, until=until)

    assert sync_log.error_count == 0
    assert sync_log.fetched_count == 2
    assert sync_log.new_count == 2

    orders = session.execute(select(JdOrder).order_by(JdOrder.jd_order_id)).scalars().all()
    assert [o.jd_order_id for o in orders] == ["100000000001", "100000000002"]
    o1 = orders[0]
    assert o1.recipient_name == "Ivan Petrov"
    assert o1.total_cny == 850.0
    assert o1.total_rub == round(850.0 * 12.5, 2)
    assert o1.raw_payload["result"]["jdOrderId"] == "100000000001"


@pytest.mark.asyncio
async def test_sync_is_idempotent(session):
    until = datetime.now(timezone.utc)
    since = until - timedelta(hours=1)

    first = await run_sync(session, since=since, until=until)
    second = await run_sync(session, since=since, until=until)

    assert first.new_count == 2
    assert second.new_count == 0
    assert second.fetched_count == 2

    rows = session.execute(select(JdOrder)).scalars().all()
    assert len(rows) == 2

    logs = session.execute(select(SyncLog)).scalars().all()
    assert len(logs) == 2
