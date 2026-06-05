"""Telegram notifications for sync events.

Fails silently — a broken notification must never interrupt a sync run.
Configure via TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

_TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"


async def send(text: str, token: str, chat_id: str) -> None:
    if not token or not chat_id:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(
                _TELEGRAM_URL.format(token=token),
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            if resp.status_code != 200:
                log.warning("notify.telegram_error", status=resp.status_code, body=resp.text[:200])
    except Exception as exc:  # noqa: BLE001
        log.warning("notify.telegram_failed", error=str(exc))


def _fmt_sync_result(
    source: str,
    fetched: int,
    new: int,
    errors: int,
) -> str:
    tag = source.upper()
    if errors == 0:
        return f"[{tag}] Синхронизация завершена: {fetched} обработано, {new} новых"
    if fetched == 0:
        return f"[{tag}] Синхронизация не получила данные. Ошибок: {errors}"
    return f"[{tag}] Синхронизация с ошибками: {fetched} обработано, {new} новых, {errors} ошибок"
