"""Mock JD Union client — returns sample_data fixtures without real API calls."""

from __future__ import annotations

import json
from pathlib import Path

from src.jd_union.schemas import UnionEnvelope

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_data"


def _load(name: str) -> UnionEnvelope:
    return UnionEnvelope(**json.loads((SAMPLE_DIR / name).read_text("utf-8")))


class MockUnionClient:
    def __init__(self, *_, **__) -> None:
        pass

    async def search_goods(self, keyword: str, **__) -> UnionEnvelope:  # noqa: ARG002
        return _load("union_goods_query.json")

    async def goods_bigfield(self, sku_ids, fields=None) -> UnionEnvelope:  # noqa: ARG002
        return _load("union_goods_bigfield.json")
