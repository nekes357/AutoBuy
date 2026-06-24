"""Tmall / Taobao Open Platform async client.

Auth: MD5-signed form params (no session token needed for public item data).
Base URL: https://gw.api.taobao.com/router/rest
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import Settings
from src.tmall import methods
from src.tmall.auth import build_params
from src.tmall.schemas import TaobaoEnvelope

log = structlog.get_logger(__name__)

TAOBAO_BASE_URL = "https://gw.api.taobao.com/router/rest"


class TmallApiError(RuntimeError):
    def __init__(self, code: str | int | None, msg: str | None, body: Any = None):
        super().__init__(f"Tmall API error {code}: {msg}")
        self.code = code
        self.msg = msg
        self.body = body


class TmallClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        reraise=True,
    )
    async def _call(self, method: str, **extra: str) -> TaobaoEnvelope:
        params = build_params(
            self._settings.tmall_app_key,
            self._settings.tmall_app_secret,
            method,
            **extra,
        )
        resp = await self._http.post(TAOBAO_BASE_URL, data=params, timeout=30.0)
        if 500 <= resp.status_code < 600:
            resp.raise_for_status()
        body = resp.json()
        envelope = TaobaoEnvelope(**body)
        if envelope.error_response:
            err = envelope.error_response
            raise TmallApiError(err.code, err.msg, body)
        return envelope

    async def get_item(
        self, num_iid: int | str, fields: str = methods.DEFAULT_ITEM_FIELDS
    ) -> TaobaoEnvelope:
        return await self._call(methods.ITEM_GET, num_iid=str(num_iid), fields=fields)

    async def get_items(
        self, num_iids: list[int | str], fields: str = methods.DEFAULT_ITEM_FIELDS
    ) -> TaobaoEnvelope:
        ids_str = ",".join(str(i) for i in num_iids)
        return await self._call(methods.ITEMS_LIST_GET, num_iids=ids_str, fields=fields)

    async def search_items(
        self,
        query: str,
        page_no: int = 1,
        page_size: int = 40,
        fields: str = methods.DEFAULT_ITEM_FIELDS,
    ) -> TaobaoEnvelope:
        return await self._call(
            methods.ITEMS_SEARCH,
            q=query,
            page_no=str(page_no),
            page_size=str(page_size),
            fields=fields,
        )
