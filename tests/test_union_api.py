"""FastAPI integration tests for /union/* endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    from src.main import app
    return TestClient(app)


def test_union_sync_requires_api_key():
    with _client() as c:
        r = c.post("/union/sync?keyword=drill")
        assert r.status_code == 401


def test_union_sync_and_list_products():
    with _client() as c:
        r = c.post("/union/sync?keyword=drill", headers={"x-api-key": "test-key"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fetched"] == 3
        assert body["new"] == 3

        r = c.get("/union/products", headers={"x-api-key": "test-key"})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 3

        r = c.get("/union/products/100012345001", headers={"x-api-key": "test-key"})
        assert r.status_code == 200
        body = r.json()
        assert body["sku_name"].startswith("Аккумуляторная дрель")
        assert body["wdesc"] is not None  # bigfield enabled by default


def test_union_product_404():
    with _client() as c:
        r = c.get("/union/products/99999", headers={"x-api-key": "test-key"})
        assert r.status_code == 404
