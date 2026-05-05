"""CNY -> RUB conversion using a static rate from settings.

The rate is intentionally not fetched dynamically — per project decision, it
lives in ENV (CNY_RUB_RATE) and is changed manually. Every conversion is
logged so the audit trail shows which rate was applied.
"""

from __future__ import annotations

import structlog

from src.config import get_settings

log = structlog.get_logger(__name__)


def cny_to_rub(amount_cny: float, *, correlation_id: str | None = None) -> float:
    rate = get_settings().cny_rub_rate
    rub = round(amount_cny * rate, 2)
    log.info(
        "currency.convert",
        currency_from="CNY",
        currency_to="RUB",
        amount_from=amount_cny,
        rate=rate,
        amount_to=rub,
        correlation_id=correlation_id,
    )
    return rub
