"""JD Union async client.

Gateway: https://router.jd.com/api
Auth: MD5-signed JOS params (no OAuth session for goods queries).
Retries: 4 attempts with exponential backoff on 5xx / transport errors.

Two methods only — same shape as our Tmall client:
  * search_goods(query)        → jd.union.open.goods.query
  * goods_bigfield(sku_ids)    → jd.union.open.goods.bigfield.query
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import Settings
from src.jd_union import methods
from src.jd_union.auth import build_params
from src.jd_union.schemas import UnionEnvelope

log = structlog.get_logger(__name__)

UNION_BASE_URL = "https://router.jd.com/api"


class UnionApiError(RuntimeError):
    def __init__(self, code: str | int | None, msg: str | None, body: Any = None):
        super().__init__(f"JD Union error {code}: {msg}")
        self.code = code
        self.msg = msg
        self.body = body


class UnionClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        reraise=True,
    )
    async def _call(self, method: str, business_params: dict[str, Any]) -> UnionEnvelope:
        params = build_params(
            self._settings.jd_union_app_key,
            self._settings.jd_union_app_secret,
            method,
            business_params=business_params,
        )
        resp = await self._http.post(UNION_BASE_URL, data=params, timeout=30.0)
        if 500 <= resp.status_code < 600:
            resp.raise_for_status()
        body = resp.json()
        envelope = UnionEnvelope(**body)
        err = envelope.error()
        if err:
            raise UnionApiError(err[0], err[1], body)
        return envelope

    async def search_goods(
        self,
        keyword: str,
        *,
        page_index: int = 1,
        page_size: int = 20,
        sort_name: str | None = None,
        sort: str | None = None,
    ) -> UnionEnvelope:
        """jd.union.open.goods.query — keyword search.

        Returns up to `page_size` SKUs (max 50) with summary fields.
        """
        goods_req: dict[str, Any] = {
            "keyword": keyword,
            "pageIndex": page_index,
            "pageSize": page_size,
        }
        if sort_name:
            goods_req["sortName"] = sort_name
        if sort:
            goods_req["sort"] = sort
        return await self._call(methods.GOODS_QUERY, {"goodsReq": goods_req})

    async def query_by_skus(self, sku_ids: list[int | str]) -> UnionEnvelope:
        """jd.union.open.goods.query with skuIds — look up specific SKUs.

        Used for catalog checks: given a known list of JD SKU IDs, return
        their current price / commission / promotability. Up to 100 SKUs per
        call (JD limit); the caller is responsible for batching.
        """
        ids_str = ",".join(str(s) for s in sku_ids)
        return await self._call(methods.GOODS_QUERY, {"goodsReq": {"skuIds": ids_str}})

    async def goods_bigfield(
        self,
        sku_ids: list[int | str],
        fields: str = methods.DEFAULT_BIGFIELDS,
    ) -> UnionEnvelope:
        """jd.union.open.goods.bigfield.query — large detail fields for given SKUs.

        Returns wareQD (Q&A) and wdesc (full HTML description) per SKU,
        in addition to the standard summary fields.
        """
        return await self._call(
            methods.GOODS_BIGFIELD_QUERY,
            {
                "goodsReq": {
                    "skuIds": [int(s) for s in sku_ids],
                    "fields": fields,
                }
            },
        )
