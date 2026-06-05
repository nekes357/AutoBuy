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
