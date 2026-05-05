from __future__ import annotations

from collections.abc import Iterator

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db import get_session_factory


def db_session() -> Iterator[Session]:
    with get_session_factory()() as s:
        yield s


def settings_dep() -> Settings:
    return get_settings()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().service_api_key
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")
