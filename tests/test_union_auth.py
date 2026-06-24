"""JD Union signature: regression tests for the MD5 sort-and-concat algorithm.

The signing rule (JOS):
  sign = MD5(secret + ''.join(k+v for k,v in sorted(params)) + secret).upper()

If anyone refactors the sort order, key concatenation, or hex case, these
tests will catch it — a wrong sign means every real API call gets rejected
with code 1015 (invalid signature).
"""

from __future__ import annotations

import hashlib

from src.jd_union.auth import _sign, build_params


def test_sign_md5_uppercase():
    params = {"app_key": "k1", "method": "x.y", "v": "1.0"}
    secret = "s"
    expected_raw = "sapp_keyk1methodx.yv1.0s"
    expected = hashlib.md5(expected_raw.encode()).hexdigest().upper()
    assert _sign(secret, params) == expected
    # uppercase, 32 chars, hex
    assert _sign(secret, params).isupper()
    assert len(_sign(secret, params)) == 32


def test_sign_sorts_by_key_ascii():
    a = _sign("s", {"b": "2", "a": "1", "c": "3"})
    b = _sign("s", {"c": "3", "a": "1", "b": "2"})
    assert a == b, "sign must not depend on insertion order"


def test_build_params_includes_required_jos_fields():
    p = build_params("APPKEY", "SECRET", "jd.union.open.goods.query",
                     business_params={"goodsReq": {"keyword": "drill"}})
    required = (
        "method", "app_key", "v", "format",
        "sign_method", "timestamp", "sign", "param_json",
    )
    for key in required:
        assert key in p, f"missing required JOS param: {key}"
    assert p["method"] == "jd.union.open.goods.query"
    assert p["app_key"] == "APPKEY"
    assert p["sign_method"] == "md5"
    assert p["format"] == "json"


def test_param_json_deterministic_sort():
    """param_json must serialize with sort_keys=True so the same business
    payload always produces the same sign (otherwise signature would flip
    across runs for the same logical request)."""
    p1 = build_params("k", "s", "m", business_params={"b": 2, "a": 1})
    p2 = build_params("k", "s", "m", business_params={"a": 1, "b": 2})
    assert p1["param_json"] == p2["param_json"]
