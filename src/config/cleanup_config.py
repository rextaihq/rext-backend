from datetime import timedelta
from typing import Dict

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config.hidden_secrets import HidesSecrets


class CleanupConfig(HidesSecrets, BaseSettings):
    """Configuration for data cleanup and scheduled retention policies."""

    # Retention periods (days)
    AUDIT_LOG_RETENTION_DAYS: int = Field(default=365, ge=1, le=3650)
    EMAIL_LOG_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)
    EMAIL_EVENT_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)
    # error_logs was the only monitoring table with no retention, so it grew
    # without bound. Kept shorter than audit logs: these rows are an
    # operational signal for diagnosing a live problem, not a compliance
    # record, and a dependency outage can write them in volume.
    ERROR_LOG_RETENTION_DAYS: int = Field(default=90, ge=1, le=3650)
    USER_SESSION_INACTIVE_DAYS: int = Field(default=7, ge=1, le=3650)
    # Read by anonymize_cancelled_subscriptions, which cleanup_all doesn't run yet.
    CANCELLED_SUBSCRIPTION_RETENTION_DAYS: int = Field(default=90, ge=1, le=3650)

    # Scheduler toggles
    SCHEDULER_ENABLED: bool = True
    CLEANUP_ENABLED: bool = True
    BILLING_TASKS_ENABLED: bool = True
    TRIAL_TASKS_ENABLED: bool = True
    DIGEST_TASKS_ENABLED: bool = True
    # The reminder a pending workspace invitation gets two days before it expires.
    INVITATION_REMINDERS_ENABLED: bool = True
    WEBHOOK_REPROCESS_TASKS_ENABLED: bool = True
    # Nightly re-read of every unfinished subscription from Lemon Squeezy (F11).
    SUBSCRIPTION_RECONCILE_ENABLED: bool = True

    # How often live API counters are copied into api_usage_hourly. Must stay
    # well below the Redis metric TTL so no bucket expires undrained.
    API_USAGE_ROLLUP_INTERVAL_MINUTES: int = 10

    # Schedule
    CLEANUP_HOUR: int = Field(default=2, ge=0, le=23)
    CLEANUP_MINUTE: int = Field(default=0, ge=0, le=59)
    # Email digest — checked daily; each user receives one per their cadence.
    DIGEST_HOUR: int = Field(default=8, ge=0, le=23)
    DIGEST_MINUTE: int = Field(default=0, ge=0, le=59)
    # Invitation reminders — once a day (UTC).
    INVITATION_REMINDER_HOUR: int = Field(default=9, ge=0, le=23)
    INVITATION_REMINDER_MINUTE: int = Field(default=0, ge=0, le=59)

    # Operational controls
    CLEANUP_BATCH_SIZE: int = Field(default=1000, ge=1, le=100000)
    # The nightly cleanup only counts and logs what it would delete, per table,
    # until this is turned off: its deletes never ran before, so the first runs
    # show how much is past each period before anything is removed.
    CLEANUP_DRY_RUN: bool = True

    # Scheduled publish retry
    # Fixed (non-exponential) interval so a transient failure doesn't drift the
    # publish far past the time the user actually scheduled it for.
    SCHEDULED_PUBLISH_MAX_RETRIES: int = Field(default=3, ge=1, le=10)
    SCHEDULED_PUBLISH_RETRY_INTERVAL_MINUTES: int = Field(default=3, ge=1, le=1440)

    # Failed-webhook automatic reprocessing (LemonSqueezy webhook monitoring).
    # Events are retried at most WEBHOOK_REPROCESS_MAX_RETRIES times; an event is
    # only picked up once its last attempt is older than the backoff window.
    WEBHOOK_REPROCESS_MAX_RETRIES: int = Field(default=5, ge=1, le=20)
    WEBHOOK_REPROCESS_BACKOFF_MINUTES: int = Field(default=15, ge=1, le=1440)
    WEBHOOK_REPROCESS_INTERVAL_MINUTES: int = Field(default=10, ge=1, le=1440)
    WEBHOOK_REPROCESS_BATCH_LIMIT: int = Field(default=25, ge=1, le=500)
    WEBHOOK_REPROCESS_LOOKBACK_HOURS: int = Field(default=72, ge=1, le=720)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    def get_retention_periods(self) -> Dict[str, timedelta]:
        return {
            "audit_logs": timedelta(days=self.AUDIT_LOG_RETENTION_DAYS),
            "email_logs": timedelta(days=self.EMAIL_LOG_RETENTION_DAYS),
            "email_events": timedelta(days=self.EMAIL_EVENT_RETENTION_DAYS),
            "error_logs": timedelta(days=self.ERROR_LOG_RETENTION_DAYS),
            "user_sessions": timedelta(days=self.USER_SESSION_INACTIVE_DAYS),
        }

    def get_retention_summary(self) -> Dict[str, str]:
        return {
            "audit_logs": f"{self.AUDIT_LOG_RETENTION_DAYS} days",
            "email_logs": f"{self.EMAIL_LOG_RETENTION_DAYS} days",
            "email_events": f"{self.EMAIL_EVENT_RETENTION_DAYS} days",
            "error_logs": f"{self.ERROR_LOG_RETENTION_DAYS} days",
            "user_sessions": f"{self.USER_SESSION_INACTIVE_DAYS} days (inactive)",
        }


cleanup_config = CleanupConfig()
