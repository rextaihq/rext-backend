from datetime import timedelta
from typing import Dict

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CleanupConfig(BaseSettings):
    """Configuration for data cleanup and scheduled retention policies."""

    # Retention periods (days)
    AUDIT_LOG_RETENTION_DAYS: int = Field(default=365, ge=1, le=3650)
    EMAIL_LOG_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)
    EMAIL_EVENT_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)
    USER_SESSION_INACTIVE_DAYS: int = Field(default=7, ge=1, le=3650)

    # Scheduler toggles
    SCHEDULER_ENABLED: bool = True
    CLEANUP_ENABLED: bool = True
    BILLING_TASKS_ENABLED: bool = True
    TRIAL_TASKS_ENABLED: bool = True
    DUNNING_TASKS_ENABLED: bool = True
    GRACE_PERIOD_TASKS_ENABLED: bool = True

    # Schedule
    CLEANUP_HOUR: int = Field(default=2, ge=0, le=23)
    CLEANUP_MINUTE: int = Field(default=0, ge=0, le=59)

    # Operational controls
    CLEANUP_BATCH_SIZE: int = Field(default=1000, ge=1, le=100000)
    CLEANUP_DRY_RUN: bool = False

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
            "user_sessions": timedelta(days=self.USER_SESSION_INACTIVE_DAYS),
        }

    def get_retention_summary(self) -> Dict[str, str]:
        return {
            "audit_logs": f"{self.AUDIT_LOG_RETENTION_DAYS} days",
            "email_logs": f"{self.EMAIL_LOG_RETENTION_DAYS} days",
            "email_events": f"{self.EMAIL_EVENT_RETENTION_DAYS} days",
            "user_sessions": f"{self.USER_SESSION_INACTIVE_DAYS} days (inactive)",
        }


cleanup_config = CleanupConfig()