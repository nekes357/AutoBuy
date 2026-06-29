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
    nick: str | None = None          # seller nickname (shop owner)
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


class TaobaoShop(BaseModel):
    """Shop record from taobao.shop.get."""

    model_config = ConfigDict(extra="allow")

    sid: int | str | None = None      # shop id
    cid: int | str | None = None
    title: str | None = None
    nick: str | None = None           # seller nickname
    desc: str | None = None
    pic_path: str | None = None
    created: str | None = None
    modified: str | None = None


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
        """Single item from item.get. Tolerates both the flat shape and the
        nested item_get_response -> item: {...} shape."""
        for value in (self.model_extra or {}).values():
            if not isinstance(value, dict):
                continue
            if "num_iid" in value:
                return TaobaoItem(**value)
            inner = value.get("item")
            if isinstance(inner, dict) and "num_iid" in inner:
                return TaobaoItem(**inner)
        return None

    def items(self) -> list[TaobaoItem]:
        """Extract the item list, tolerating both response shapes:
        - items.list.get:  response -> item: [...]
        - items.search:    response -> items -> item: [...]
        """
        for value in (self.model_extra or {}).values():
            if not isinstance(value, dict):
                continue
            raw_items = value.get("item")
            if raw_items is None and isinstance(value.get("items"), dict):
                raw_items = value["items"].get("item")
            if isinstance(raw_items, dict):  # single item comes back unwrapped
                raw_items = [raw_items]
            if isinstance(raw_items, list):
                return [TaobaoItem(**i) for i in raw_items if isinstance(i, dict)]
        return []

    def total_results(self) -> int | None:
        for value in (self.model_extra or {}).values():
            if isinstance(value, dict) and "total_results" in value:
                try:
                    return int(value["total_results"])
                except (TypeError, ValueError):
                    return None
        return None

    def shop(self) -> TaobaoShop | None:
        for value in (self.model_extra or {}).values():
            if isinstance(value, dict):
                raw = value.get("shop")
                if isinstance(raw, dict):
                    return TaobaoShop(**raw)
                if "sid" in value or "nick" in value:
                    return TaobaoShop(**value)
        return None
