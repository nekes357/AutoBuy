"""JD VOP REST client.

Thin async wrapper around the few endpoints we actually use:
  * checkNewOrder  - list new orders in a time window
  * selectJdOrder  - full order details

VOP authentication is by token in the POST body (no URL signing). All requests
go through tenacity retries on 5xx / network errors with exponential backoff.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import structlog
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import Settings
from src.jd import methods
from src.jd.auth import JdAuth

log = structlog.get_logger(__name__)


class JdApiError(RuntimeError):
    def __init__(self, code: str | int | None, message: str | None, body: Any):
        super().__init__(f"JD VOP error {code}: {message}")
        self.code = code
        self.message = message
        self.body = body


class JdClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient, auth: JdAuth) -> None:
        self._settings = settings
        self._http = http
        self._auth = auth

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        reraise=True,
    )
    async def _post(self, session: Session, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = await self._auth.get_token(session)
        body = {**payload, "token": token}

        resp = await self._http.post(
            f"{self._settings.jd_base_url}{path}",
            json=body,
            timeout=30.0,
        )
        # Retry only on transient 5xx; 4xx fail fast.
        if 500 <= resp.status_code < 600:
            resp.raise_for_status()
        if resp.status_code >= 400:
            raise JdApiError(resp.status_code, resp.text, None)

        data = resp.json()
        if isinstance(data, dict) and data.get("success") is False:
            raise JdApiError(data.get("resultCode") or data.get("code"),
                             data.get("resultMessage") or data.get("message"),
                             data)
        return data

    async def check_new_orders(
        self,
        session: Session,
        *,
        since: datetime,
        until: datetime,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        # TBD: real VOP field names for date range / pagination — confirm in cabinet.
        return await self._post(session, methods.CHECK_NEW_ORDER, {
            "startDate": since.strftime("%Y-%m-%d %H:%M:%S"),
            "endDate": until.strftime("%Y-%m-%d %H:%M:%S"),
            "pageNo": page,
            "pageSize": page_size,
        })

    async def get_order_detail(self, session: Session, jd_order_id: str) -> dict[str, Any]:
        return await self._post(session, methods.SELECT_JD_ORDER, {"jdOrderId": jd_order_id})
