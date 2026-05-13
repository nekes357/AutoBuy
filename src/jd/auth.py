"""JD VOP token cache.

The exact token endpoint and TTL are TBD until JD credentials are issued. The
class is structured so only `_request_new_token` needs to change.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings
from src.jd import methods
from src.models import OAuthToken

log = structlog.get_logger(__name__)

# Refresh a little before actual expiry to avoid 401 races.
EXPIRY_GUARD = timedelta(seconds=60)


class JdAuthError(RuntimeError):
    pass


class JdAuth:
    PROVIDER = "jd"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    async def get_token(self, session: Session) -> str:
        if self._settings.jd_mode == "mock":
            return "MOCK_TOKEN"

        cached = session.execute(
            select(OAuthToken).where(OAuthToken.provider == self.PROVIDER)
        ).scalar_one_or_none()

        now = datetime.now(UTC)
        if cached and cached.expires_at - EXPIRY_GUARD > now:
            return cached.access_token

        token, ttl_seconds = await self._request_new_token()
        expires_at = now + timedelta(seconds=ttl_seconds)

        if cached is None:
            cached = OAuthToken(provider=self.PROVIDER, access_token=token, expires_at=expires_at)
            session.add(cached)
        else:
            cached.access_token = token
            cached.expires_at = expires_at
        session.commit()

        log.info("jd.auth.token_refreshed", expires_at=expires_at.isoformat())
        return token

    async def _request_new_token(self) -> tuple[str, int]:
        """Request a fresh access_token from JD VOP.

        TBD: The exact path, payload shape and response keys will be finalised
        when the real VOP credentials are available. The implementation below
        follows the convention used by the open-source PHP wrapper.
        """
        s = self._settings
        if not (s.jd_app_key and s.jd_app_secret and s.jd_username and s.jd_password):
            raise JdAuthError(
                "JD credentials are not configured "
                "(set JD_APP_KEY/SECRET/USERNAME/PASSWORD)."
            )

        resp = await self._http.post(
            f"{s.jd_base_url}{methods.GET_ACCESS_TOKEN}",
            json={
                "appKey": s.jd_app_key,
                "appSecret": s.jd_app_secret,
                "username": s.jd_username,
                "password": s.jd_password,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        body = resp.json()

        # Tolerate either {"data":{"accessToken":..., "expiresIn":...}} or flat shape.
        data = body.get("data") if isinstance(body, dict) else None
        payload = data or body or {}
        token = payload.get("accessToken") or payload.get("access_token")
        ttl = payload.get("expiresIn") or payload.get("expires_in") or 86400

        if not token:
            raise JdAuthError(f"JD token response missing accessToken: {body!r}")
        return str(token), int(ttl)
