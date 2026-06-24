"""JD Union catalog sync.

Two-step pull:
  1. search_goods(keyword) → list of SKU IDs with summary fields
  2. goods_bigfield(sku_ids) → wareQD + wdesc (large fields)

Both pages of data are merged and upserted into jd_union_products.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.currency import cny_to_rub
from src.jd_union.client import UnionClient
from src.jd_union.mock import MockUnionClient
from src.jd_union.schemas import UnionGoodsItem
from src.models import JdUnionProduct, SyncLog

log = structlog.get_logger(__name__)


ClientPair = tuple[UnionClient | MockUnionClient, httpx.AsyncClient | None]


def _build_client(settings: Settings) -> ClientPair:
    if settings.jd_union_mode == "mock":
        return MockUnionClient(), None
    http = httpx.AsyncClient()
    return UnionClient(settings, http), http


def _to_row(item: UnionGoodsItem, correlation_id: str) -> dict[str, Any]:
    price_cny = item.priceInfo.price if item.priceInfo else None
    price_rub = (
        cny_to_rub(price_cny, correlation_id=correlation_id)
        if price_cny is not None
        else None
    )
    main_image = None
    if item.imageInfo:
        urls = item.imageInfo.urls()
        if urls:
            main_image = urls[0]

    shop = item.shopInfo
    cat = item.categoryInfo
    return {
        "sku_id": str(item.skuId),
        "sku_name": item.skuName,
        "price_cny": price_cny,
        "price_rub": price_rub,
        "lowest_price_cny": item.priceInfo.lowestPrice if item.priceInfo else None,
        "brand_name": item.brandName,
        "shop_id": str(shop.shopId) if shop and shop.shopId else None,
        "shop_name": shop.shopName if shop else None,
        "category_id": str(cat.cid3) if cat and cat.cid3 else None,
        "category_name": cat.cid3Name if cat else None,
        "material_url": item.materialUrl,
        "main_image_url": main_image,
        "commission": item.commissionInfo.commission if item.commissionInfo else None,
        "commission_share": item.commissionInfo.commissionShare if item.commissionInfo else None,
        "in_order_count_30d": item.inOrderCount30Days,
        "ware_qd": item.wareQD,
        "wdesc": item.wdesc,
        "raw_payload": item.model_dump(),
    }


async def run_union_sync(
    session: Session,
    *,
    keyword: str,
    with_bigfield: bool = True,
    settings: Settings | None = None,
) -> SyncLog:
    """Search Union by keyword, optionally fetch detail fields, upsert."""
    settings = settings or get_settings()
    correlation_id = uuid.uuid4().hex
    bound = log.bind(correlation_id=correlation_id, mode=settings.jd_union_mode)
    bound.info("union_sync.start", keyword=keyword, with_bigfield=with_bigfield)

    sync_log = SyncLog(source="jd_union", correlation_id=correlation_id)
    session.add(sync_log)
    session.commit()

    client, http = _build_client(settings)
    fetched = new_count = 0
    errors: list[dict[str, Any]] = []

    try:
        search_env = await client.search_goods(keyword)
        items = search_env.unwrap().data or []

        if with_bigfield and items:
            sku_ids = [item.skuId for item in items]
            bf_env = await client.goods_bigfield(sku_ids)
            bf_items = bf_env.unwrap().data or []
            bf_by_id = {str(b.skuId): b for b in bf_items}
            # Merge wareQD / wdesc onto the search results.
            for item in items:
                bf = bf_by_id.get(str(item.skuId))
                if bf:
                    if bf.wareQD:
                        item.wareQD = bf.wareQD
                    if bf.wdesc:
                        item.wdesc = bf.wdesc

        for item in items:
            fetched += 1
            try:
                row = _to_row(item, correlation_id)
                existing = session.execute(
                    select(JdUnionProduct).where(JdUnionProduct.sku_id == row["sku_id"])
                ).scalar_one_or_none()

                if existing is None:
                    session.add(JdUnionProduct(**row))
                    new_count += 1
                else:
                    for k, v in row.items():
                        setattr(existing, k, v)
                session.commit()
            except Exception as exc:  # noqa: BLE001
                bound.exception("union_sync.persist_failed", sku_id=str(item.skuId))
                errors.append({"sku_id": str(item.skuId), "error": str(exc)})
                session.rollback()

    finally:
        if http is not None:
            await http.aclose()

    sync_log.fetched_count = fetched
    sync_log.new_count = new_count
    sync_log.error_count = len(errors)
    sync_log.errors = errors or None
    sync_log.finished_at = datetime.now(UTC)
    session.commit()

    bound.info("union_sync.done", fetched=fetched, new=new_count, errors=len(errors))
    return sync_log
