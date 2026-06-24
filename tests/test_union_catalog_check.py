"""Tests for the JD Union bulk catalog check (xlsx/csv → report)."""

from __future__ import annotations

import io

import openpyxl
import pytest

from src.jd_union.catalog_check import (
    check_products,
    extract_sku_id,
    load_product_bytes,
    parse_rows,
    report_to_csv,
)

# SKUs 100012345001/002/003 exist in union_goods_query.json (the mock pool);
# 999... does not, so it exercises the not-found path.
SKU_PRESENT_1 = "100012345001"
SKU_PRESENT_2 = "100012345002"
SKU_MISSING = "100099999999"


def test_extract_sku_id_from_jd_url():
    assert extract_sku_id("https://item.jd.com/100357310860.html") == "100357310860"
    assert extract_sku_id("http://item.jd.com/55.html?x=1") == "55"
    assert extract_sku_id("https://example.com/foo") is None
    assert extract_sku_id(None) is None
    assert extract_sku_id("") is None


def test_parse_rows_picks_columns_and_extracts_sku():
    raw = [
        ("product_id", "name", "status", "stock_status", "active_url", "any_url"),
        (55083746, "Honor 600", "published", "in_stock",
         f"https://item.jd.com/{SKU_PRESENT_1}.html",
         f"https://item.jd.com/{SKU_PRESENT_1}.html"),
        (55083545, "No URL product", "published", "in_stock", "", ""),
    ]
    rows = parse_rows(raw)
    assert len(rows) == 2
    assert rows[0].product_id == "55083746"
    assert rows[0].name == "Honor 600"
    assert rows[0].sku_id == SKU_PRESENT_1
    # Second row has no URL → no SKU extracted.
    assert rows[1].sku_id is None


def _make_xlsx(rows: list[tuple]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_load_product_bytes_xlsx():
    data = _make_xlsx([
        ("product_id", "name", "active_url", "any_url"),
        (1, "A", f"https://item.jd.com/{SKU_PRESENT_1}.html", ""),
    ])
    rows = load_product_bytes(data, "catalog.xlsx")
    assert len(rows) == 1
    assert rows[0].sku_id == SKU_PRESENT_1


def test_load_product_bytes_csv():
    text = (
        "product_id,name,active_url,any_url\n"
        f"1,A,https://item.jd.com/{SKU_PRESENT_1}.html,\n"
    )
    rows = load_product_bytes(text.encode("utf-8"), "catalog.csv")
    assert len(rows) == 1
    assert rows[0].sku_id == SKU_PRESENT_1


@pytest.mark.asyncio
async def test_check_products_found_and_missing():
    raw = [
        ("product_id", "name", "active_url"),
        (1, "Present 1", f"https://item.jd.com/{SKU_PRESENT_1}.html"),
        (2, "Present 2", f"https://item.jd.com/{SKU_PRESENT_2}.html"),
        (3, "Missing", f"https://item.jd.com/{SKU_MISSING}.html"),
        (4, "No url", ""),
    ]
    rows = parse_rows(raw)
    report = await check_products(rows)

    s = report.summary()
    assert s["total"] == 4
    assert s["with_sku"] == 3
    assert s["found"] == 2
    assert s["not_found"] == 1
    assert s["no_sku"] == 1

    by_sku = {r.sku_id: r for r in report.results}
    assert by_sku[SKU_PRESENT_1].found is True
    assert by_sku[SKU_PRESENT_1].price_cny == 389.0
    assert by_sku[SKU_PRESENT_1].price_rub == round(389.0 * 12.5, 2)
    assert by_sku[SKU_PRESENT_1].commission == 15.56
    assert by_sku[SKU_MISSING].found is False
    assert by_sku[SKU_MISSING].price_cny is None


def test_extract_sku_id_tolerates_htm_and_query():
    # Real catalog files contain truncated .htm and trailing query strings.
    assert extract_sku_id("https://item.jd.com/100260510439.htm") == "100260510439"
    assert extract_sku_id("https://item.jd.com/123.html?cu=true&utm=x") == "123"


@pytest.mark.asyncio
async def test_check_products_duplicate_sku_kept_per_row():
    """Two input rows sharing one SKU must both appear in the report
    (the SKU is queried once, but no input row is dropped)."""
    raw = [
        ("product_id", "name", "active_url"),
        (1, "Variant A", f"https://item.jd.com/{SKU_PRESENT_1}.html"),
        (2, "Variant B", f"https://item.jd.com/{SKU_PRESENT_1}.html"),
    ]
    rows = parse_rows(raw)
    report = await check_products(rows)

    assert report.total == 2
    assert report.with_sku == 2
    assert report.found == 2
    assert len(report.results) == 2
    pids = sorted(r.product_id for r in report.results)
    assert pids == ["1", "2"]


@pytest.mark.asyncio
async def test_report_to_csv_roundtrip():
    raw = [
        ("product_id", "name", "active_url"),
        (1, "Present 1", f"https://item.jd.com/{SKU_PRESENT_1}.html"),
    ]
    report = await check_products(parse_rows(raw))
    csv_text = report_to_csv(report)
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("product_id,name,sku_id,url,found")
    assert SKU_PRESENT_1 in lines[1]
    assert "True" in lines[1]
