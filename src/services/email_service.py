"""
Email Service - Business Logic Layer

Handles email sending with database logging, retry logic, and fallback providers.
Acts as the main interface between application code and email providers.
"""

import logging
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from src.api.lib.logger import auto_logger
from src.api.models.email_models.email_log import EmailLog
from src.config.email_config import email_config
from src.providers.email.base import EmailMessage, EmailRecipient, EmailResult
from src.providers.email.factory import get_email_provider, get_fallback_email_provider
from src.utils.datetime_utils import utc_now

logger = auto_logger()

# Sentry integration (optional - only if SENTRY_DSN is configured)
try:
    import sentry_sdk

    from src.api.lib.sentry_config import add_breadcrumb

    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

    # Dummy function if Sentry not available
    def add_breadcrumb(*args, **kwargs):
        pass


class EmailService:
    """
    Service for email business logic.

    Handles:
    - Email sending via configured provider
    - Database logging of all sends
    - Automatic retry logic with fallback provider
    - Error handling and recovery
    - Email status tracking
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize Email Service.

        Args:
            db: Async SQLAlchemy database session
        """
        self.db = db
        self.primary_provider = get_email_provider()
        self.fallback_provider = get_fallback_email_provider()

        logger.debug(
            "Email service initialized",
            extra={
                "primary_provider": self.primary_provider.get_provider_name(),
                "has_fallback": self.fallback_provider is not None,
            },
        )

    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        workspace_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        template_type: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        retry_on_failure: bool = True,
        auto_commit: bool = True,
    ) -> EmailLog:
        """
        Send email with database logging and retry logic.

        Args:
            to: Recipient email address
            subject: Email subject
            html: HTML email content
            from_email: Sender email (defaults to config)
            from_name: Sender name (defaults to config)
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            reply_to: Reply-to address (optional)
            workspace_id: Associated workspace ID (optional)
            user_id: Associated user ID (optional)
            template_type: Email template type identifier (optional)
            tags: Custom tags for categorization (optional)
            retry_on_failure: Whether to retry with fallback provider on failure
            auto_commit: Whether to auto-commit transaction (default True, set False in tests)

        Returns:
            EmailLog record with send results

        Raises:
            Exception: If email_enabled is False or database operations fail

        Note:
            - Email send failures are logged but don't raise exceptions
            - Automatic fallback to secondary provider if primary fails
            - All operations logged to database for auditing
        """
        # Add breadcrumb for Sentry
        add_breadcrumb(
            message=f"Preparing to send email: {subject} to {to}",
            category="email",
            level="info",
            data={
                "to": to,
                "subject": subject,
                "template_type": template_type,
                "has_workspace": workspace_id is not None,
                "has_user": user_id is not None,
                "provider": self.primary_provider.get_provider_name(),
            },
        )

        # Check if email sending is enabled
        if not email_config.email_enabled:
            logger.warning("Email sending is disabled via configuration")
            raise Exception("Email sending is disabled")

        # Use defaults from config if not provided
        from_email = from_email or email_config.resend_from_email
        from_name = from_name or email_config.resend_from_name

        # Build email message
        message = EmailMessage(
            to=[EmailRecipient(email=to)],
            subject=subject,
            html=html,
            from_email=from_email,
            from_name=from_name,
            cc=[EmailRecipient(email=e) for e in cc] if cc else None,
            bcc=[EmailRecipient(email=e) for e in bcc] if bcc else None,
            reply_to=reply_to,
            tags=tags,
        )

        email_log = EmailLog(
            workspace_id=workspace_id,
            user_id=user_id,
            template_type=template_type,
            provider=self.primary_provider.get_provider_name(),
            to_email=to,
            from_email=from_email,
            subject=subject,
            html_content=html,  # Store HTML for retry capability
            status="queued",
            tags=tags,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        self.db.add(email_log)
        await self.db.flush()  # Get the ID but don't commit yet

        logger.info(
            "Sending email",
            extra={
                "email_log_id": str(email_log.id),
                "to": to,
                "subject": subject,
                "provider": email_log.provider,
                "template_type": template_type,
            },
        )

        # Try primary provider
        result = await self._send_with_provider(message, self.primary_provider, email_log)

        # Retry with fallback if enabled and primary failed
        if (
            not result.success
            and retry_on_failure
            and self.fallback_provider
            and email_config.email_retry_enabled
        ):
            logger.warning(
                "Primary provider failed, trying fallback",
                extra={
                    "email_log_id": str(email_log.id),
                    "primary_provider": self.primary_provider.get_provider_name(),
                    "fallback_provider": self.fallback_provider.get_provider_name(),
                },
            )

            # Update provider in log
            email_log.provider = self.fallback_provider.get_provider_name()

            result = await self._send_with_provider(message, self.fallback_provider, email_log)

        # Update log with final result
        self._update_log_with_result(email_log, result)

        # Commit transaction (unless disabled for testing)
        if auto_commit:
            await self.db.flush()  # Changed from commit() as per Task 074

        # Note: We don't refresh after commit because:
        # 1. We already have all the data we just set
        # 2. In test contexts with nested transactions, refresh after commit can fail
        # If you need fresh data from DB, query separately after this method returns

        logger.info(
            f"Email send completed: {email_log.status}",
            extra={
                "email_log_id": str(email_log.id),
                "status": email_log.status,
                "provider": email_log.provider,
                "has_message_id": email_log.provider_message_id is not None,
            },
        )

        return email_log

    async def _send_with_provider(
        self, message: EmailMessage, provider, email_log: EmailLog
    ) -> EmailResult:
        """
        Send email using specific provider with exponential backoff retry.

        Args:
            message: Email message to send
            provider: Provider instance to use
            email_log: Log entry to update

        Returns:
            EmailResult from provider
        """
        max_attempts = email_config.email_retry_max_attempts
        retry_delay = email_config.email_retry_delay_seconds

        # Create retry decorator with config-driven exponential backoff
        @retry(
            stop=stop_after_attempt(max_attempts if email_config.email_retry_enabled else 1),
            wait=wait_exponential(multiplier=1, min=retry_delay, max=retry_delay * 3),
            before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
            reraise=True,
        )
        async def _send_with_retry():
            # Increment retry count
            email_log.retry_count += 1
            await self.db.flush()

            try:
                result = await provider.send_email(message)
                return result
            except Exception as e:
                logger.error(
                    f"Provider send failed (attempt {email_log.retry_count}/{max_attempts}): {str(e)}",
                    extra={
                        "email_log_id": str(email_log.id),
                        "provider": provider.get_provider_name(),
                        "error_type": type(e).__name__,
                        "retry_count": email_log.retry_count,
                    },
                    exc_info=True,
                )

                # Alert Sentry on final failure (critical)
                if email_log.retry_count >= max_attempts and SENTRY_AVAILABLE:
                    sentry_sdk.capture_exception(e)
                    logger.critical(
                        f"Email failed after {max_attempts} attempts - Sentry alert sent",
                        extra={
                            "email_log_id": str(email_log.id),
                            "to_email": email_log.to_email,
                            "subject": email_log.subject,
                        },
                    )

                # Re-raise to trigger retry
                raise

        try:
            result = await _send_with_retry()
            return result
        except Exception as e:
            # All retries exhausted, return failed result
            logger.error(
                f"Provider send failed after all retries: {str(e)}",
                extra={
                    "email_log_id": str(email_log.id),
                    "provider": provider.get_provider_name(),
                    "final_retry_count": email_log.retry_count,
                },
            )
            return EmailResult(
                success=False,
                error=f"Provider exception after {email_log.retry_count} attempts: {str(e)}",
                provider_response={
                    "exception": type(e).__name__,
                    "error": str(e),
                    "retry_count": email_log.retry_count,
                },
            )

    def _update_log_with_result(self, email_log: EmailLog, result: EmailResult):
        """
        Update email log with send result.

        Args:
            email_log: Log entry to update
            result: Result from provider
        """
        if result.success:
            email_log.status = "sent"
            email_log.provider_message_id = result.message_id
            email_log.sent_at = utc_now()
            email_log.error_message = None
        else:
            email_log.status = "failed"
            email_log.error_message = result.error
            email_log.failed_at = utc_now()

        email_log.provider_response = result.provider_response
        email_log.updated_at = utc_now()

    async def get_email_log(self, email_log_id: UUID) -> Optional[EmailLog]:
        """
        Get email log by ID.

        Args:
            email_log_id: Email log UUID

        Returns:
            EmailLog instance or None if not found
        """
        result = await self.db.execute(select(EmailLog).where(EmailLog.id == email_log_id))
        return result.scalar_one_or_none()

    async def get_emails_for_user(
        self, user_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[EmailLog]:
        """
        Get email logs for a specific user.

        Args:
            user_id: User UUID
            limit: Maximum number of records
            offset: Pagination offset

        Returns:
            List of EmailLog records
        """
        result = await self.db.execute(
            select(EmailLog)
            .where(EmailLog.user_id == user_id)
            .order_by(EmailLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_emails_for_workspace(
        self, workspace_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[EmailLog]:
        """
        Get email logs for a specific workspace.

        Args:
            workspace_id: Workspace UUID
            limit: Maximum number of records
            offset: Pagination offset

        Returns:
            List of EmailLog records
        """
        result = await self.db.execute(
            select(EmailLog)
            .where(EmailLog.workspace_id == workspace_id)
            .order_by(EmailLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_recent_failures(self, hours: int = 24, limit: int = 100) -> List[EmailLog]:
        """
        Get recent failed email sends.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of records

        Returns:
            List of failed EmailLog records
        """
        from datetime import timedelta

        cutoff_time = utc_now() - timedelta(hours=hours)

        result = await self.db.execute(
            select(EmailLog)
            .where(EmailLog.status == "failed", EmailLog.created_at >= cutoff_time)
            .order_by(EmailLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def retry_failed_email(self, email_log_id: UUID, auto_commit: bool = True) -> EmailLog:
        """
        Retry sending a failed email.

        Args:
            email_log_id: Email log UUID to retry
            auto_commit: Whether to auto-commit transaction (default True, set False in tests)

        Returns:
            Updated EmailLog record

        Raises:
            ValueError: If email log not found or not in failed status
        """
        # Get original email log
        email_log = await self.get_email_log(email_log_id)

        if not email_log:
            raise ValueError(f"Email log {email_log_id} not found")

        if email_log.status != "failed":
            raise ValueError(f"Email log {email_log_id} is not in failed status")

        logger.info(
            "Retrying failed email",
            extra={"email_log_id": str(email_log_id), "original_provider": email_log.provider},
        )

        # Build message from stored log data
        if not email_log.html_content:
            raise ValueError(
                f"Email log {email_log_id} has no stored HTML content. "
                "Emails sent before the html_content column was added cannot be retried."
            )

        message = EmailMessage(
            to=[EmailRecipient(email=email_log.to_email)],
            subject=email_log.subject,
            html=email_log.html_content,
            from_email=email_log.from_email,
            tags=email_log.tags,
        )

        # Reset log status
        email_log.status = "queued"
        email_log.error_message = None
        email_log.failed_at = None
        email_log.updated_at = utc_now()

        # Try sending with current provider
        provider = get_email_provider()
        result = await self._send_with_provider(message, provider, email_log)

        # Update with result
        self._update_log_with_result(email_log, result)

        if auto_commit:
            await self.db.flush()  # Changed from commit() as per Task 074

        # Note: No refresh after commit (see send_email for explanation)

        return email_log
