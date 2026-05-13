from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.api.deps import db_session, require_api_key, settings_dep
from src.config import Settings
from src.models import JdOrder, SyncLog
from src.sync import run_sync

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/sync/run", dependencies=[Depends(require_api_key)])
async def sync_run(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    session: Session = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    until = until or datetime.now(UTC)
    since = since or (until - timedelta(minutes=settings.sync_lookback_minutes))
    sync_log = await run_sync(session, since=since, until=until, settings=settings)
    return {
        "id": sync_log.id,
        "correlation_id": sync_log.correlation_id,
        "fetched": sync_log.fetched_count,
        "new": sync_log.new_count,
        "errors": sync_log.error_count,
        "since": since.isoformat(),
        "until": until.isoformat(),
    }


@router.get("/sync/logs", dependencies=[Depends(require_api_key)])
def sync_logs(limit: int = 20, session: Session = Depends(db_session)) -> list[dict[str, Any]]:
    rows = session.execute(select(SyncLog).order_by(desc(SyncLog.id)).limit(limit)).scalars().all()
    return [
        {
            "id": r.id,
            "correlation_id": r.correlation_id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "since": r.since.isoformat() if r.since else None,
            "until": r.until.isoformat() if r.until else None,
            "fetched": r.fetched_count,
            "new": r.new_count,
            "errors": r.error_count,
        }
        for r in rows
    ]


@router.get("/orders", dependencies=[Depends(require_api_key)])
def list_orders(
    status: str | None = None,
    limit: int = 50,
    session: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    stmt = select(JdOrder).order_by(desc(JdOrder.fetched_at)).limit(limit)
    if status:
        stmt = stmt.where(JdOrder.status == status)
    rows = session.execute(stmt).scalars().all()
    return [
        {
            "jd_order_id": r.jd_order_id,
            "status": r.status,
            "recipient_name": r.recipient_name,
            "recipient_phone": r.recipient_phone,
            "total_cny": r.total_cny,
            "total_rub": r.total_rub,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in rows
    ]


@router.get("/orders/{jd_order_id}", dependencies=[Depends(require_api_key)])
def order_detail(jd_order_id: str, session: Session = Depends(db_session)) -> dict[str, Any]:
    row = session.get(JdOrder, jd_order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    return {
        "jd_order_id": row.jd_order_id,
        "status": row.status,
        "recipient_name": row.recipient_name,
        "recipient_phone": row.recipient_phone,
        "total_cny": row.total_cny,
        "total_rub": row.total_rub,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        "raw_payload": row.raw_payload,
    }


@router.api_route("/jd/callback", methods=["GET", "POST", "HEAD"])
async def jd_callback(request: Request) -> dict[str, Any]:
    """Whitelisted endpoint for JD VOP. Logs and returns 200.

    JD's exact ping/callback contract is TBD until app registration; this stub
    is sufficient to register the URL and unblock issuance of production keys.
    """
    import structlog

    log = structlog.get_logger(__name__)
    body: Any = None
    if request.method != "GET":
        try:
            body = await request.json()
        except Exception:
            body = (await request.body()).decode("utf-8", errors="replace")
    log.info("jd.callback", method=request.method, query=dict(request.query_params), body=body)
    return {"status": "ok"}
