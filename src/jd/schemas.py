"""Pydantic models for JD VOP responses.

Field shapes are best-effort and based on the public PHP wrapper. The exact
wire format will be confirmed against the live VOP cabinet — until then, models
are permissive (extra="allow") so unknown fields are preserved in raw_payload.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JdEnvelope(BaseModel):
    """Generic VOP response envelope. TBD: exact shape from real responses."""

    model_config = ConfigDict(extra="allow")

    success: bool | None = None
    code: str | int | None = None
    message: str | None = None
    result: Any | None = None
    resultCode: str | int | None = None
    resultMessage: str | None = None


class JdOrderListItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    jdOrderId: str = Field(alias="jdOrderId")
    submitState: str | int | None = None
    state: str | int | None = None
    submitTime: datetime | str | None = None


class JdOrderItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    skuId: str | int | None = None
    name: str | None = None
    num: int | None = None
    price: float | None = None
    currency: str | None = "CNY"


class JdOrderDetail(BaseModel):
    """Detailed JD order. Permissive: unknown fields preserved in raw."""

    model_config = ConfigDict(extra="allow")

    jdOrderId: str
    submitTime: datetime | str | None = None
    state: str | int | None = None

    # Recipient (Chinese B2B address — flat or nested, both supported).
    name: str | None = None
    phone: str | None = None
    mobile: str | None = None
    email: str | None = None
    province: str | None = None
    city: str | None = None
    county: str | None = None
    town: str | None = None
    address: str | None = None

    # Money.
    orderPrice: float | None = None
    freight: float | None = None
    currency: str | None = "CNY"

    # Items.
    sku: list[JdOrderItem] | None = None
    items: list[JdOrderItem] | None = None
