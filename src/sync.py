"""Sync orchestrator: pull JD orders for a window, persist to DB.

Idempotent on jd_order_id: existing rows are updated, new rows inserted.
CDEK push is intentionally out of scope on this iteration.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.currency import cny_to_rub
from src.jd.auth import JdAuth
from src.jd.client import JdClient
from src.jd.mock import MockJdClient
from src.models import JdOrder, SyncLog
from src.notify import _fmt_sync_result
from src.notify import send as tg_send

log = structlog.get_logger(__name__)


def _build_client(settings: Settings) -> tuple[JdClient | MockJdClient, httpx.AsyncClient | None]:
    if settings.jd_mode == "mock":
        return MockJdClient(), None
    http = httpx.AsyncClient()
    auth = JdAuth(settings, http)
    return JdClient(settings, http, auth), http


def _extract_order_ids(envelope: dict[str, Any]) -> list[str]:
    """Best-effort extraction of jd_order_id list from checkNewOrder response.

    VOP envelope shape varies; supports both {"result": [...]} and flat shapes.
    """
    if not isinstance(envelope, dict):
        return []
    candidates = envelope.get("result") or envelope.get("data") or envelope.get("orderIds")
    if isinstance(candidates, list):
        out: list[str] = []
        for item in candidates:
            if isinstance(item, str | int):
                out.append(str(item))
            elif isinstance(item, dict):
                jd_id = item.get("jdOrderId") or item.get("orderId") or item.get("id")
                if jd_id:
                    out.append(str(jd_id))
        return out
    if isinstance(candidates, dict):
        nested = candidates.get("orderIdList") or candidates.get("orders") or []
        return [str(x) if not isinstance(x, dict) else str(x.get("jdOrderId")) for x in nested]
    return []


def _summarize(detail_envelope: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    """Pull a few human-readable fields out of an order detail for the table."""
    result = detail_envelope.get("result") if isinstance(detail_envelope, dict) else None
    if not isinstance(result, dict):
        result = detail_envelope if isinstance(detail_envelope, dict) else {}

    name = result.get("name") or result.get("consigneeName")
    phone = result.get("mobile") or result.get("phone")
    # Use explicit None check: `0.0 or x` returns x because 0.0 is falsy.
    total_cny = result.get("orderPrice")
    if total_cny is None:
        total_cny = result.get("totalPrice")
    total_rub: float | None = None
    if isinstance(total_cny, int | float):
        total_rub = cny_to_rub(float(total_cny), correlation_id=correlation_id)
    return {
        "recipient_name": name,
        "recipient_phone": phone,
        "total_cny": float(total_cny) if isinstance(total_cny, int | float) else None,
        "total_rub": total_rub,
    }


async def run_sync(
    session: Session,
    *,
    since: datetime,
    until: datetime,
    settings: Settings | None = None,
) -> SyncLog:
    settings = settings or get_settings()
    correlation_id = uuid.uuid4().hex
    bound = log.bind(
        correlation_id=correlation_id,
        since=since.isoformat(),
        until=until.isoformat(),
    )
    bound.info("sync.start", mode=settings.jd_mode)

    sync_log = SyncLog(since=since, until=until, correlation_id=correlation_id)
    session.add(sync_log)
    session.commit()

    client, http = _build_client(settings)
    errors: list[dict[str, Any]] = []
    fetched = 0
    new_count = 0
    MAX_PAGES = 100  # safety cap; JD won't realistically return this many pages per window
    sem = asyncio.Semaphore(max(1, settings.sync_concurrency))

    async def _fetch_one(jd_id: str) -> tuple[str, dict[str, Any] | None, Exception | None]:
        async with sem:
            try:
                detail = await client.get_order_detail(session, jd_id)
                return jd_id, detail, None
            except Exception as exc:  # noqa: BLE001
                return jd_id, None, exc

    try:
        page = 1
        while page <= MAX_PAGES:
            listing = await client.check_new_orders(session, since=since, until=until, page=page)
            order_ids = _extract_order_ids(listing)
            bound.info("sync.page_listed", page=page, count=len(order_ids))
            if not order_ids:
                break

            # Fetch order details concurrently (network-bound). DB writes below
            # stay sequential because SQLAlchemy's Session is not async-safe to
            # share across tasks.
            results = await asyncio.gather(*(_fetch_one(jd_id) for jd_id in order_ids))

            for jd_id, detail, exc in results:
                fetched += 1
                if exc is not None or detail is None:
                    bound.error("sync.order_failed", jd_order_id=jd_id, error=str(exc))
                    errors.append({"jd_order_id": jd_id, "error": str(exc)})
                    continue
                try:
                    summary = _summarize(detail, correlation_id)
                    existing = session.execute(
                        select(JdOrder).where(JdOrder.jd_order_id == jd_id)
                    ).scalar_one_or_none()

                    if existing is None:
                        session.add(JdOrder(
                            jd_order_id=jd_id,
                            status="fetched",
                            raw_payload=detail,
                            **summary,
                        ))
                        new_count += 1
                    else:
                        existing.raw_payload = detail
                        for k, v in summary.items():
                            setattr(existing, k, v)
                    session.commit()
                except Exception as exc:  # noqa: BLE001
                    bound.exception("sync.persist_failed", jd_order_id=jd_id)
                    errors.append({"jd_order_id": jd_id, "error": str(exc)})
                    session.rollback()

            page += 1
    finally:
        if http is not None:
            await http.aclose()

    sync_log.fetched_count = fetched
    sync_log.new_count = new_count
    sync_log.error_count = len(errors)
    sync_log.errors = errors or None
    sync_log.finished_at = datetime.now(UTC)
    session.commit()

    bound.info("sync.done", fetched=fetched, new=new_count, errors=len(errors))

    has_errors = len(errors) > 0
    if has_errors or settings.telegram_notify_success:
        await tg_send(
            _fmt_sync_result("JD", fetched, new_count, len(errors)),
            token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )

    return sync_log
