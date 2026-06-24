from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    __table_args__ = (UniqueConstraint("provider", name="uq_oauth_tokens_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)  # "jd" | "tmall"
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class JdOrder(Base):
    __tablename__ = "jd_orders"

    jd_order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="fetched")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Convenience columns extracted from payload (best-effort, may be NULL until mapper fills them).
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_cny: Mapped[float | None] = mapped_column(nullable=True)
    total_rub: Mapped[float | None] = mapped_column(nullable=True)


class JdProduct(Base):
    """JD VOP product catalog item. Synced separately from orders."""

    __tablename__ = "jd_products"

    sku_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    price_cny: Mapped[float | None] = mapped_column(nullable=True)
    price_rub: Mapped[float | None] = mapped_column(nullable=True)
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class TmallItem(Base):
    """Tmall/Taobao product catalog item. Source of the CDEK feed."""

    __tablename__ = "tmall_items"

    num_iid: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    price_cny: Mapped[float | None] = mapped_column(nullable=True)
    price_rub: Mapped[float | None] = mapped_column(nullable=True)
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pic_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class JdUnionProduct(Base):
    """JD Union (affiliate / CPS) goods record.

    Distinct from JdProduct (which is for VOP B2B catalog) — Union exposes
    affiliate-marketing-oriented data with commission rates, promo links and
    aggregated sales counts.
    """

    __tablename__ = "jd_union_products"

    sku_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sku_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    price_cny: Mapped[float | None] = mapped_column(nullable=True)
    price_rub: Mapped[float | None] = mapped_column(nullable=True)
    lowest_price_cny: Mapped[float | None] = mapped_column(nullable=True)

    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shop_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shop_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    material_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    main_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    commission: Mapped[float | None] = mapped_column(nullable=True)
    commission_share: Mapped[float | None] = mapped_column(nullable=True)
    in_order_count_30d: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stock (best-effort from goods.query.stockInfo — may be NULL when JD
    # didn't return stockInfo, which is common for some categories).
    in_stock: Mapped[bool | None] = mapped_column(nullable=True)
    stock_state: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_num: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Big fields (only filled when bigfield.query was run).
    ware_qd: Mapped[str | None] = mapped_column(Text, nullable=True)
    wdesc: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class JdUnionCatalogCheck(Base):
    """One run of POST /union/check — bulk catalog audit against JD Union.

    Stores the summary so the user can list past runs and re-download a
    report without re-running the API calls.
    """

    __tablename__ = "jd_union_catalog_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    total: Mapped[int] = mapped_column(Integer, default=0)
    with_sku: Mapped[int] = mapped_column(Integer, default=0)
    found: Mapped[int] = mapped_column(Integer, default=0)
    not_found: Mapped[int] = mapped_column(Integer, default=0)
    no_sku: Mapped[int] = mapped_column(Integer, default=0)


class JdUnionCatalogCheckRow(Base):
    """Per-input-row result of a catalog check, joined to JdUnionCatalogCheck."""

    __tablename__ = "jd_union_catalog_check_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    found: Mapped[bool] = mapped_column(default=False)
    jd_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    price_cny: Mapped[float | None] = mapped_column(nullable=True)
    price_rub: Mapped[float | None] = mapped_column(nullable=True)
    commission: Mapped[float | None] = mapped_column(nullable=True)
    commission_share: Mapped[float | None] = mapped_column(nullable=True)
    in_stock: Mapped[bool | None] = mapped_column(nullable=True)
    stock_num: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CatalogWatchlistEntry(Base):
    """Which categories / queries we actively sync from each source."""

    __tablename__ = "catalog_watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)   # "tmall" | "jd"
    category_name: Mapped[str] = mapped_column(String(255))        # human-readable label
    category_id: Mapped[str | None] = mapped_column(String(64), nullable=True)   # Taobao cid
    query: Mapped[str | None] = mapped_column(String(255), nullable=True)         # search query
    enabled: Mapped[bool] = mapped_column(default=True, index=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True, default="jd")  # "jd" | "tmall"
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
