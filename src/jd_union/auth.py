"""JD Union request signing (JOS style).

sign = MD5(app_secret + sorted_param_pairs + app_secret).upper()
- pairs are concatenated as k+v with no separators
- params are sorted by ASCII of param name
- business params are packed into the `param_json` field

Reference: https://union.jd.com/openplatform/api — Signing section.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


def _sign(app_secret: str, params: dict[str, str]) -> str:
    pairs = sorted(params.items())
    raw = app_secret + "".join(f"{k}{v}" for k, v in pairs) + app_secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def build_params(
    app_key: str,
    app_secret: str,
    method: str,
    *,
    business_params: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, str]:
    """Return a fully-signed param dict ready to POST.

    `business_params` is the method-specific payload (e.g. goodsReqDTO);
    it gets JSON-encoded and placed in `param_json`. Order of keys inside
    that JSON string matters for the signature, so use sort_keys=True to
    keep things deterministic across runs.
    """
    params: dict[str, str] = {
        "method": method,
        "app_key": app_key,
        "v": "1.0",
        "format": "json",
        "sign_method": "md5",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if access_token:
        params["access_token"] = access_token
    if business_params is not None:
        params["param_json"] = json.dumps(business_params, sort_keys=True, ensure_ascii=False)

    params["sign"] = _sign(app_secret, params)
    return params
