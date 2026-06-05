from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from src.api.routes import router
from src.config import get_settings
from src.db import get_session_factory
from src.notify import send as tg_send


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
    )


async def _scheduled_jd_sync() -> None:
    from datetime import datetime, timedelta

    from src.sync import run_sync

    settings = get_settings()
    until = datetime.now(UTC)
    since = until - timedelta(minutes=settings.sync_lookback_minutes)
    with get_session_factory()() as session:
        await run_sync(session, since=since, until=until, settings=settings)


async def _scheduled_tmall_sync() -> None:
    from src.sync_tmall import run_watchlist_sync

    settings = get_settings()
    with get_session_factory()() as session:
        await run_watchlist_sync(session, settings=settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    # Schema is managed by Alembic in production (see src/cli_migrate.py
    # invoked from the Docker entrypoint). Tests bootstrap the schema
    # directly via src.db.init_db().

    scheduler: AsyncIOScheduler | None = None
    if settings.sync_interval_minutes or settings.tmall_sync_interval_minutes:
        scheduler = AsyncIOScheduler(timezone="UTC")
        if settings.sync_interval_minutes:
            scheduler.add_job(
                _scheduled_jd_sync,
                IntervalTrigger(minutes=settings.sync_interval_minutes),
                id="jd_sync",
            )
        if settings.tmall_sync_interval_minutes:
            scheduler.add_job(
                _scheduled_tmall_sync,
                IntervalTrigger(minutes=settings.tmall_sync_interval_minutes),
                id="tmall_sync",
            )
        scheduler.start()
        structlog.get_logger(__name__).info(
            "scheduler.started",
            jd_interval=settings.sync_interval_minutes,
            tmall_interval=settings.tmall_sync_interval_minutes,
        )

    await tg_send(
        "[FeedBridge] Сервис запущен",
        token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="FeedBridge — JD + Tmall → СДЭК", version="0.1.0", lifespan=lifespan)
app.include_router(router)
