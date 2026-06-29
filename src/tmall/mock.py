"""Mock Tmall client — returns sample_data fixtures without real API calls."""

from __future__ import annotations

import json
from pathlib import Path

from src.tmall.schemas import TaobaoEnvelope

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_data"


def _load(name: str) -> TaobaoEnvelope:
    return TaobaoEnvelope(**json.loads((SAMPLE_DIR / name).read_text("utf-8")))


class MockTmallClient:
    def __init__(self, *_, **__) -> None:
        pass

    async def get_item(self, num_iid: int | str, **__) -> TaobaoEnvelope:
        env = _load("tmall_item_get.json")
        return env

    async def get_items(self, num_iids: list[int | str], **__) -> TaobaoEnvelope:
        return _load("tmall_items_list.json")

    async def search_items(self, query: str, **__) -> TaobaoEnvelope:
        return _load("tmall_items_list.json")

    async def get_shop(self, nick: str, **__) -> TaobaoEnvelope:  # noqa: ARG002
        return _load("taobao_shop_get.json")

    async def get_shop_items(self, nick: str, page_no: int = 1, **__) -> TaobaoEnvelope:  # noqa: ARG002
        # Page-aware: page 1 has 2 items, page 2 has 1, page 3+ is empty (stops pagination).
        if page_no <= 1:
            return _load("taobao_shop_items_page1.json")
        if page_no == 2:
            return _load("taobao_shop_items_page2.json")
        return _load("taobao_shop_items_empty.json")
