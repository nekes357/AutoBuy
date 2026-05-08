"""Mock JD client used when JD_MODE=mock.

Reads canned responses from tests/fixtures so the full pipeline can run without
real JD credentials. Same async signature as JdClient.
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
    """Drop-in replacement for JdClient. Reads from fixtures."""

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
        return _load("jd_check_new_order.json")

    async def get_order_detail(self, session: Session, jd_order_id: str) -> dict[str, Any]:
        all_details = _load("jd_order_details.json")
        if jd_order_id in all_details:
            return {"success": True, "result": all_details[jd_order_id]}
        # fallback to first sample
        first = next(iter(all_details.values()))
        return {"success": True, "result": {**first, "jdOrderId": jd_order_id}}
