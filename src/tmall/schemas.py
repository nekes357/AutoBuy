"""Pydantic models for Taobao Open Platform responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class TaobaoSku(BaseModel):
    model_config = ConfigDict(extra="allow")

    sku_id: str | None = None
    properties: str | None = None
    quantity: int | None = None
    price: str | None = None


class TaobaoItemImg(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str | None = None


class TaobaoItem(BaseModel):
    """Single item from taobao.item.get or taobao.items.list.get."""

    model_config = ConfigDict(extra="allow")

    num_iid: int | str
    title: str | None = None
    price: str | None = None
    pic_url: str | None = None
    detail_url: str | None = None
    num: int | None = None
    cid: int | str | None = None
    props_name: str | None = None
    modified: str | None = None

    skus: dict[str, Any] | None = None
    item_imgs: dict[str, Any] | None = None

    def image_urls(self) -> list[str]:
        imgs = self.item_imgs or {}
        raw = imgs.get("item_img", [])
        if isinstance(raw, dict):
            raw = [raw]
        return [i.get("url") for i in raw if i.get("url")]

    def sku_list(self) -> list[dict[str, Any]]:
        skus = self.skus or {}
        raw = skus.get("sku", [])
        if isinstance(raw, dict):
            raw = [raw]
        return raw


class TaobaoError(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str | int | None = None
    msg: str | None = None
    sub_code: str | None = None
    sub_msg: str | None = None


class TaobaoEnvelope(BaseModel):
    """Top-level response wrapper. Key varies by method."""

    model_config = ConfigDict(extra="allow")

    error_response: TaobaoError | None = None

    def item(self) -> TaobaoItem | None:
        data = self.model_extra or {}
        for key in data.values():
            if isinstance(key, dict) and "num_iid" in key:
                return TaobaoItem(**key)
        return None

    def items(self) -> list[TaobaoItem]:
        data = self.model_extra or {}
        for key in data.values():
            if isinstance(key, dict):
                raw_items = key.get("item", [])
                if isinstance(raw_items, list):
                    return [TaobaoItem(**i) for i in raw_items if isinstance(i, dict)]
        return []
