"""Settings, read once from the environment. Mirrors .env.example."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./local.db"
    sql_echo: bool = False
    redis_url: str = ""

    email_provider: Literal["fake", "resend"] = "fake"
    resend_api_key: str = ""
    resend_webhook_secret: str = ""
    fake_webhook_secret: str = "fake-webhook-secret"

    llm_provider: Literal["fake", "anthropic", "openai"] = "fake"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    from_address: str = "hello@sendrun.test"
    from_name: str = "Sendrun"
    send_rate_per_second: int = 8

    worker_id: str = "worker_local"
    lease_seconds: int = 30
    poll_interval_seconds: float = 1.0
    max_attempts: int = 5

    chaos_enabled: bool = False
    chaos_seed: int = 42

    session_secret: str = "change-me-in-production"
    session_ttl_hours: int = 24 * 14
    # False locally (http://localhost) and in tests; set true in any real
    # deployment, since the session cookie is otherwise never sent — see
    # services/api/routers/auth.py for why this cannot just be hardcoded True.
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
