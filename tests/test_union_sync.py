"""End-to-end test for JD Union sync against the mock client."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.models import JdUnionProduct, SyncLog
from src.sync_union import run_union_sync

EXPECTED_FIXTURE_COUNT = 3  # union_goods_query.json has 3 items


@pytest.mark.asyncio
async def test_union_sync_search_only(session):
    """Without bigfield: items have summary fields, no wareQD/wdesc."""
    sync_log = await run_union_sync(session, keyword="drill", with_bigfield=False)

    assert sync_log.error_count == 0
    assert sync_log.fetched_count == EXPECTED_FIXTURE_COUNT
    assert sync_log.new_count == EXPECTED_FIXTURE_COUNT

    rows = session.execute(select(JdUnionProduct)).scalars().all()
    assert len(rows) == EXPECTED_FIXTURE_COUNT

    by_id = {r.sku_id: r for r in rows}
    drill = by_id["100012345001"]
    assert drill.sku_name.startswith("Аккумуляторная дрель")
    assert drill.price_cny == 389.0
    assert drill.price_rub == round(389.0 * 12.5, 2)
    assert drill.commission == 15.56
    assert drill.commission_share == 4.0
    assert drill.in_order_count_30d == 1820
    assert drill.main_image_url.startswith("https://img14.360buyimg.com")
    assert drill.brand_name == "JD Brand"
    # bigfield extras should be empty in summary-only mode.
    assert drill.ware_qd is None
    assert drill.wdesc is None


@pytest.mark.asyncio
async def test_union_sync_with_bigfield(session):
    """With bigfield: wareQD + wdesc are populated for items present in both fixtures."""
    sync_log = await run_union_sync(session, keyword="drill", with_bigfield=True)

    assert sync_log.error_count == 0
    assert sync_log.fetched_count == EXPECTED_FIXTURE_COUNT

    drill = session.get(JdUnionProduct, "100012345001")
    assert drill.wdesc is not None
    assert "<h3>" in drill.wdesc
    assert drill.ware_qd is not None
    assert "сверления металла" in drill.ware_qd

    # Order 3 from the search fixture has no bigfield entry — must stay None.
    third = session.get(JdUnionProduct, "100012345003")
    assert third is not None
    assert third.ware_qd is None
    assert third.wdesc is None


@pytest.mark.asyncio
async def test_union_sync_is_idempotent(session):
    """Re-running the same sync must not create duplicate rows."""
    first = await run_union_sync(session, keyword="drill")
    second = await run_union_sync(session, keyword="drill")

    assert first.new_count == EXPECTED_FIXTURE_COUNT
    assert second.new_count == 0
    assert second.fetched_count == EXPECTED_FIXTURE_COUNT

    rows = session.execute(select(JdUnionProduct)).scalars().all()
    assert len(rows) == EXPECTED_FIXTURE_COUNT


@pytest.mark.asyncio
async def test_union_sync_writes_sync_log(session):
    await run_union_sync(session, keyword="drill")
    logs = session.execute(
        select(SyncLog).where(SyncLog.source == "jd_union")
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].correlation_id is not None
    assert logs[0].finished_at is not None
