"""Mock JD client used when JD_MODE=mock.

Reads canned responses from src/jd/sample_data/ so the full pipeline can run
without real JD credentials. Same async signature as JdClient.

The sample data deliberately covers a range of edge cases (missing fields,
flat addresses, multi-item orders, cancellations, pagination) so the
production code is exercised against realistic variation before any live
JD response is ever seen.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

SAMPLE_DATA_DIR = Path(__file__).resolve().parent / "sample_data"


def _load(name: str) -> Any:
    return json.loads((SAMPLE_DATA_DIR / name).read_text(encoding="utf-8"))


class MockJdClient:
    """Drop-in replacement for JdClient. Reads from sample_data/."""

    def __init__(self, *_, **__) -> None:
        pass

    async def check_new_orders(
        self,
        session: Session,
        *,
        since: datetime,
        until: datetime,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Return a page of order ids.

        Recognises additional `jd_check_new_order_pageN.json` files for
        N >= 2 so pagination behaviour can be exercised in tests. Page 1
        falls back to the canonical `jd_check_new_order.json`.
        """
        if page <= 1:
            return _load("jd_check_new_order.json")
        path = SAMPLE_DATA_DIR / f"jd_check_new_order_page{page}.json"
        if path.exists():
            return _load(path.name)
        # No more pages — return an empty result set in the same envelope shape.
        return {
            "success": True,
            "resultCode": "0000",
            "result": [],
            "pageNo": page,
            "totalCount": 0,
        }

    async def get_order_detail(self, session: Session, jd_order_id: str) -> dict[str, Any]:
        all_details = _load("jd_order_details.json")
        if jd_order_id in all_details:
            return {"success": True, "result": all_details[jd_order_id]}
        # Fallback for unknown ids: clone the first sample with the requested id.
        first = next(iter(all_details.values()))
        return {"success": True, "result": {**first, "jdOrderId": jd_order_id}}
