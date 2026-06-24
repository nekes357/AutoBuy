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

    async def query_by_skus(self, sku_ids) -> UnionEnvelope:
        """Return only the fixture items whose skuId was requested.

        Lets catalog-check tests exercise both the found and not-found paths:
        any SKU not present in the fixture pool comes back missing.
        """
        wanted = {str(s) for s in sku_ids}
        env = _load("union_goods_query.json")
        result = env.unwrap()
        kept = [it for it in (result.data or []) if str(it.skuId) in wanted]
        result.data = kept
        result.totalCount = len(kept)
        # Re-wrap as an envelope so the caller's .unwrap() still works.
        return UnionEnvelope(
            jd_union_open_goods_query_response={
                "code": "0",
                "result": result.model_dump_json(),
            },
            code="0",
        )
