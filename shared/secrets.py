"""
Centralized secret loading.
All secrets come from environment variables — never hardcoded.
"""
import os
from functools import lru_cache
from typing import Optional


def _require(key: str) -> str:
    """Get an env var or raise a clear error if missing."""
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            f"Check your .env file or environment configuration."
        )
    return value


def _optional(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(key, default)


@lru_cache(maxsize=None)
def get_secrets() -> "Secrets":
    return Secrets()


class Secrets:
    """Single access point for all secrets. Loaded once, cached."""

    # Telegram
    @property
    def telegram_bot_token(self) -> str:
        return _require("TELEGRAM_BOT_TOKEN")

    @property
    def telegram_allowed_user_ids(self) -> list[int]:
        raw = _require("TELEGRAM_ALLOWED_USER_IDS")
        return [int(uid.strip()) for uid in raw.split(",") if uid.strip()]

    # Anthropic
    @property
    def anthropic_api_key(self) -> str:
        return _require("ANTHROPIC_API_KEY")

    # PostgreSQL
    @property
    def postgres_dsn(self) -> str:
        host = _optional("POSTGRES_HOST", "localhost")
        port = _optional("POSTGRES_PORT", "5432")
        db = _optional("POSTGRES_DB", "apollo")
        user = _optional("POSTGRES_USER", "apollo")
        password = _require("POSTGRES_PASSWORD")
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    @property
    def postgres_dsn_sync(self) -> str:
        host = _optional("POSTGRES_HOST", "localhost")
        port = _optional("POSTGRES_PORT", "5432")
        db = _optional("POSTGRES_DB", "apollo")
        user = _optional("POSTGRES_USER", "apollo")
        password = _require("POSTGRES_PASSWORD")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    # Redis
    @property
    def redis_url(self) -> str:
        host = _optional("REDIS_HOST", "localhost")
        port = _optional("REDIS_PORT", "6379")
        password = _optional("REDIS_PASSWORD")
        if password:
            return f"redis://:{password}@{host}:{port}/0"
        return f"redis://{host}:{port}/0"

    # Internal API
    @property
    def internal_api_secret(self) -> str:
        return _require("INTERNAL_API_SECRET")

    @property
    def orchestrator_host(self) -> str:
        return _optional("ORCHESTRATOR_HOST", "http://localhost:8000")

    # TradingView
    @property
    def tradingview_webhook_secret(self) -> str:
        return _require("TRADINGVIEW_WEBHOOK_SECRET")

    # IBKR
    @property
    def ibkr_client_portal_url(self) -> str:
        return _optional("IBKR_CLIENT_PORTAL_URL", "https://localhost:5000")

    @property
    def ibkr_account_id(self) -> Optional[str]:
        return _optional("IBKR_ACCOUNT_ID")

    # Google Calendar
    @property
    def google_client_id(self) -> Optional[str]:
        return _optional("GOOGLE_CLIENT_ID")

    @property
    def google_client_secret(self) -> Optional[str]:
        return _optional("GOOGLE_CLIENT_SECRET")

    @property
    def google_cal_token(self) -> Optional[str]:
        return _optional("GOOGLE_CAL_TOKEN")

    # Apple CalDAV
    @property
    def apple_caldav_url(self) -> str:
        return _optional("APPLE_CALDAV_URL", "https://caldav.icloud.com")

    @property
    def apple_caldav_user(self) -> Optional[str]:
        return _optional("APPLE_CALDAV_USER")

    @property
    def apple_caldav_token(self) -> Optional[str]:
        return _optional("APPLE_CALDAV_TOKEN")

    # Research
    @property
    def tavily_api_key(self) -> Optional[str]:
        return _optional("TAVILY_API_KEY")

    # Misc
    @property
    def log_level(self) -> str:
        return _optional("LOG_LEVEL", "INFO").upper()

    @property
    def environment(self) -> str:
        return _optional("ENVIRONMENT", "development")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"
