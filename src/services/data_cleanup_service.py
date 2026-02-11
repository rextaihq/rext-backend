"""
Data Cleanup Service

Handles cleanup of old data based on retention policies.
Provides methods for cleaning up different table types with proper logging.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.models.user_models.token_blacklist import TokenBlacklist

from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.email_models.email_log import EmailLog
from src.api.models.email_models.email_event import EmailEvent
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.config.cleanup_config import cleanup_config
from src.utils.logger import logger


class DataCleanupService:
    """Service for cleaning up old data based on retention policies."""

    def __init__(self, db: AsyncSession, dry_run: bool = False):
        """
        Initialize cleanup service.

        Args:
            db: Async database session
            dry_run: If True, only count records without deleting
        """
        self.db = db
        self.dry_run = dry_run

    async def cleanup_audit_logs(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up old audit logs.

        Args:
            retention_days: Number of days to retain (default from config)

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        retention_days = retention_days or cleanup_config.AUDIT_LOG_RETENTION_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning audit logs older than {cutoff_date.isoformat()}",
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()}
        )

        # Count records to be deleted
        count_result = await self.db.execute(
            select(func.count(AuditLog.id))
            .where(AuditLog.created_at < cutoff_date)
        )
        record_count = count_result.scalar()

        if record_count == 0:
            logger.info("No audit logs to clean up")
            return 0

        if not self.dry_run:
            # Delete in batches to avoid long-running transactions
            deleted_total = 0
            batch_size = cleanup_config.CLEANUP_BATCH_SIZE

            while True:
                # Delete a batch
                result = await self.db.execute(
                    delete(AuditLog)
                    .where(AuditLog.created_at < cutoff_date)
                    .execution_options(synchronize_session=False)
                    .returning(AuditLog.id)
                    .limit(batch_size)
                )
                deleted_batch = len(result.fetchall())

                if deleted_batch == 0:
                    break

                deleted_total += deleted_batch
                await self.db.flush()

                logger.debug(f"Deleted batch of {deleted_batch} audit logs (total: {deleted_total})")

                if deleted_batch < batch_size:
                    break

            logger.info(
                f"Deleted {deleted_total} audit logs",
                extra={"deleted_count": deleted_total, "retention_days": retention_days}
            )
            return deleted_total
        else:
            logger.info(
                f"[DRY RUN] Would delete {record_count} audit logs",
                extra={"would_delete": record_count, "retention_days": retention_days}
            )
            return record_count

    async def cleanup_email_logs(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up old email logs and associated events.

        Args:
            retention_days: Number of days to retain (default from config)

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        retention_days = retention_days or cleanup_config.EMAIL_LOG_RETENTION_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning email logs older than {cutoff_date.isoformat()}",
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()}
        )

        # Count records to be deleted
        count_result = await self.db.execute(
            select(func.count(EmailLog.id))
            .where(EmailLog.created_at < cutoff_date)
        )
        record_count = count_result.scalar()

        if record_count == 0:
            logger.info("No email logs to clean up")
            return 0

        if not self.dry_run:
            # EmailEvents will be deleted via CASCADE
            deleted_total = 0
            batch_size = cleanup_config.CLEANUP_BATCH_SIZE

            while True:
                result = await self.db.execute(
                    delete(EmailLog)
                    .where(EmailLog.created_at < cutoff_date)
                    .execution_options(synchronize_session=False)
                    .returning(EmailLog.id)
                    .limit(batch_size)
                )
                deleted_batch = len(result.fetchall())

                if deleted_batch == 0:
                    break

                deleted_total += deleted_batch
                await self.db.flush()

                logger.debug(f"Deleted batch of {deleted_batch} email logs (total: {deleted_total})")

                if deleted_batch < batch_size:
                    break

            logger.info(
                f"Deleted {deleted_total} email logs (events deleted via CASCADE)",
                extra={"deleted_count": deleted_total, "retention_days": retention_days}
            )
            return deleted_total
        else:
            logger.info(
                f"[DRY RUN] Would delete {record_count} email logs",
                extra={"would_delete": record_count, "retention_days": retention_days}
            )
            return record_count

    async def cleanup_email_events(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up orphaned email events (events without email_log).

        Args:
            retention_days: Number of days to retain (default from config)

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        retention_days = retention_days or cleanup_config.EMAIL_EVENT_RETENTION_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning orphaned email events older than {cutoff_date.isoformat()}",
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()}
        )

        # Count orphaned records (email_log_id is NULL) to be deleted
        count_result = await self.db.execute(
            select(func.count(EmailEvent.id))
            .where(
                EmailEvent.created_at < cutoff_date,
                EmailEvent.email_log_id.is_(None)
            )
        )
        record_count = count_result.scalar()

        if record_count == 0:
            logger.info("No orphaned email events to clean up")
            return 0

        if not self.dry_run:
            deleted_total = 0
            batch_size = cleanup_config.CLEANUP_BATCH_SIZE

            while True:
                result = await self.db.execute(
                    delete(EmailEvent)
                    .where(
                        EmailEvent.created_at < cutoff_date,
                        EmailEvent.email_log_id.is_(None)
                    )
                    .execution_options(synchronize_session=False)
                    .returning(EmailEvent.id)
                    .limit(batch_size)
                )
                deleted_batch = len(result.fetchall())

                if deleted_batch == 0:
                    break

                deleted_total += deleted_batch
                await self.db.flush()

                logger.debug(f"Deleted batch of {deleted_batch} orphaned email events (total: {deleted_total})")

                if deleted_batch < batch_size:
                    break

            logger.info(
                f"Deleted {deleted_total} orphaned email events",
                extra={"deleted_count": deleted_total, "retention_days": retention_days}
            )
            return deleted_total
        else:
            logger.info(
                f"[DRY RUN] Would delete {record_count} orphaned email events",
                extra={"would_delete": record_count, "retention_days": retention_days}
            )
            return record_count

    async def cleanup_inactive_sessions(self, inactive_days: Optional[int] = None) -> int:
        """
        Clean up inactive and expired user sessions.

        Args:
            inactive_days: Number of days of inactivity before cleanup (default from config)

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        inactive_days = inactive_days or cleanup_config.USER_SESSION_INACTIVE_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=inactive_days)
        now = datetime.now(timezone.utc)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning inactive sessions (last_activity < {cutoff_date.isoformat()}) or expired",
            extra={"inactive_days": inactive_days, "cutoff_date": cutoff_date.isoformat()}
        )

        # Count records to be deleted (inactive OR expired OR revoked)
        count_result = await self.db.execute(
            select(func.count(UserSession.id))
            .where(
                (UserSession.last_activity_at < cutoff_date) |
                (UserSession.expires_at < now) |
                (UserSession.revoked_at.isnot(None))
            )
        )
        record_count = count_result.scalar()

        if record_count == 0:
            logger.info("No inactive sessions to clean up")
            return 0

        if not self.dry_run:
            deleted_total = 0
            batch_size = cleanup_config.CLEANUP_BATCH_SIZE

            while True:
                result = await self.db.execute(
                    delete(UserSession)
                    .where(
                        (UserSession.last_activity_at < cutoff_date) |
                        (UserSession.expires_at < now) |
                        (UserSession.revoked_at.isnot(None))
                    )
                    .execution_options(synchronize_session=False)
                    .returning(UserSession.id)
                    .limit(batch_size)
                )
                deleted_batch = len(result.fetchall())

                if deleted_batch == 0:
                    break

                deleted_total += deleted_batch
                await self.db.flush()

                logger.debug(f"Deleted batch of {deleted_batch} inactive sessions (total: {deleted_total})")

                if deleted_batch < batch_size:
                    break

            logger.info(
                f"Deleted {deleted_total} inactive/expired sessions",
                extra={"deleted_count": deleted_total, "inactive_days": inactive_days}
            )
            return deleted_total
        else:
            logger.info(
                f"[DRY RUN] Would delete {record_count} inactive/expired sessions",
                extra={"would_delete": record_count, "inactive_days": inactive_days}
            )
            return record_count

    async def cleanup_webhook_events(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up old webhook events (processed events older than retention period).

        Args:
            retention_days: Number of days to retain (default 90 days)

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        retention_days = retention_days or 90  # Default 90 days for webhook events
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning processed webhook events older than {cutoff_date.isoformat()}",
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()}
        )

        # Count records to be deleted (only processed events)
        count_result = await self.db.execute(
            select(func.count(WebhookEvent.id))
            .where(
                WebhookEvent.created_at < cutoff_date,
                WebhookEvent.processed.is_(True)
            )
        )
        record_count = count_result.scalar()

        if record_count == 0:
            logger.info("No webhook events to clean up")
            return 0

        if not self.dry_run:
            deleted_total = 0
            batch_size = cleanup_config.CLEANUP_BATCH_SIZE

            while True:
                result = await self.db.execute(
                    delete(WebhookEvent)
                    .where(
                        WebhookEvent.created_at < cutoff_date,
                        WebhookEvent.processed.is_(True)
                    )
                    .execution_options(synchronize_session=False)
                    .returning(WebhookEvent.id)
                    .limit(batch_size)
                )
                deleted_batch = len(result.fetchall())

                if deleted_batch == 0:
                    break

                deleted_total += deleted_batch
                await self.db.flush()

                logger.debug(f"Deleted batch of {deleted_batch} webhook events (total: {deleted_total})")

                if deleted_batch < batch_size:
                    break

            logger.info(
                f"Deleted {deleted_total} processed webhook events",
                extra={"deleted_count": deleted_total, "retention_days": retention_days}
            )
            return deleted_total
        else:
            logger.info(
                f"[DRY RUN] Would delete {record_count} processed webhook events",
                extra={"would_delete": record_count, "retention_days": retention_days}
            )
            return record_count

    async def anonymize_cancelled_subscriptions(self, retention_days: Optional[int] = None) -> int:
        """
        Anonymize user_id from cancelled/expired subscriptions older than retention period.
        Keeps subscription data for financial records but removes link to user.

        NOTE: This does NOT delete subscriptions (required for 7-year financial record retention).
        It only anonymizes them by setting user_id to NULL.

        Args:
            retention_days: Number of days to retain user link (default 90 days after cancellation)

        Returns:
            Number of records anonymized (or would be anonymized in dry-run mode)
        """
        retention_days = retention_days or 90  # Default 90 days after cancellation
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Anonymizing cancelled subscriptions older than {cutoff_date.isoformat()}",
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()}
        )

        # Count records to be anonymized (cancelled/expired subscriptions with user_id still set)
        count_result = await self.db.execute(
            select(func.count(UserSubscription.id))
            .where(
                UserSubscription.updated_at < cutoff_date,
                UserSubscription.status.in_(["cancelled", "expired"]),
                UserSubscription.user_id.isnot(None)
            )
        )
        record_count = count_result.scalar()

        if record_count == 0:
            logger.info("No cancelled subscriptions to anonymize")
            return 0

        if not self.dry_run:
            # Anonymize by setting user_id to NULL (keep subscription for financial records)
            from sqlalchemy import update

            result = await self.db.execute(
                update(UserSubscription)
                .where(
                    UserSubscription.updated_at < cutoff_date,
                    UserSubscription.status.in_(["cancelled", "expired"]),
                    UserSubscription.user_id.isnot(None)
                )
                .values(user_id=None)
                .returning(UserSubscription.id)
            )
            anonymized_count = len(result.fetchall())
            await self.db.flush()

            logger.info(
                f"Anonymized {anonymized_count} cancelled subscriptions (user_id set to NULL)",
                extra={"anonymized_count": anonymized_count, "retention_days": retention_days}
            )
            return anonymized_count
        else:
            logger.info(
                f"[DRY RUN] Would anonymize {record_count} cancelled subscriptions",
                extra={"would_anonymize": record_count, "retention_days": retention_days}
            )
            return record_count

    async def cleanup_all(self) -> Dict[str, int]:
        """
        Run all cleanup tasks.

        Returns:
            Dictionary with cleanup results for each table
        """
        logger.info(f"{'[DRY RUN] ' if self.dry_run else ''}Starting full data cleanup")

        results = {
            "audit_logs": await self.cleanup_audit_logs(),
            "email_logs": await self.cleanup_email_logs(),
            "email_events": await self.cleanup_email_events(),
            "user_sessions": await self.cleanup_inactive_sessions(),
            "webhook_events": await self.cleanup_webhook_events(),
            "cancelled_subscriptions_anonymized": await self.anonymize_cancelled_subscriptions(),
            "cleanup_expired_tokens": await self.cleanup_expired_tokens()
        }

        total_deleted = sum(results.values())

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Data cleanup completed: {total_deleted} total records {'would be ' if self.dry_run else ''}deleted/anonymized",
            extra={"results": results, "total": total_deleted}
        )

        return results
    
    async def cleanup_expired_tokens(self) -> int:
        """
        Clean up expired tokens from the blacklist.

        Expired tokens can be safely removed since they would be
        rejected anyway due to expiration.

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        cutoff_date = datetime.now(timezone.utc)

        if self.dry_run:
            count_stmt = select(func.count()).select_from(TokenBlacklist).where(
                TokenBlacklist.expires_at < cutoff_date
            )
            result = await self.db.execute(count_stmt)
            count = result.scalar() or 0
            logger.info(f"[DRY RUN] Would delete {count} expired tokens from blacklist")
            return count

        stmt = delete(TokenBlacklist).where(
            TokenBlacklist.expires_at < cutoff_date
        )
        result = await self.db.execute(stmt)
        deleted = result.rowcount
        await self.db.flush()

        logger.info(f"Cleaned up {deleted} expired tokens from blacklist")
        return deleted
