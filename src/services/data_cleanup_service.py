"""
Data Cleanup Service

Handles cleanup of old data based on retention policies.
Provides methods for cleaning up different table types with proper logging.
"""

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.admin_models.error_log import ErrorLog
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.email_models.email_event import EmailEvent
from src.api.models.email_models.email_log import EmailLog
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.user_sessions import UserSession
from src.config.cleanup_config import cleanup_config
from src.services.plan_change_charges import PAID, REFUNDED
from src.utils.logger import logger

# The payment events the admin's refund rows are read from (plan_change_charges):
# kept however old they are, until the invoices themselves are recorded
# (rext-control#804). An admin's refund has no time limit.
KEPT_WEBHOOK_EVENTS = (PAID, REFUNDED)


class DataCleanupIncomplete(Exception):
    """cleanup_all ran every step and some of them failed. ``failed`` names them;
    ``results`` holds the count of each step that ran."""

    def __init__(self, failed: List[str], results: Dict[str, int]):
        self.failed = failed
        self.results = results
        super().__init__(f"Data cleanup steps failed: {', '.join(failed)}")


class DataCleanupService:
    """Service for cleaning up old data based on retention policies.

    Deletes run in batches and commit each batch, so no transaction stays open
    across a large table, and a run that fails part-way keeps what it deleted.
    """

    def __init__(self, db: AsyncSession, dry_run: bool = False):
        """
        Initialize cleanup service.

        Args:
            db: Async database session
            dry_run: If True, only count records without deleting
        """
        self.db = db
        self.dry_run = dry_run

    async def _delete_in_batches(self, model, *conditions) -> int:
        """
        Delete the rows that match the conditions, one batch at a time.

        PostgreSQL has no DELETE ... LIMIT, so each batch deletes the ids a
        limited select picks, and is committed before the next one starts.
        The delete repeats the conditions: a row updated after the select
        picked it (a session refreshed meanwhile) is checked again as it now
        is, and kept. "fetch" takes the deleted rows out of the session too, so
        a caller that loaded one doesn't still see it.

        It ends with the first batch that deletes nothing. A batch can delete
        fewer rows than it picked (the kept ones above) while more wait beyond
        its limit, so a short batch is not the end.

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        if self.dry_run:
            count_result = await self.db.execute(
                select(func.count()).select_from(model).where(*conditions)
            )
            return count_result.scalar() or 0

        deleted_total = 0
        batch_size = cleanup_config.CLEANUP_BATCH_SIZE

        while True:
            batch = select(model.id).where(*conditions).limit(batch_size)
            result = await self.db.execute(
                delete(model)
                .where(model.id.in_(batch), *conditions)
                .execution_options(synchronize_session="fetch")
            )
            await self.db.commit()

            deleted_batch = result.rowcount
            deleted_total += deleted_batch

            logger.debug(
                f"Deleted batch of {deleted_batch} rows from {model.__tablename__} "
                f"(total: {deleted_total})"
            )

            if deleted_batch <= 0:
                return deleted_total

    def _log_result(self, count: int, records: str, **context) -> None:
        """Log what a cleanup step deleted, or would delete in dry-run mode."""
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would delete {count} {records}",
                extra={"would_delete": count, **context},
            )
        elif count:
            logger.info(
                f"Deleted {count} {records}",
                extra={"deleted_count": count, **context},
            )
        else:
            logger.info(f"No {records} to clean up")

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
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()},
        )

        deleted = await self._delete_in_batches(AuditLog, AuditLog.created_at < cutoff_date)
        self._log_result(deleted, "audit logs", retention_days=retention_days)
        return deleted

    async def cleanup_error_logs(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up old error logs.

        error_logs had no retention at all while every other monitoring table
        had one, so it grew without bound. That matters more now that
        infrastructure outages and third-party failures are recorded: a
        dependency that is down writes rows for as long as it stays down.

        Args:
            retention_days: Number of days to retain (default from config)

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        retention_days = retention_days or cleanup_config.ERROR_LOG_RETENTION_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning error logs older than "
            f"{cutoff_date.isoformat()}",
            extra={
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
            },
        )

        deleted = await self._delete_in_batches(ErrorLog, ErrorLog.timestamp < cutoff_date)
        self._log_result(deleted, "error logs", retention_days=retention_days)
        return deleted

    async def cleanup_email_logs(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up old email logs.

        Their events are kept with email_log_id set to NULL (ON DELETE SET NULL),
        and cleanup_email_events deletes those orphans once they are old enough.

        Args:
            retention_days: Number of days to retain (default from config)

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        retention_days = retention_days or cleanup_config.EMAIL_LOG_RETENTION_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning email logs older than {cutoff_date.isoformat()}",
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()},
        )

        deleted = await self._delete_in_batches(EmailLog, EmailLog.created_at < cutoff_date)
        self._log_result(deleted, "email logs", retention_days=retention_days)
        return deleted

    async def cleanup_email_events(
        self,
        retention_days: Optional[int] = None,
        logs_older_than: Optional[datetime] = None,
    ) -> int:
        """
        Clean up orphaned email events (events without email_log).

        Args:
            retention_days: Number of days to retain (default from config)
            logs_older_than: Also take the events whose email log is older than this.
                cleanup_all's dry run passes the email logs' cutoff: a real run has
                just deleted those logs (orphaning their events), and the dry run,
                which hasn't, then counts the same events.

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """
        retention_days = retention_days or cleanup_config.EMAIL_EVENT_RETENTION_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning orphaned email events older than {cutoff_date.isoformat()}",
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()},
        )

        orphaned = EmailEvent.email_log_id.is_(None)
        if logs_older_than is not None:
            orphaned = orphaned | EmailEvent.email_log_id.in_(
                select(EmailLog.id).where(EmailLog.created_at < logs_older_than)
            )

        deleted = await self._delete_in_batches(
            EmailEvent, EmailEvent.created_at < cutoff_date, orphaned
        )
        self._log_result(deleted, "orphaned email events", retention_days=retention_days)
        return deleted

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
            extra={"inactive_days": inactive_days, "cutoff_date": cutoff_date.isoformat()},
        )

        # Inactive OR expired OR revoked
        deleted = await self._delete_in_batches(
            UserSession,
            (UserSession.last_activity_at < cutoff_date)
            | (UserSession.expires_at < now)
            | (UserSession.revoked_at.isnot(None)),
        )
        self._log_result(deleted, "inactive/expired sessions", inactive_days=inactive_days)
        return deleted

    async def cleanup_webhook_events(self, retention_days: Optional[int] = None) -> int:
        """
        Clean up old webhook events (processed events older than retention period).

        The payment events in KEPT_WEBHOOK_EVENTS are never deleted.

        Args:
            retention_days: Number of days to retain (default from config)

        Returns:
            Number of records deleted (or would be deleted in dry-run mode)
        """

        retention_days = retention_days or cleanup_config.WEBHOOK_EVENT_RETENTION_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Cleaning processed webhook events older than {cutoff_date.isoformat()}",
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()},
        )

        # Only processed events: an unprocessed one may still need attention
        deleted = await self._delete_in_batches(
            WebhookEvent,
            WebhookEvent.created_at < cutoff_date,
            WebhookEvent.processed.is_(True),
            WebhookEvent.event_name.notin_(KEPT_WEBHOOK_EVENTS),
        )
        self._log_result(deleted, "processed webhook events", retention_days=retention_days)
        return deleted

    async def anonymize_cancelled_subscriptions(self, retention_days: Optional[int] = None) -> int:
        """
        Anonymize user_id from cancelled/expired subscriptions older than retention period.
        Keeps subscription data for financial records but removes link to user.

        NOTE: This does NOT delete subscriptions (required for 7-year financial record retention).
        It only anonymizes them by setting user_id to NULL.

        Not run by cleanup_all: user_subscriptions.user_id is NOT NULL, so the
        update can't be stored until the anonymization is designed (a migration,
        and a decision about which financial records keep their owner).

        Args:
            retention_days: Number of days to retain user link (default from config)

        Returns:
            Number of records anonymized (or would be anonymized in dry-run mode)
        """
        retention_days = retention_days or cleanup_config.CANCELLED_SUBSCRIPTION_RETENTION_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Anonymizing cancelled subscriptions older than {cutoff_date.isoformat()}",
            extra={"retention_days": retention_days, "cutoff_date": cutoff_date.isoformat()},
        )

        # Count records to be anonymized (cancelled/expired subscriptions with user_id still set)
        count_result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.updated_at < cutoff_date,
                UserSubscription.status.in_(["cancelled", "expired"]),
                UserSubscription.user_id.isnot(None),
            )
        )
        record_count = count_result.scalar()

        if record_count == 0:
            logger.info("No cancelled subscriptions to anonymize")
            return 0

        if not self.dry_run:
            # Anonymize by setting user_id to NULL (keep subscription for financial records)

            result = await self.db.execute(
                update(UserSubscription)
                .where(
                    UserSubscription.updated_at < cutoff_date,
                    UserSubscription.status.in_(["cancelled", "expired"]),
                    UserSubscription.user_id.isnot(None),
                )
                .values(user_id=None)
                .returning(UserSubscription.id)
            )
            anonymized_count = len(result.fetchall())
            await self.db.flush()

            logger.info(
                f"Anonymized {anonymized_count} cancelled subscriptions (user_id set to NULL)",
                extra={"anonymized_count": anonymized_count, "retention_days": retention_days},
            )
            return anonymized_count
        else:
            logger.info(
                f"[DRY RUN] Would anonymize {record_count} cancelled subscriptions",
                extra={"would_anonymize": record_count, "retention_days": retention_days},
            )
            return record_count

    async def cleanup_all(self) -> Dict[str, int]:
        """
        Run all cleanup tasks.

        Every step runs, whatever happened to the one before it: a table whose
        cleanup fails doesn't cost the others theirs.

        Returns:
            Dictionary with cleanup results for each table

        Raises:
            DataCleanupIncomplete: after the last step, when any step failed
        """
        logger.info(f"{'[DRY RUN] ' if self.dry_run else ''}Starting full data cleanup")

        email_logs_cutoff = datetime.now(timezone.utc) - timedelta(
            days=cleanup_config.EMAIL_LOG_RETENTION_DAYS
        )
        steps: Tuple[Tuple[str, Callable[[], Awaitable[int]]], ...] = (
            ("audit_logs", self.cleanup_audit_logs),
            ("email_logs", self.cleanup_email_logs),
            (
                "email_events",
                # A real run has just deleted the old logs, and the database unlinked
                # their events: they are orphans by now. Only the dry run, which
                # deleted nothing, has to be told which events those would be. And when
                # the logs' step failed, the events of the logs still there stay.
                lambda: self.cleanup_email_events(
                    logs_older_than=email_logs_cutoff if self.dry_run else None
                ),
            ),
            ("error_logs", self.cleanup_error_logs),
            ("user_sessions", self.cleanup_inactive_sessions),
            ("webhook_events", self.cleanup_webhook_events),
            ("cleanup_expired_tokens", self.cleanup_expired_tokens),
        )
        results: Dict[str, int] = {}
        failed: List[str] = []
        for name, step in steps:
            try:
                results[name] = await step()
            except Exception as error:  # noqa: BLE001 - the next step still runs
                failed.append(name)
                logger.error(
                    f"Data cleanup step failed: {name}",
                    exc_info=True,
                    extra={"step": name, "error": type(error).__name__},
                )
                # A failed statement leaves the transaction unusable for the next step.
                await self.db.rollback()

        total_deleted = sum(results.values())

        logger.info(
            f"{'[DRY RUN] ' if self.dry_run else ''}Data cleanup completed: {total_deleted} total records {'would be ' if self.dry_run else ''}deleted",
            extra={"results": results, "total": total_deleted, "failed": failed},
        )

        if failed:
            raise DataCleanupIncomplete(failed, results)
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

        deleted = await self._delete_in_batches(
            TokenBlacklist, TokenBlacklist.expires_at < cutoff_date
        )
        self._log_result(deleted, "expired tokens from blacklist")
        return deleted
