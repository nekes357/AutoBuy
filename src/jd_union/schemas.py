"""Pydantic models for JD Union goods responses.

Quirk: JD Union wraps the actual payload twice. The HTTP response is:

    { "jd_union_open_goods_query_response": {
        "result": "{\\"code\\":200, \\"data\\":[...]}"  # <- JSON string, not object
      }
    }

So we get the outer envelope key, then json.loads the `result` string a second
time to get the real data. `UnionEnvelope.unwrap()` does that for both
goods.query and goods.bigfield.query.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict


class UnionImageInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    imageList: list[dict[str, Any]] | None = None

    def urls(self) -> list[str]:
        return [img.get("url") for img in (self.imageList or []) if img.get("url")]


class UnionPriceInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    price: float | None = None         # current price
    lowestPrice: float | None = None
    lowestPriceType: int | None = None


class UnionCategoryInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    cid1: int | None = None
    cid2: int | None = None
    cid3: int | None = None
    cid1Name: str | None = None
    cid2Name: str | None = None
    cid3Name: str | None = None


class UnionCommissionInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    commission: float | None = None
    commissionShare: float | None = None
    couponCommission: float | None = None


class UnionShopInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    shopId: int | None = None
    shopName: str | None = None
    shopLevel: float | None = None


class UnionGoodsItem(BaseModel):
    """Single goods record returned by goods.query or bigfield.query."""

    model_config = ConfigDict(extra="allow")

    skuId: int | str
    skuName: str | None = None
    spuid: int | str | None = None
    materialUrl: str | None = None
    brandCode: str | None = None
    brandName: str | None = None
    owner: str | None = None
    inOrderCount30Days: int | None = None
    inOrderComm30Days: float | None = None

    imageInfo: UnionImageInfo | None = None
    priceInfo: UnionPriceInfo | None = None
    categoryInfo: UnionCategoryInfo | None = None
    commissionInfo: UnionCommissionInfo | None = None
    shopInfo: UnionShopInfo | None = None

    # bigfield extras (only present when fields=wareQD,wdesc requested).
    wareQD: str | None = None
    wdesc: str | None = None


class UnionResult(BaseModel):
    """Parsed `result` JSON string."""

    model_config = ConfigDict(extra="allow")

    code: int | None = None
    message: str | None = None
    requestId: str | None = None
    totalCount: int | None = None
    data: list[UnionGoodsItem] | None = None


class UnionEnvelope(BaseModel):
    """Top-level JD Union response. The actual response key is method-specific
    (jd_union_open_goods_query_response, jd_union_open_goods_bigfield_query_response, ...)
    so we accept anything via extra='allow' and dig in via `unwrap()`."""

    model_config = ConfigDict(extra="allow")

    def unwrap(self) -> UnionResult:
        for value in (self.model_extra or {}).values():
            if isinstance(value, dict) and "result" in value:
                raw = value["result"]
                payload = json.loads(raw) if isinstance(raw, str) else raw
                return UnionResult(**payload)
        return UnionResult()

    def error(self) -> tuple[str | int | None, str | None] | None:
        ok_codes = ("0", 0, "200", 200)
        for value in (self.model_extra or {}).values():
            if isinstance(value, dict):
                code = value.get("code")
                if code and code not in ok_codes:
                    return code, value.get("zh_desc") or value.get("en_desc")
        return None
