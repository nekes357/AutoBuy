"""FastAPI integration tests for /shop/* endpoints."""

from __future__ import annotations

import io

import openpyxl
from fastapi.testclient import TestClient


def _client():
    from src.main import app
    return TestClient(app)


def test_shop_sync_requires_api_key():
    with _client() as c:
        r = c.post("/shop/sync?url=https://item.taobao.com/item.htm?id=1")
        assert r.status_code == 401


def test_shop_sync_by_url_and_list_items():
    with _client() as c:
        r = c.post(
            "/shop/sync",
            params={"url": "https://item.taobao.com/item.htm?id=612286553782"},
            headers={"x-api-key": "test-key"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sellers"] == 1
        assert body["total_items"] == 3
        assert body["shops"][0]["nick"] == "demo_taobao_shop"

        r = c.get(
            "/shop/items",
            params={"seller": "demo_taobao_shop"},
            headers={"x-api-key": "test-key"},
        )
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 3
        assert all(i["seller_nick"] == "demo_taobao_shop" for i in items)


def test_shop_sync_from_uploaded_file():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(("name", "url"))
    ws.append(("Кабель", "https://item.taobao.com/item.htm?id=612286553782"))
    buf = io.BytesIO()
    wb.save(buf)

    with _client() as c:
        r = c.post(
            "/shop/sync",
            headers={"x-api-key": "test-key"},
            files={"file": ("shops.xlsx", buf.getvalue(), "application/octet-stream")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["total_items"] == 3


def test_shop_sync_no_input_is_400():
    with _client() as c:
        r = c.post("/shop/sync", headers={"x-api-key": "test-key"})
        assert r.status_code == 400
