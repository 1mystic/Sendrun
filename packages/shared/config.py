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

    # Off by default — see services/api/rate_limit_middleware.py. Enabling
    # without REDIS_URL set falls back to a single-process in-memory bucket
    # (correct for a solo dev server, NOT safe across multiple instances).
    rate_limit_enabled: bool = False
    rate_limit_capacity: float = 60.0
    rate_limit_refill_per_second: float = 1.0

    email_provider: Literal["fake", "resend"] = "fake"
    resend_api_key: str = ""
    resend_webhook_secret: str = ""
    fake_webhook_secret: str = "fake-webhook-secret"

    llm_provider: Literal["fake", "anthropic", "openai", "openrouter"] = "fake"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    # OpenRouter: one API key, one OpenAI-compatible endpoint, routes to
    # 100+ underlying models (Claude, GPT, Llama, Mistral, Gemini, ...) by
    # qualifying the model name, e.g. "anthropic/claude-sonnet-4.5". See
    # packages/shared/providers/llm_http.py::OpenRouterProvider.
    openrouter_api_key: str = ""
    openrouter_site_url: str = ""

    # Off by default: an unset tracking URI makes mlflow silently create a
    # local ./mlruns store on first use, which is a real filesystem side
    # effect nothing (tests especially) should trigger by accident. Preflight
    # falls back to its neutral delivery estimate when this is disabled — see
    # services/api/routers/preflight.py.
    bounce_model_enabled: bool = False
    mlflow_tracking_uri: str = ""

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

    # The one browser origin allowed to call this API with credentials (see
    # main.py's CORS setup) — never "*", since a wildcard origin cannot carry
    # credentials per the CORS spec and the session cookie is httponly
    # regardless. Set to the deployed Vercel URL in production.
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
