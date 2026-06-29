"""Taobao shop data via Apify web-scraping actors.

Instead of the official Taobao Open Platform API (which requires app
registration and review), this client runs an Apify actor that scrapes
Taobao/Tmall product pages directly.

Default actor: zen-studio/taobao-seller-products-scraper
Input:  {"sellers": ["https://shop123.taobao.com"], "maxItemsPerSeller": 5000}
Output: [{itemId, title, shopName, price, mainPictureUrl, url, ...}, ...]

Requires only an Apify API token (free tier gives 5 USD/month).

The client implements the same interface as TmallClient / MockTmallClient
so the shop-sync orchestrator works unchanged.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from src.config import Settings
from src.tmall.schemas import TaobaoEnvelope

log = structlog.get_logger(__name__)

APIFY_API = "https://api.apify.com/v2"
DEFAULT_ACTOR = "zen-studio/taobao-seller-products-scraper"


class ApifyError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"Apify error {status}: {detail}")
        self.status = status
        self.detail = detail


class ApifyTaobaoClient:
    """Fetch Taobao item/shop data through an Apify scraper actor."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._token = settings.apify_api_token
        self._actor = settings.apify_taobao_actor or DEFAULT_ACTOR
        self._http = http
        self._shop_cache: dict[str, list[dict[str, Any]]] = {}

    async def _run_actor(
        self,
        input_data: dict[str, Any],
        timeout: float = 300,
    ) -> list[dict[str, Any]]:
        url = f"{APIFY_API}/acts/{self._actor}/run-sync-get-dataset-items"
        log.info(
            "apify.run_actor",
            actor=self._actor,
            input_keys=list(input_data.keys()),
        )
        resp = await self._http.post(
            url,
            params={"token": self._token},
            json=input_data,
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise ApifyError(resp.status_code, resp.text[:300])
        data = resp.json()
        if isinstance(data, list):
            return data
        return []

    @staticmethod
    def _map_item(raw: dict[str, Any]) -> dict[str, Any]:
        num_iid = raw.get("itemId") or raw.get("id") or raw.get("num_iid")
        price = raw.get("discountPrice") or raw.get("price")
        return {
            "num_iid": str(num_iid) if num_iid is not None else None,
            "title": raw.get("title") or raw.get("titleOriginal"),
            "nick": (
                raw.get("shopName")
                or raw.get("sellerNick")
                or raw.get("nick")
            ),
            "price": str(price) if price is not None else None,
            "pic_url": (
                raw.get("mainPictureUrl")
                or raw.get("imageUrl")
                or raw.get("pic_url")
            ),
            "detail_url": raw.get("url") or raw.get("detail_url"),
            "num": raw.get("stock") or raw.get("quantity") or raw.get("num"),
            "cid": raw.get("categoryId") or raw.get("cid"),
        }

    async def get_item(self, num_iid: int | str, **__: Any) -> TaobaoEnvelope:
        results = await self._run_actor({
            "sellers": [f"itemId:{num_iid}"],
            "maxItemsPerSeller": 1,
        })
        if results:
            mapped = self._map_item(results[0])
            return TaobaoEnvelope(**{"item_get_response": {"item": mapped}})
        return TaobaoEnvelope()

    async def get_shop(self, nick: str, **__: Any) -> TaobaoEnvelope:
        if nick in self._shop_cache:
            first = self._shop_cache[nick][0] if self._shop_cache[nick] else {}
            shop_name = first.get("shopName") or nick
            shop_id = first.get("shopId")
            return TaobaoEnvelope(**{
                "shop_get_response": {
                    "shop": {
                        "nick": nick,
                        "title": shop_name,
                        "sid": shop_id,
                    },
                },
            })
        return TaobaoEnvelope(**{
            "shop_get_response": {"shop": {"nick": nick}},
        })

    async def get_shop_items(
        self,
        nick: str,
        page_no: int = 1,
        page_size: int = 40,
        **__: Any,
    ) -> TaobaoEnvelope:
        if nick not in self._shop_cache:
            items = await self._run_actor(
                {
                    "sellers": [nick],
                    "maxItemsPerSeller": 5000,
                    "sort": "best_selling",
                },
                timeout=600,
            )
            self._shop_cache[nick] = items
            log.info("apify.shop_scraped", nick=nick, items=len(items))

        all_items = self._shop_cache[nick]
        start = (page_no - 1) * page_size
        page = all_items[start : start + page_size]
        mapped = [self._map_item(i) for i in page]
        return TaobaoEnvelope(**{
            "items_search_response": {
                "items": {"item": mapped},
                "total_results": len(all_items),
            },
        })
