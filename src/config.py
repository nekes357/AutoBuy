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

    database_url: str = "sqlite+pysqlite:///./autobuy.db"

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

    @field_validator("sync_interval_minutes", mode="before")
    @classmethod
    def _empty_str_as_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
