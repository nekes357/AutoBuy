"""Bulk catalog check against JD Union.

Given a product file (xlsx or csv) exported from the store — where the real
JD SKU is embedded in an item.jd.com URL rather than a dedicated column — this
module:

  1. extracts the JD SKU id from each row's URL,
  2. queries JD Union in batches of <=100 SKUs (jd.union.open.goods.query),
  3. returns a per-row report: still on JD? current price (CNY/RUB)? commission?

The store's own `product_id` is kept in the report so results can be joined
back to the catalog. Rows whose URL has no recognisable SKU, or whose SKU JD
no longer returns, are reported as not-found rather than dropped silently.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.currency import cny_to_rub
from src.fileio import read_tabular, read_tabular_path
from src.jd_union.client import UnionClient
from src.jd_union.mock import MockUnionClient
from src.jd_union.schemas import UnionGoodsItem
from src.models import JdUnionCatalogCheck, JdUnionCatalogCheckRow
from src.sync_union import _build_client

log = structlog.get_logger(__name__)

# item.jd.com/100357310860.html  ->  100357310860
# Tolerant of .html / .htm / no extension / query strings / trailing junk —
# the SKU is just the run of digits right after the host slash.
_SKU_RE = re.compile(r"item\.jd\.com/(\d+)", re.IGNORECASE)

# JD goods.query accepts up to 100 skuIds per call.
SKU_BATCH = 100

# Column names we try, in order, when reading the product file.
_URL_COLUMNS = ("active_url", "any_url", "url")
_ID_COLUMNS = ("product_id", "id")
_NAME_COLUMNS = ("name", "title")


@dataclass
class ProductRow:
    """One row parsed from the input file."""

    product_id: str | None
    name: str | None
    url: str | None
    sku_id: str | None  # extracted from url; None if not parseable


@dataclass
class CheckResult:
    """Per-row outcome of the JD Union check."""

    product_id: str | None
    name: str | None
    sku_id: str | None
    url: str | None
    found: bool = False
    jd_name: str | None = None
    price_cny: float | None = None
    price_rub: float | None = None
    commission: float | None = None
    commission_share: float | None = None
    in_stock: bool | None = None     # None if JD didn't report stockInfo
    stock_num: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "sku_id": self.sku_id,
            "url": self.url,
            "found": self.found,
            "jd_name": self.jd_name,
            "price_cny": self.price_cny,
            "price_rub": self.price_rub,
            "commission": self.commission,
            "commission_share": self.commission_share,
            "in_stock": self.in_stock,
            "stock_num": self.stock_num,
        }


@dataclass
class CheckReport:
    total: int = 0
    with_sku: int = 0
    found: int = 0
    not_found: int = 0
    no_sku: int = 0
    check_id: int | None = None   # populated when results are persisted
    results: list[CheckResult] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "with_sku": self.with_sku,
            "found": self.found,
            "not_found": self.not_found,
            "no_sku": self.no_sku,
            "check_id": self.check_id,
        }


def extract_sku_id(url: str | None) -> str | None:
    if not url:
        return None
    m = _SKU_RE.search(url)
    return m.group(1) if m else None


def _pick(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    lowered = [h.lower().strip() if h else "" for h in headers]
    for cand in candidates:
        if cand in lowered:
            return lowered.index(cand)
    return None


def _pick_all(headers: list[str], candidates: tuple[str, ...]) -> list[int]:
    """All matching column indices, in candidate-priority order."""
    lowered = [h.lower().strip() if h else "" for h in headers]
    return [lowered.index(c) for c in candidates if c in lowered]


def parse_rows(raw_rows: list[tuple[Any, ...]]) -> list[ProductRow]:
    """Turn a header+data matrix into ProductRow objects."""
    if not raw_rows:
        return []
    headers = [str(c) if c is not None else "" for c in raw_rows[0]]
    id_idx = _pick(headers, _ID_COLUMNS)
    name_idx = _pick(headers, _NAME_COLUMNS)
    # Collect every URL column present so we can fall back per-row
    # (e.g. active_url empty -> use any_url).
    url_indices = _pick_all(headers, _URL_COLUMNS)

    rows: list[ProductRow] = []
    for raw in raw_rows[1:]:
        if raw is None or all(c is None or str(c).strip() == "" for c in raw):
            continue

        url = next((c for i in url_indices if (c := _cell(raw, i))), None)
        rows.append(
            ProductRow(
                product_id=_cell(raw, id_idx),
                name=_cell(raw, name_idx),
                url=url,
                sku_id=extract_sku_id(url),
            )
        )
    return rows


def _cell(raw: tuple[Any, ...], idx: int | None) -> str | None:
    if idx is None or idx >= len(raw):
        return None
    v = raw[idx]
    return str(v).strip() if v is not None and str(v).strip() != "" else None


def load_product_file(path: str | Path) -> list[ProductRow]:
    """Read an .xlsx or .csv product file into ProductRows."""
    return parse_rows(read_tabular_path(path))


def load_product_bytes(data: bytes, filename: str) -> list[ProductRow]:
    """Read product rows from in-memory bytes (e.g. an HTTP upload)."""
    return parse_rows(read_tabular(data, filename))


async def check_products(
    rows: list[ProductRow],
    *,
    session: Session | None = None,
    settings: Settings | None = None,
    source_filename: str | None = None,
) -> CheckReport:
    """Query JD Union for every row that has a SKU, build a CheckReport.

    One report row is emitted per *input* row (duplicate SKUs are not merged),
    but each unique SKU is queried only once.

    When `session` is given, the run and its per-row results are persisted to
    jd_union_catalog_checks / jd_union_catalog_check_rows, and report.check_id
    is set so the caller can later fetch the report back from the DB.
    """
    settings = settings or get_settings()
    report = CheckReport(total=len(rows))

    # Persist the run header up front so we can attach rows to it later.
    check: JdUnionCatalogCheck | None = None
    if session is not None:
        check = JdUnionCatalogCheck(
            source_filename=source_filename,
            total=len(rows),
        )
        session.add(check)
        session.commit()
        report.check_id = check.id

    # Unique SKUs to query (dedupe API calls); rows keep their own identity.
    unique_skus = {row.sku_id for row in rows if row.sku_id}
    report.with_sku = sum(1 for row in rows if row.sku_id)
    report.no_sku = sum(1 for row in rows if not row.sku_id)
    sku_ids = list(unique_skus)

    client, http = _build_client(settings)
    correlation_id = "catalog-check"
    found_items: dict[str, UnionGoodsItem] = {}

    try:
        for i in range(0, len(sku_ids), SKU_BATCH):
            batch = sku_ids[i : i + SKU_BATCH]
            env = await _query_batch(client, batch)
            for item in env.unwrap().data or []:
                found_items[str(item.skuId)] = item
    finally:
        if http is not None:
            await http.aclose()

    for row in rows:
        if not row.sku_id:
            report.results.append(
                CheckResult(row.product_id, row.name, None, row.url, found=False)
            )
            continue

        item = found_items.get(row.sku_id)
        if item is None:
            report.not_found += 1
            report.results.append(
                CheckResult(row.product_id, row.name, row.sku_id, row.url, found=False)
            )
            continue

        report.found += 1
        price_cny = item.priceInfo.price if item.priceInfo else None
        price_rub = (
            cny_to_rub(price_cny, correlation_id=correlation_id)
            if price_cny is not None
            else None
        )
        comm = item.commissionInfo
        report.results.append(
            CheckResult(
                product_id=row.product_id,
                name=row.name,
                sku_id=row.sku_id,
                url=row.url,
                found=True,
                jd_name=item.skuName,
                price_cny=price_cny,
                price_rub=price_rub,
                commission=comm.commission if comm else None,
                commission_share=comm.commissionShare if comm else None,
                in_stock=item.is_in_stock(),
                stock_num=item.stock_num(),
            )
        )

    if session is not None and check is not None:
        check.with_sku = report.with_sku
        check.found = report.found
        check.not_found = report.not_found
        check.no_sku = report.no_sku
        check.finished_at = datetime.now(UTC)
        for r in report.results:
            session.add(
                JdUnionCatalogCheckRow(
                    check_id=check.id,
                    product_id=r.product_id,
                    name=r.name,
                    sku_id=r.sku_id,
                    url=r.url,
                    found=r.found,
                    jd_name=r.jd_name,
                    price_cny=r.price_cny,
                    price_rub=r.price_rub,
                    commission=r.commission,
                    commission_share=r.commission_share,
                    in_stock=r.in_stock,
                    stock_num=r.stock_num,
                )
            )
        session.commit()

    log.info(
        "catalog_check.done",
        total=report.total,
        with_sku=report.with_sku,
        found=report.found,
        not_found=report.not_found,
        no_sku=report.no_sku,
    )
    return report


async def _query_batch(client: UnionClient | MockUnionClient, batch: list[str]):
    # MockUnionClient also implements query_by_skus.
    return await client.query_by_skus(batch)


def report_to_csv(report: CheckReport) -> str:
    """Serialize a CheckReport to CSV text for download."""
    buf = io.StringIO()
    cols = [
        "product_id", "name", "sku_id", "url", "found",
        "jd_name", "price_cny", "price_rub",
        "commission", "commission_share",
        "in_stock", "stock_num",
    ]
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for r in report.results:
        writer.writerow(r.as_dict())
    return buf.getvalue()


def load_check_from_db(session: Session, check_id: int) -> CheckReport | None:
    """Hydrate a CheckReport from a previously-persisted run."""
    check = session.get(JdUnionCatalogCheck, check_id)
    if check is None:
        return None
    rows = (
        session.query(JdUnionCatalogCheckRow)
        .filter(JdUnionCatalogCheckRow.check_id == check_id)
        .order_by(JdUnionCatalogCheckRow.id)
        .all()
    )
    report = CheckReport(
        total=check.total,
        with_sku=check.with_sku,
        found=check.found,
        not_found=check.not_found,
        no_sku=check.no_sku,
        check_id=check.id,
    )
    report.results = [
        CheckResult(
            product_id=r.product_id,
            name=r.name,
            sku_id=r.sku_id,
            url=r.url,
            found=r.found,
            jd_name=r.jd_name,
            price_cny=r.price_cny,
            price_rub=r.price_rub,
            commission=r.commission,
            commission_share=r.commission_share,
            in_stock=r.in_stock,
            stock_num=r.stock_num,
        )
        for r in rows
    ]
    return report
