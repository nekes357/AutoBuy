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


def _xlsx_bytes(rows):
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_union_check_persists_and_can_be_replayed():
    """POST /union/check returns a check_id that GET /union/checks/{id}
    resolves to the same summary + rows."""
    data = _xlsx_bytes([
        ("product_id", "name", "active_url"),
        (1, "Drill", "https://item.jd.com/100012345001.html"),
        (2, "Missing", "https://item.jd.com/100099999999.html"),
    ])

    with _client() as c:
        r = c.post(
            "/union/check",
            headers={"x-api-key": "test-key"},
            files={"file": ("JD.xlsx", data, "application/octet-stream")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        check_id = body["summary"]["check_id"]
        assert check_id is not None
        assert body["summary"]["found"] == 1
        assert body["summary"]["not_found"] == 1
        # in_stock surfaces in the JSON results.
        found_row = next(x for x in body["results"] if x["found"])
        assert found_row["in_stock"] is True
        assert found_row["stock_num"] == 158

        # List shows the new run.
        r = c.get("/union/checks", headers={"x-api-key": "test-key"})
        assert r.status_code == 200
        listing = r.json()
        assert any(item["id"] == check_id for item in listing)

        # Replay JSON.
        r = c.get(f"/union/checks/{check_id}", headers={"x-api-key": "test-key"})
        assert r.status_code == 200
        replay = r.json()
        assert replay["summary"]["found"] == 1
        assert len(replay["results"]) == 2

        # Replay CSV.
        r = c.get(
            f"/union/checks/{check_id}?format=csv",
            headers={"x-api-key": "test-key"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "in_stock,stock_num" in r.text.splitlines()[0]


def test_union_check_404():
    with _client() as c:
        r = c.get("/union/checks/99999", headers={"x-api-key": "test-key"})
        assert r.status_code == 404
