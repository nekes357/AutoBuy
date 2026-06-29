"""Taobao seller-shop sync.

Input is a file (xlsx/csv) of Taobao links — item links and/or shop links.
For each:
  * item link  (item.taobao.com/item.htm?id=X) -> resolve the seller via
    item.get, which returns the shop's `nick`;
  * shop link  (myshop.taobao.com, *.tmall.com, view_shop.htm?user_number_id)
    -> use the nick / shop id directly.

Sellers are de-duplicated (a file with 200 items from one shop hits the shop
once), then every seller's full catalogue is pulled page by page and upserted
into tmall_items, tagged with seller_nick.

Usage:
    await run_shop_sync(session, file_bytes=data, filename="shops.xlsx")
    await run_shop_sync(session, urls=["https://item.taobao.com/item.htm?id=..."])
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.currency import cny_to_rub
from src.fileio import read_tabular
from src.models import SyncLog, TmallItem
from src.tmall.apify_client import ApifyTaobaoClient
from src.tmall.client import TmallClient
from src.tmall.links import parse_ref
from src.tmall.mock import MockTmallClient
from src.tmall.schemas import TaobaoItem

log = structlog.get_logger(__name__)

# Stop paginating a shop after this many pages (safety cap).
MAX_SHOP_PAGES = 100
SHOP_PAGE_SIZE = 40

# Column names we look for when a file is provided.
_URL_COLUMNS = ("url", "link", "active_url", "any_url", "ссылка", "товар")

AnyTaobaoClient = TmallClient | MockTmallClient | ApifyTaobaoClient
ClientPair = tuple[AnyTaobaoClient, httpx.AsyncClient | None]


@dataclass
class ShopResult:
    nick: str | None = None
    shop_id: str | None = None
    shop_title: str | None = None
    items_synced: int = 0
    new_items: int = 0
    error: str | None = None


@dataclass
class ShopSyncReport:
    correlation_id: str = ""
    sellers: int = 0
    total_items: int = 0
    new_items: int = 0
    unresolved_links: int = 0     # links we couldn't map to any seller
    shops: list[ShopResult] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "sellers": self.sellers,
            "total_items": self.total_items,
            "new_items": self.new_items,
            "unresolved_links": self.unresolved_links,
            "shops": [
                {
                    "nick": s.nick,
                    "shop_id": s.shop_id,
                    "shop_title": s.shop_title,
                    "items_synced": s.items_synced,
                    "new_items": s.new_items,
                    "error": s.error,
                }
                for s in self.shops
            ],
        }


def _build_client(settings: Settings) -> ClientPair:
    if settings.tmall_mode == "mock":
        return MockTmallClient(), None
    http = httpx.AsyncClient()
    if settings.tmall_mode == "apify":
        return ApifyTaobaoClient(settings, http), http
    return TmallClient(settings, http), http


def _extract_urls_from_file(data: bytes, filename: str) -> list[str]:
    rows = read_tabular(data, filename)
    if not rows:
        return []
    headers = [str(c).lower().strip() if c is not None else "" for c in rows[0]]
    url_indices = [headers.index(c) for c in _URL_COLUMNS if c in headers]
    # If no header matched, scan every cell for a taobao/tmall URL instead.
    urls: list[str] = []
    for raw in rows[1:]:
        if raw is None:
            continue
        if url_indices:
            for i in url_indices:
                if i < len(raw) and raw[i]:
                    urls.append(str(raw[i]).strip())
        else:
            for cell in raw:
                if cell and ("taobao.com" in str(cell) or "tmall.com" in str(cell)):
                    urls.append(str(cell).strip())
    return [u for u in urls if u]


async def _resolve_sellers(
    client: AnyTaobaoClient,
    urls: list[str],
    report: ShopSyncReport,
) -> dict[str, str | None]:
    """Map URLs to unique sellers. Returns {nick_or_shopid: shop_title_or_None}.

    Item links are resolved through item.get to discover the seller nick.
    """
    sellers: dict[str, str | None] = {}
    for url in urls:
        ref = parse_ref(url)
        nick = ref.shop_nick or ref.shop_id
        if nick is None and ref.item_id:
            try:
                env = await client.get_item(ref.item_id)
                item = env.item()
                nick = item.nick if item else None
            except Exception as exc:  # noqa: BLE001
                log.warning("shop_sync.item_resolve_failed", url=url, error=str(exc))
        if nick:
            sellers.setdefault(nick, None)
        else:
            report.unresolved_links += 1
    return sellers


def _to_row(item: TaobaoItem, nick: str, correlation_id: str) -> dict[str, Any]:
    price_cny: float | None = None
    try:
        price_cny = float(item.price) if item.price else None
    except (ValueError, TypeError):
        price_cny = None
    price_rub = (
        cny_to_rub(price_cny, correlation_id=correlation_id)
        if price_cny is not None
        else None
    )

    return {
        "num_iid": str(item.num_iid),
        "title": item.title,
        "seller_nick": item.nick or nick,
        "price_cny": price_cny,
        "price_rub": price_rub,
        "stock": item.num,
        "pic_url": item.pic_url,
        "detail_url": item.detail_url,
        "category_id": str(item.cid) if item.cid is not None else None,
        "raw_payload": item.model_dump(),
    }


async def _sync_one_shop(
    client: AnyTaobaoClient,
    session: Session,
    nick: str,
    correlation_id: str,
) -> ShopResult:
    result = ShopResult(nick=nick)
    try:
        shop_env = await client.get_shop(nick)
        shop = shop_env.shop()
        if shop:
            result.shop_title = shop.title
            result.shop_id = str(shop.sid) if shop.sid is not None else None
    except Exception as exc:  # noqa: BLE001
        log.warning("shop_sync.shop_get_failed", nick=nick, error=str(exc))

    total_results: int | None = None
    for page in range(1, MAX_SHOP_PAGES + 1):
        env = await client.get_shop_items(nick, page_no=page, page_size=SHOP_PAGE_SIZE)
        if total_results is None:
            total_results = env.total_results()
        items = env.items()
        if not items:
            break
        for item in items:
            row = _to_row(item, nick, correlation_id)
            existing = session.get(TmallItem, row["num_iid"])
            if existing is None:
                session.add(TmallItem(**row))
                result.new_items += 1
            else:
                for k, v in row.items():
                    setattr(existing, k, v)
            result.items_synced += 1
        session.commit()
        # Stop when we've collected everything the API said it has.
        if total_results is not None and result.items_synced >= total_results:
            break

    return result


async def run_shop_sync(
    session: Session,
    *,
    file_bytes: bytes | None = None,
    filename: str | None = None,
    urls: list[str] | None = None,
    settings: Settings | None = None,
) -> ShopSyncReport:
    """Sync every Taobao seller referenced by a file or an explicit URL list."""
    settings = settings or get_settings()
    correlation_id = uuid.uuid4().hex
    report = ShopSyncReport(correlation_id=correlation_id)
    bound = log.bind(correlation_id=correlation_id, mode=settings.tmall_mode)

    all_urls: list[str] = list(urls or [])
    if file_bytes is not None:
        all_urls.extend(_extract_urls_from_file(file_bytes, filename or "upload.csv"))
    if not all_urls:
        raise ValueError("Provide file_bytes or urls")

    bound.info("shop_sync.start", links=len(all_urls))

    sync_log = SyncLog(source="taobao_shop", correlation_id=correlation_id)
    session.add(sync_log)
    session.commit()

    client, http = _build_client(settings)
    try:
        sellers = await _resolve_sellers(client, all_urls, report)
        report.sellers = len(sellers)

        for nick in sellers:
            res = await _sync_one_shop(client, session, nick, correlation_id)
            report.shops.append(res)
            report.total_items += res.items_synced
            report.new_items += res.new_items
    finally:
        if http is not None:
            await http.aclose()

    sync_log.fetched_count = report.total_items
    sync_log.new_count = report.new_items
    sync_log.error_count = sum(1 for s in report.shops if s.error)
    sync_log.finished_at = datetime.now(UTC)
    session.commit()

    bound.info(
        "shop_sync.done",
        sellers=report.sellers,
        total_items=report.total_items,
        new_items=report.new_items,
        unresolved=report.unresolved_links,
    )
    return report


def list_shop_items(session: Session, seller_nick: str, limit: int = 200) -> list[TmallItem]:
    return (
        session.execute(
            select(TmallItem)
            .where(TmallItem.seller_nick == seller_nick)
            .order_by(TmallItem.num_iid)
            .limit(limit)
        )
        .scalars()
        .all()
    )
