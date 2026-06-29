from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"
    service_api_key: str = "change-me"

    database_url: str = "sqlite+pysqlite:///./feedbridge.db"

    jd_mode: Literal["mock", "live"] = "mock"
    jd_base_url: str = "https://bizapi.jd.com"
    jd_app_key: str = ""
    jd_app_secret: str = ""
    jd_username: str = ""
    jd_password: str = ""
    jd_callback_url: str = ""

    cny_rub_rate: float = 12.50

    default_weight_g: int = 500
    default_length_cm: int = 20
    default_width_cm: int = 15
    default_height_cm: int = 10

    sync_interval_minutes: int | None = Field(default=None)
    sync_lookback_minutes: int = 60
    # How many JD order-detail requests are in flight at once.
    # Network latency to JD (RU<->CN) is ~150-250ms per request, so
    # a sequential loop tops out around 4-5 orders/sec. With sync_concurrency=10
    # the practical throughput rises to ~30-50/sec, which is enough headroom
    # for any realistic JD page (default page_size=100).
    sync_concurrency: int = 10

    # --- JD Union (CPS affiliate) ---
    jd_union_mode: Literal["mock", "live"] = "mock"
    jd_union_app_key: str = ""
    jd_union_app_secret: str = ""
    # Affiliate site ID — usually required for promo-link methods, not for goods.
    jd_union_site_id: str = ""

    # --- Apify (web scraping, alternative to Taobao Open Platform) ---
    apify_api_token: str = ""
    apify_taobao_actor: str = "zen-studio/taobao-seller-products-scraper"

    # --- Tmall / Taobao Open Platform (taoworld.com) ---
    tmall_mode: Literal["mock", "live", "apify"] = "mock"
    tmall_app_key: str = ""
    tmall_app_secret: str = ""
    # How many item IDs to fetch in one taobao.items.list.get call (max 40).
    tmall_batch_size: int = 40
    # Interval for scheduled catalog refresh (None = manual /feed/sync only).
    tmall_sync_interval_minutes: int | None = Field(default=None)

    # --- Telegram notifications ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    # Set to False to suppress successful-sync messages (errors always sent).
    telegram_notify_success: bool = True

    @field_validator("sync_interval_minutes", "tmall_sync_interval_minutes", mode="before")
    @classmethod
    def _empty_str_as_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
