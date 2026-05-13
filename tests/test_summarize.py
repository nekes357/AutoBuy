"""Unit tests for src.sync._summarize against every edge-case fixture.

The pipeline depends on _summarize coping with whatever JD throws at it
without crashing. Parametrise it across every fixture order so any future
regression is caught immediately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.sync import _summarize

SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "src" / "jd" / "sample_data" / "jd_order_details.json"
)
ALL_ORDERS = json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("jd_order_id", sorted(ALL_ORDERS.keys()))
def test_summarize_does_not_crash(jd_order_id: str) -> None:
    """Every order in sample_data should pass through _summarize cleanly."""
    detail = {"success": True, "result": ALL_ORDERS[jd_order_id]}
    summary = _summarize(detail, correlation_id=f"test-{jd_order_id}")

    # Must always return all four keys, even if values are None.
    assert set(summary.keys()) == {"recipient_name", "recipient_phone", "total_cny", "total_rub"}

    # If total_cny is set, total_rub must be set too (and >= 0).
    if summary["total_cny"] is not None:
        assert summary["total_rub"] is not None
        assert summary["total_rub"] >= 0


@pytest.mark.parametrize("jd_order_id,expected_name,expected_phone", [
    ("100000000001", "Ivan Petrov", "+79991234567"),
    ("100000000002", "Anna Sidorova", "+79997654321"),
    ("100000000003", "Sergey Volkov", "010-12345678"),   # consigneeName + landline phone
    ("100000000004", "Marina K.", "+79998887766"),
    ("100000000005", "Wholesale Customer LLC", "+74951234567"),
    ("100000000006", "Test User", "+79990000000"),
    ("100000000007", "Olga N.", "+79991112233"),
    ("100000000008", "Empty Items Test", "+79993334455"),
    ("100000000009", "Alt Schema", "+79995556677"),
])
def test_summarize_extracts_name_and_phone(jd_order_id, expected_name, expected_phone):
    detail = {"success": True, "result": ALL_ORDERS[jd_order_id]}
    summary = _summarize(detail, correlation_id="test")
    assert summary["recipient_name"] == expected_name
    assert summary["recipient_phone"] == expected_phone


@pytest.mark.parametrize("jd_order_id,expected_cny", [
    ("100000000001", 850.0),
    ("100000000002", 1200.5),
    ("100000000005", 18450.0),       # large multi-item
    ("100000000007", None),          # no price field at all
    ("100000000008", 0.0),           # explicit zero
    ("100000000009", 777.77),        # totalPrice instead of orderPrice
])
def test_summarize_extracts_total_cny(jd_order_id, expected_cny):
    detail = {"success": True, "result": ALL_ORDERS[jd_order_id]}
    summary = _summarize(detail, correlation_id="test")
    assert summary["total_cny"] == expected_cny


def test_summarize_handles_flat_envelope_without_result_key():
    """JD sometimes returns the order dict at the top level instead of nested under 'result'."""
    flat = {"jdOrderId": "X", "name": "Test", "mobile": "+1", "orderPrice": 100.0}
    summary = _summarize(flat, correlation_id="test")
    assert summary["recipient_name"] == "Test"
    assert summary["total_cny"] == 100.0


def test_summarize_handles_completely_empty_envelope():
    """Garbage in, sensible None out — no crash."""
    summary = _summarize({}, correlation_id="test")
    assert summary == {
        "recipient_name": None,
        "recipient_phone": None,
        "total_cny": None,
        "total_rub": None,
    }


def test_summarize_handles_non_dict_envelope():
    """Defensive: even if upstream returns a list or string, don't crash."""
    summary = _summarize([], correlation_id="test")  # type: ignore[arg-type]
    assert summary["recipient_name"] is None
