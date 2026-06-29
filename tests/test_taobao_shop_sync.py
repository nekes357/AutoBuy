"""End-to-end Taobao shop sync against the mock client."""

from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy import select

from src.models import SyncLog, TmallItem
from src.sync_taobao_shop import list_shop_items, run_shop_sync

# Mock shop fixtures: page1 has 2 items, page2 has 1 -> 3 total for the seller.
EXPECTED_SHOP_ITEMS = 3
SELLER = "demo_taobao_shop"


@pytest.mark.asyncio
async def test_shop_sync_from_item_url_pulls_whole_shop(session):
    """An item link resolves to its seller, then the whole shop is pulled."""
    report = await run_shop_sync(
        session,
        urls=["https://item.taobao.com/item.htm?id=612286553782"],
    )

    assert report.sellers == 1
    assert report.total_items == EXPECTED_SHOP_ITEMS
    assert report.new_items == EXPECTED_SHOP_ITEMS
    assert report.unresolved_links == 0

    shop = report.shops[0]
    assert shop.nick == SELLER
    assert shop.shop_title == "Demo Taobao Магазин электроники"
    assert shop.items_synced == EXPECTED_SHOP_ITEMS

    rows = session.execute(select(TmallItem)).scalars().all()
    assert len(rows) == EXPECTED_SHOP_ITEMS
    by_id = {r.num_iid: r for r in rows}
    cable = by_id["612286553782"]
    assert cable.seller_nick == SELLER
    assert cable.price_cny == 39.9
    assert cable.price_rub == round(39.9 * 12.5, 2)
    assert cable.title.startswith("Зарядный кабель")


@pytest.mark.asyncio
async def test_shop_sync_dedupes_sellers(session):
    """Many item links to the same shop hit the shop once."""
    report = await run_shop_sync(
        session,
        urls=[
            "https://item.taobao.com/item.htm?id=612286553782",
            "https://item.taobao.com/item.htm?id=612286553783",
            "https://item.taobao.com/item.htm?id=612286553784",
        ],
    )
    # All three items belong to demo_taobao_shop -> one seller, one shop crawl.
    assert report.sellers == 1
    assert report.total_items == EXPECTED_SHOP_ITEMS


@pytest.mark.asyncio
async def test_shop_sync_is_idempotent(session):
    first = await run_shop_sync(session, urls=["https://item.taobao.com/item.htm?id=612286553782"])
    second = await run_shop_sync(session, urls=["https://item.taobao.com/item.htm?id=612286553782"])
    assert first.new_items == EXPECTED_SHOP_ITEMS
    assert second.new_items == 0
    assert second.total_items == EXPECTED_SHOP_ITEMS
    rows = session.execute(select(TmallItem)).scalars().all()
    assert len(rows) == EXPECTED_SHOP_ITEMS


@pytest.mark.asyncio
async def test_shop_sync_unresolved_link_counted(session):
    report = await run_shop_sync(
        session,
        urls=["https://example.com/not-a-taobao-link"],
    )
    assert report.sellers == 0
    assert report.unresolved_links == 1
    assert report.total_items == 0


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_shop_sync_from_file(session):
    data = _xlsx([
        ("name", "url"),
        ("Кабель", "https://item.taobao.com/item.htm?id=612286553782"),
        ("Прямая ссылка на магазин", "https://demo_taobao_shop.taobao.com"),
    ])
    report = await run_shop_sync(session, file_bytes=data, filename="shops.xlsx")
    # Both rows resolve to the same seller (nick from item + nick subdomain).
    assert report.sellers == 1
    assert report.total_items == EXPECTED_SHOP_ITEMS


@pytest.mark.asyncio
async def test_shop_sync_writes_synclog_and_list_helper(session):
    await run_shop_sync(session, urls=["https://item.taobao.com/item.htm?id=612286553782"])
    logs = session.execute(
        select(SyncLog).where(SyncLog.source == "taobao_shop")
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].fetched_count == EXPECTED_SHOP_ITEMS

    items = list_shop_items(session, SELLER)
    assert len(items) == EXPECTED_SHOP_ITEMS
