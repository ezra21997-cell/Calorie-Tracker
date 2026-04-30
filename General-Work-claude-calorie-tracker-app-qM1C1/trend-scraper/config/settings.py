"""
Application settings loaded from environment variables.
All defaults are suitable for local development.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg2://trend_user:trend_pass@localhost:5432/trend_db"

    # ── Redis (optional – used for caching / Celery broker) ───────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── API ───────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False

    # ── Ingestion ─────────────────────────────────────────────────────────
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "trend-scraper/1.0"
    reddit_subreddit: str = "all"
    reddit_post_limit: int = 50

    # Google Trends (pytrends – no API key required)
    google_trends_geo: str = ""            # e.g. "US"
    google_trends_hl: str = "en-US"

    # ── Scheduler ─────────────────────────────────────────────────────────
    scheduler_interval_seconds: int = 900  # 15 minutes

    # ── Scoring ───────────────────────────────────────────────────────────
    scoring_recent_window_minutes: int = 60
    scoring_baseline_window_hours: int = 24
    scoring_recency_decay: float = 0.9    # λ for time-decay

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_json: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
