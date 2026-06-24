"""Tmall catalog sync orchestrator.

Pull item data from Taobao Open Platform (taoworld), normalize, upsert to DB.
Supports two modes:
  - by_ids:   sync a specific list of num_iid values
  - by_query: search by keyword / category, sync results

Usage:
    await run_tmall_sync(session, item_ids=[123, 456])
    await run_tmall_sync(session, query="шуруповерт")
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.currency import cny_to_rub
from src.models import CatalogWatchlistEntry, SyncLog, TmallItem
from src.notify import _fmt_sync_result
from src.notify import send as tg_send
from src.tmall.client import TmallClient
from src.tmall.mock import MockTmallClient
from src.tmall.schemas import TaobaoItem

log = structlog.get_logger(__name__)


def _build_client(
    settings: Settings,
) -> tuple[TmallClient | MockTmallClient, httpx.AsyncClient | None]:
    if settings.tmall_mode == "mock":
        return MockTmallClient(), None
    http = httpx.AsyncClient()
    return TmallClient(settings, http), http


def _to_row(item: TaobaoItem, correlation_id: str) -> dict[str, Any]:
    price_cny: float | None = None
    with contextlib.suppress(ValueError, TypeError):
        price_cny = float(item.price) if item.price else None

    price_rub: float | None = None
    if price_cny is not None:
        price_rub = cny_to_rub(price_cny, correlation_id=correlation_id)

    return {
        "num_iid": str(item.num_iid),
        "title": item.title,
        "price_cny": price_cny,
        "price_rub": price_rub,
        "stock": item.num,
        "pic_url": item.pic_url,
        "detail_url": item.detail_url,
        "category_id": str(item.cid) if item.cid is not None else None,
        "raw_payload": item.model_dump(),
    }


async def run_tmall_sync(
    session: Session,
    *,
    item_ids: list[int | str] | None = None,
    query: str | None = None,
    settings: Settings | None = None,
) -> SyncLog:
    """Sync Tmall items by explicit IDs or by search query."""
    if not item_ids and not query:
        raise ValueError("Provide item_ids or query")

    settings = settings or get_settings()
    correlation_id = uuid.uuid4().hex
    bound = log.bind(correlation_id=correlation_id, mode=settings.tmall_mode)
    bound.info("tmall_sync.start", item_ids=item_ids, query=query)

    sync_log = SyncLog(source="tmall", correlation_id=correlation_id)
    session.add(sync_log)
    session.commit()

    client, http = _build_client(settings)
    fetched = new_count = 0
    errors: list[dict[str, Any]] = []

    try:
        items: list[TaobaoItem] = []

        if item_ids:
            batch_size = settings.tmall_batch_size
            for i in range(0, len(item_ids), batch_size):
                batch = item_ids[i : i + batch_size]
                envelope = await client.get_items(batch)
                items.extend(envelope.items())
        elif query:
            envelope = await client.search_items(query)
            items.extend(envelope.items())

        for item in items:
            fetched += 1
            try:
                row_data = _to_row(item, correlation_id)
                existing = session.execute(
                    select(TmallItem).where(TmallItem.num_iid == row_data["num_iid"])
                ).scalar_one_or_none()

                if existing is None:
                    session.add(TmallItem(**row_data))
                    new_count += 1
                else:
                    for k, v in row_data.items():
                        setattr(existing, k, v)
                session.commit()
            except Exception as exc:  # noqa: BLE001
                bound.exception("tmall_sync.persist_failed", num_iid=str(item.num_iid))
                errors.append({"num_iid": str(item.num_iid), "error": str(exc)})
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

    bound.info("tmall_sync.done", fetched=fetched, new=new_count, errors=len(errors))

    has_errors = len(errors) > 0
    if has_errors or settings.telegram_notify_success:
        await tg_send(
            _fmt_sync_result("Tmall", fetched, new_count, len(errors)),
            token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )

    return sync_log


async def run_watchlist_sync(session: Session, *, settings: Settings | None = None) -> None:
    """Run sync for every enabled entry in catalog_watchlist."""
    settings = settings or get_settings()
    entries = session.execute(
        select(CatalogWatchlistEntry).where(CatalogWatchlistEntry.enabled.is_(True))
    ).scalars().all()

    for entry in entries:
        try:
            sync_log = await run_tmall_sync(
                session,
                item_ids=None,
                query=entry.query or entry.category_name,
                settings=settings,
            )
            entry.last_synced_at = datetime.now(UTC)
            entry.last_error = None
            # Count items belonging to this category in DB.
            if entry.category_id:
                count = session.query(TmallItem).filter(
                    TmallItem.category_id == entry.category_id
                ).count()
            else:
                count = sync_log.fetched_count
            entry.item_count = count
        except Exception as exc:  # noqa: BLE001
            entry.last_error = str(exc)[:500]
            log.error("watchlist_sync.entry_failed", entry_id=entry.id, error=str(exc))
        finally:
            session.commit()
