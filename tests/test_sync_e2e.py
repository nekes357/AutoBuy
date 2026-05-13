"""End-to-end sync test using the mock JD client and fixture data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.models import JdOrder, SyncLog
from src.sync import run_sync

# Total orders across both fixture pages.
EXPECTED_TOTAL = 11
EXPECTED_PAGE_1 = 9
EXPECTED_PAGE_2 = 2


@pytest.mark.asyncio
async def test_sync_pulls_orders_from_mock(session):
    until = datetime.now(UTC)
    since = until - timedelta(hours=1)

    sync_log = await run_sync(session, since=since, until=until)

    assert sync_log.error_count == 0
    assert sync_log.fetched_count == EXPECTED_TOTAL
    assert sync_log.new_count == EXPECTED_TOTAL

    orders = session.execute(select(JdOrder).order_by(JdOrder.jd_order_id)).scalars().all()
    assert len(orders) == EXPECTED_TOTAL

    by_id = {o.jd_order_id: o for o in orders}
    # Order with both pages present:
    assert "100000000001" in by_id
    assert "100000000011" in by_id  # last id from page 2

    o1 = by_id["100000000001"]
    assert o1.recipient_name == "Ivan Petrov"
    assert o1.total_cny == 850.0
    assert o1.total_rub == round(850.0 * 12.5, 2)
    assert o1.raw_payload["result"]["jdOrderId"] == "100000000001"


@pytest.mark.asyncio
async def test_sync_is_idempotent(session):
    until = datetime.now(UTC)
    since = until - timedelta(hours=1)

    first = await run_sync(session, since=since, until=until)
    second = await run_sync(session, since=since, until=until)

    assert first.new_count == EXPECTED_TOTAL
    assert second.new_count == 0
    assert second.fetched_count == EXPECTED_TOTAL

    rows = session.execute(select(JdOrder)).scalars().all()
    assert len(rows) == EXPECTED_TOTAL

    logs = session.execute(select(SyncLog)).scalars().all()
    assert len(logs) == 2


@pytest.mark.asyncio
async def test_sync_handles_edge_cases_without_errors(session):
    """Run sync once and verify every edge-case fixture lands in the DB
    with sensible (but possibly partial) summary fields."""
    until = datetime.now(UTC)
    since = until - timedelta(hours=1)

    sync_log = await run_sync(session, since=since, until=until)
    assert sync_log.error_count == 0, f"some orders failed: {sync_log.errors}"

    by_id = {
        o.jd_order_id: o
        for o in session.execute(select(JdOrder)).scalars().all()
    }

    # Order 3: uses `consigneeName` instead of `name`, and landline `phone` instead of `mobile`.
    assert by_id["100000000003"].recipient_name == "Sergey Volkov"
    assert by_id["100000000003"].recipient_phone == "010-12345678"

    # Order 4: flat address string (no province/city/county breakdown). Should still parse.
    assert by_id["100000000004"].recipient_name == "Marina K."
    assert by_id["100000000004"].total_cny == 99.0

    # Order 5: large multi-item order.
    assert by_id["100000000005"].total_cny == 18450.0
    assert len(by_id["100000000005"].raw_payload["result"]["sku"]) == 6

    # Order 6: cancelled order, still gets persisted (we capture everything, filter later).
    assert by_id["100000000006"].raw_payload["result"]["state"] == "CANCELLED"

    # Order 7: missing orderPrice — total_cny is None, no crash on conversion.
    assert by_id["100000000007"].total_cny is None
    assert by_id["100000000007"].total_rub is None

    # Order 8: empty sku list — still saved.
    assert by_id["100000000008"].total_cny == 0.0
    assert by_id["100000000008"].raw_payload["result"]["sku"] == []

    # Order 9: uses `totalPrice` instead of `orderPrice`, and `items` instead of `sku`.
    assert by_id["100000000009"].total_cny == 777.77
    assert by_id["100000000009"].total_rub == round(777.77 * 12.5, 2)

    # Orders 10, 11 come from page 2 — verifies pagination.
    assert "100000000010" in by_id
    assert "100000000011" in by_id


@pytest.mark.asyncio
async def test_sync_tolerates_unknown_fields(session):
    """The mock data already includes assorted unknown keys; make sure they
    round-trip into raw_payload without breaking the pipeline."""
    until = datetime.now(UTC)
    since = until - timedelta(hours=1)

    sync_log = await run_sync(session, since=since, until=until)
    assert sync_log.error_count == 0

    order = session.execute(
        select(JdOrder).where(JdOrder.jd_order_id == "100000000006")
    ).scalar_one()
    # `cancelReason` is not a known field anywhere in our models or summarizer,
    # but it must still be preserved in raw_payload for debugging.
    assert order.raw_payload["result"]["cancelReason"] == "buyer_refused"
