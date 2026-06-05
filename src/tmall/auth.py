"""Taobao Open Platform MD5 request signing.

Auth flow is different from JD VOP:
- No OAuth session token needed for reading public item data.
- Every request carries: app_key, timestamp, sign_method=md5, sign.
- sign = MD5(app_secret + sorted_param_pairs + app_secret).upper()

Reference: https://open.taobao.global/doc — "Signing" section.
"""

from __future__ import annotations

import hashlib
from datetime import datetime


def _sign(app_secret: str, params: dict[str, str]) -> str:
    pairs = sorted(params.items())
    raw = app_secret + "".join(f"{k}{v}" for k, v in pairs) + app_secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def build_params(
    app_key: str,
    app_secret: str,
    method: str,
    *,
    session: str | None = None,
    **extra: str,
) -> dict[str, str]:
    """Return a fully-signed param dict ready to POST as form data."""
    params: dict[str, str] = {
        "method": method,
        "app_key": app_key,
        "v": "2.0",
        "format": "json",
        "sign_method": "md5",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **{k: str(v) for k, v in extra.items()},
    }
    if session:
        params["session"] = session

    params["sign"] = _sign(app_secret, params)
    return params
