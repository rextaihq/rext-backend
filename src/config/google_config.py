from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GoogleConfig(BaseSettings):
    """Configuration for the Google Search Console / GA4 background sync job."""

    GOOGLE_SYNC_ENABLED: bool = True
    GOOGLE_SYNC_INTERVAL_HOURS: int = Field(default=6, ge=1, le=48)
    GOOGLE_SYNC_LOOKBACK_DAYS: int = Field(default=7, ge=1, le=90)
    # First time a site's SiteDailyMetric is synced, pull this much history
    # so the dashboard's period-over-period comparison (e.g. 28d vs previous
    # 28d) has data immediately instead of accruing over weeks.
    GOOGLE_SYNC_SITE_BACKFILL_DAYS: int = Field(default=90, ge=1, le=480)

    # Search Console URL Inspection (→ "Indexed Pages" dashboard KPI).
    # Google enforces a per-property quota (commonly ~2,000/day, ~600/min at
    # time of writing) — verify current limits in the Search Console API
    # quota dashboard and tune these accordingly; defaults here are
    # intentionally conservative.
    GOOGLE_INDEX_INSPECTION_ENABLED: bool = True
    GOOGLE_INDEX_INSPECTION_INTERVAL_HOURS: int = Field(default=24, ge=1, le=168)
    GOOGLE_INDEX_INSPECTION_DAILY_QUOTA_PER_SITE: int = Field(default=200, ge=1, le=100000)
    GOOGLE_INDEX_INSPECTION_PER_MINUTE_LIMIT: int = Field(default=300, ge=1, le=10000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )


google_config = GoogleConfig()
