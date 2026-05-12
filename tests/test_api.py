from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    # Import here so per-test env (conftest) takes effect first.
    from src.main import app
    return TestClient(app)


def test_health():
    with _client() as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_sync_run_requires_api_key():
    with _client() as c:
        r = c.post("/sync/run")
        assert r.status_code == 401


def test_sync_run_and_list_orders():
    # Should match EXPECTED_TOTAL in test_sync_e2e.py
    expected_total = 11

    with _client() as c:
        r = c.post("/sync/run", headers={"x-api-key": "test-key"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fetched"] == expected_total
        assert body["new"] == expected_total

        r = c.get("/orders", headers={"x-api-key": "test-key"})
        assert r.status_code == 200
        orders = r.json()
        assert len(orders) == expected_total

        r = c.get("/orders/100000000001", headers={"x-api-key": "test-key"})
        assert r.status_code == 200
        assert r.json()["recipient_name"] == "Ivan Petrov"


def test_jd_callback_accepts_post():
    with _client() as c:
        r = c.post("/jd/callback", json={"event": "ping"})
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
