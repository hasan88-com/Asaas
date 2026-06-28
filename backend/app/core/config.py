"""
Asaas (اثاثہ) — Core Configuration

Pydantic Settings class reading all env vars.
Secrets in env only (RULES.md A3.6).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env — resolved from this file so it loads regardless of the
# working directory uvicorn is launched from.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    environment: str = "development"
    app_name: str = "Asaas"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> List[str]:
        import json
        val = self.cors_origins.strip()
        # Handle JSON array format e.g. ["https://foo.com"] set via some dashboards
        if val.startswith("["):
            try:
                parsed = json.loads(val)
                origins = [o.strip().rstrip("/") for o in parsed]
            except Exception:
                origins = [o.strip().rstrip("/") for o in val.split(",")]
        else:
            origins = [o.strip().rstrip("/") for o in val.split(",")]
        return origins

    # --- Database ---
    # Use Supabase pooler URL (PgBouncer) for the application.
    # Use the direct connection URL for Alembic migrations.
    database_url: str = "postgresql+asyncpg://postgres.yourproject:yourpassword@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
    database_url_sync: str = "postgresql://postgres:yourpassword@db.yourproject.supabase.co:5432/postgres"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Supabase Auth ---
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    # JWT secret from Supabase dashboard → Settings → API → JWT Settings
    supabase_jwt_secret: str = ""

    # --- LLM Providers ---
    gemini_api_key: str = ""
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    openrouter_api_key: str = ""

    # --- Data Sources ---
    coingecko_api_key: str = ""
    fred_api_key: str = ""
    alpha_vantage_api_key: str = ""

    # --- Guest Mode ---
    guest_free_runs: int = 3


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
