"""
Application configuration — validates all required environment variables at import time.

The server must NOT start if any required env var is missing.
"""

import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Required fields (missing any of these will raise a ValidationError at startup) ---
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    DATABASE_URL: str
    ANTHROPIC_API_KEY: str
    UPSTASH_REDIS_URL: str
    DEEPGRAM_API_KEY: str
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    SECRET_KEY: str

    # --- Optional fields with sensible defaults ---
    ENVIRONMENT: str = "development"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    API_BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    LOG_LEVEL: str = "INFO"


# Module-level singleton — import this directly from other modules.
# Raises pydantic_settings.ValidationError (subclass of ValueError) immediately if
# any required variable is absent, so the process exits before it can serve traffic.
settings = Settings()
