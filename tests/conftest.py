from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("JD_MODE", "mock")
    monkeypatch.setenv("CNY_RUB_RATE", "12.5")
    monkeypatch.setenv("SERVICE_API_KEY", "test-key")

    from src.config import get_settings
    from src.db import init_db, reset_engine

    get_settings.cache_clear()
    reset_engine()
    init_db()
    yield
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture()
def session(_env) -> Iterator[Session]:
    from src.db import get_session_factory

    with get_session_factory()() as s:
        yield s
