"""
Data Cleanup Configuration

Centralized configuration for data retention policies and cleanup operations.
Retention periods can be customized via environment variables.
"""

import os
from datetime import timedelta
from typing import Dict


class CleanupConfig:
    """Configuration for data cleanup and retention policies."""

    # Retention periods (in days) - can be overridden by environment variables
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "365"))  # 1 year for audit logs (compliance)
    EMAIL_LOG_RETENTION_DAYS: int = int(os.getenv("EMAIL_LOG_RETENTION_DAYS", "30"))
    EMAIL_EVENT_RETENTION_DAYS: int = int(os.getenv("EMAIL_EVENT_RETENTION_DAYS", "30"))
    USER_SESSION_INACTIVE_DAYS: int = int(os.getenv("USER_SESSION_INACTIVE_DAYS", "7"))

    # Cleanup schedule configuration
    # Master scheduler switch
    SCHEDULER_ENABLED: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    
    # Individual task category switches (all default to True)
    CLEANUP_ENABLED: bool = os.getenv("CLEANUP_ENABLED", "true").lower() == "true"
    BILLING_TASKS_ENABLED: bool = os.getenv("BILLING_TASKS_ENABLED", "true").lower() == "true"
    TRIAL_TASKS_ENABLED: bool = os.getenv("TRIAL_TASKS_ENABLED", "true").lower() == "true"
    DUNNING_TASKS_ENABLED: bool = os.getenv("DUNNING_TASKS_ENABLED", "true").lower() == "true"
    GRACE_PERIOD_TASKS_ENABLED: bool = os.getenv("GRACE_PERIOD_TASKS_ENABLED", "true").lower() == "true"
    
    CLEANUP_HOUR: int = int(os.getenv("CLEANUP_HOUR", "2"))  # 2 AM by default
    CLEANUP_MINUTE: int = int(os.getenv("CLEANUP_MINUTE", "0"))

    # Batch size for deletion (to avoid long-running transactions)
    CLEANUP_BATCH_SIZE: int = int(os.getenv("CLEANUP_BATCH_SIZE", "1000"))

    # Dry run mode (for testing without actual deletion)
    CLEANUP_DRY_RUN: bool = os.getenv("CLEANUP_DRY_RUN", "false").lower() == "true"

    @classmethod
    def get_retention_periods(cls) -> Dict[str, timedelta]:
        """Get retention periods as timedelta objects."""
        return {
            "audit_logs": timedelta(days=cls.AUDIT_LOG_RETENTION_DAYS),
            "email_logs": timedelta(days=cls.EMAIL_LOG_RETENTION_DAYS),
            "email_events": timedelta(days=cls.EMAIL_EVENT_RETENTION_DAYS),
            "user_sessions": timedelta(days=cls.USER_SESSION_INACTIVE_DAYS),
        }

    @classmethod
    def get_retention_summary(cls) -> Dict[str, str]:
        """Get human-readable retention summary."""
        return {
            "audit_logs": f"{cls.AUDIT_LOG_RETENTION_DAYS} days",
            "email_logs": f"{cls.EMAIL_LOG_RETENTION_DAYS} days",
            "email_events": f"{cls.EMAIL_EVENT_RETENTION_DAYS} days",
            "user_sessions": f"{cls.USER_SESSION_INACTIVE_DAYS} days (inactive)",
        }


# Singleton instance
cleanup_config = CleanupConfig()
