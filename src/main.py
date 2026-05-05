from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from src.api.routes import router
from src.config import get_settings
from src.db import get_session_factory, init_db


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
    )


async def _scheduled_sync() -> None:
    from datetime import datetime, timedelta, timezone

    from src.sync import run_sync

    settings = get_settings()
    until = datetime.now(timezone.utc)
    since = until - timedelta(minutes=settings.sync_lookback_minutes)
    with get_session_factory()() as session:
        await run_sync(session, since=since, until=until, settings=settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    init_db()

    scheduler: AsyncIOScheduler | None = None
    if settings.sync_interval_minutes:
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(_scheduled_sync, IntervalTrigger(minutes=settings.sync_interval_minutes))
        scheduler.start()
        structlog.get_logger(__name__).info("scheduler.started", interval=settings.sync_interval_minutes)

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AutoBuy — JD VOP connector", version="0.1.0", lifespan=lifespan)
app.include_router(router)
