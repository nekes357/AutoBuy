"""JD VOP product catalog client.

Fetches product/SKU data from JD for the CDEK feed.
Separate from order fetching — different endpoints, different sync cadence.

NOTE: All paths in src/jd/methods.py marked TBD will be confirmed
when JD B2B contract is signed and live credentials are issued.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from src.jd import methods
from src.jd.client import JdClient

log = structlog.get_logger(__name__)


class JdProductClient:
    def __init__(self, base: JdClient) -> None:
        self._base = base

    async def get_sku_detail(self, session: Session, sku_id: str) -> dict[str, Any]:
        """Fetch full details for a single SKU. Path TBD — confirm in VOP cabinet."""
        return await self._base._post(session, methods.GET_SKU_DETAIL, {"skuId": sku_id})

    async def get_skus_by_ids(self, session: Session, sku_ids: list[str]) -> dict[str, Any]:
        """Batch fetch up to N SKUs. Path and batch limit TBD."""
        return await self._base._post(
            session,
            methods.GET_SKU_BY_IDS,
            {"skuIds": ",".join(sku_ids)},
        )

    async def get_product_list(
        self,
        session: Session,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Paginated product catalog. Path and field names TBD."""
        return await self._base._post(
            session,
            methods.GET_PRODUCT_LIST,
            {"pageNo": page, "pageSize": page_size},
        )
