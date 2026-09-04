"""
Mock Email Provider Implementation

Testing and development email provider that doesn't send real emails.
Implements the IEmailProvider interface for provider abstraction.
"""
from typing import List, Dict, Any
from datetime import datetime, timezone
from src.providers.email.base import IEmailProvider, EmailMessage, EmailResult
from src.api.lib.logger import auto_logger

logger = auto_logger()


class MockEmailProvider(IEmailProvider):
    """
    Mock email provider for testing and development.

    This provider simulates email sending without actually sending emails.
    Useful for:
    - Unit testing
    - Integration testing
    - Development environments
    - CI/CD pipelines

    Features:
    - Stores sent emails in memory for verification
    - Simulates success/failure scenarios
    - Logs all operations
    - No external dependencies
    """

    def __init__(self, simulate_failures: bool = False, failure_rate: float = 0.0):
        """
        Initialize Mock provider.

        Args:
            simulate_failures: If True, can simulate random failures
            failure_rate: Probability of failure (0.0 to 1.0), only used if simulate_failures=True
        """
        self.sent_emails: List[Dict[str, Any]] = []
        self.simulate_failures = simulate_failures
        self.failure_rate = max(0.0, min(1.0, failure_rate))  # Clamp between 0 and 1
        self._email_counter = 0

        logger.info(
            "Mock email provider initialized",
            extra={
                "provider": "mock",
                "simulate_failures": simulate_failures,
                "failure_rate": failure_rate
            }
        )

    async def send_email(self, message: EmailMessage) -> EmailResult:
        """
        Mock send email - stores email in memory instead of sending.

        Args:
            message: EmailMessage object with all email details

        Returns:
            EmailResult with success status and mock message ID

        Note:
            - Always succeeds unless simulate_failures is enabled
            - Stores email for later verification in tests
            - Generates sequential message IDs
        """
        try:
            # Simulate failure if configured
            if self.simulate_failures and self._should_fail():
                error_msg = "Simulated failure for testing"
                logger.warning(
                    f"Mock provider simulating failure",
                    extra={
                        "to": [r.email for r in message.to],
                        "subject": message.subject,
                        "failure_rate": self.failure_rate
                    }
                )
                return EmailResult(
                    success=False,
                    error=error_msg,
                    provider_response={"simulated": True, "reason": "testing"}
                )

            # Generate mock message ID
            self._email_counter += 1
            message_id = f"mock-{self._email_counter}-{datetime.now(timezone.utc).timestamp()}"

            # Store email in memory for verification
            email_record = {
                "message_id": message_id,
                "to": [r.email for r in message.to],
                "subject": message.subject,
                "html": message.html,
                "from_email": message.from_email,
                "from_name": message.from_name,
                "cc": [r.email for r in message.cc] if message.cc else None,
                "bcc": [r.email for r in message.bcc] if message.bcc else None,
                "reply_to": message.reply_to,
                "tags": message.tags,
                "attachments": message.attachments,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
            self.sent_emails.append(email_record)

            logger.info(
                "Mock email 'sent' (stored in memory)",
                extra={
                    "message_id": message_id,
                    "to": [r.email for r in message.to],
                    "subject": message.subject,
                    "total_sent": len(self.sent_emails)
                }
            )

            return EmailResult(
                success=True,
                message_id=message_id,
                provider_response={
                    "mock": True,
                    "stored": True,
                    "index": len(self.sent_emails) - 1
                }
            )

        except Exception as e:
            # Even mock provider can have unexpected errors
            error_msg = f"Mock provider error: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    "to": [r.email for r in message.to],
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            return EmailResult(
                success=False,
                error=error_msg,
                provider_response={"error_type": type(e).__name__, "error": str(e)}
            )

    def _should_fail(self) -> bool:
        """
        Determine if this send should fail (for testing).

        Returns:
            True if should simulate failure, False otherwise
        """
        if not self.simulate_failures or self.failure_rate == 0.0:
            return False

        import random
        return random.random() < self.failure_rate

    def get_provider_name(self) -> str:
        """
        Get provider name identifier.

        Returns:
            String identifier 'mock'
        """
        return "mock"

    async def verify_connection(self) -> bool:
        """
        Verify mock provider connection (always succeeds).

        Returns:
            Always True since mock provider doesn't need external connections
        """
        logger.info("Mock provider connection verified (always succeeds)")
        return True

    def supports_feature(self, feature: str) -> bool:
        """
        Check if Mock provider supports a specific feature.

        Args:
            feature: Feature name to check

        Returns:
            True if feature is supported, False otherwise

        Note:
            Mock provider supports all features since it just stores data
        """
        # Mock provider supports everything since it doesn't actually send
        supported_features = {
            'basic_email',
            'webhooks',
            'tags',
            'cc_bcc',
            'reply_to',
            'html',
            'attachments',
            'templates',
        }

        return feature in supported_features

    # Testing utility methods
    def get_sent_emails(self) -> List[Dict[str, Any]]:
        """
        Get all sent emails (for testing verification).

        Returns:
            List of email records stored in memory
        """
        return self.sent_emails.copy()

    def get_last_email(self) -> Dict[str, Any] | None:
        """
        Get the most recently sent email (for testing verification).

        Returns:
            Last email record or None if no emails sent
        """
        return self.sent_emails[-1] if self.sent_emails else None

    def get_emails_to(self, email: str) -> List[Dict[str, Any]]:
        """
        Get all emails sent to a specific address (for testing verification).

        Args:
            email: Email address to filter by

        Returns:
            List of email records sent to the specified address
        """
        return [
            record for record in self.sent_emails
            if email in record["to"]
        ]

    def get_emails_with_subject(self, subject: str) -> List[Dict[str, Any]]:
        """
        Get all emails with a specific subject (for testing verification).

        Args:
            subject: Subject to filter by (case-sensitive)

        Returns:
            List of email records with matching subject
        """
        return [
            record for record in self.sent_emails
            if record["subject"] == subject
        ]

    def clear_sent_emails(self) -> None:
        """
        Clear all sent email records (for test cleanup).
        """
        count = len(self.sent_emails)
        self.sent_emails.clear()
        self._email_counter = 0
        logger.info(f"Cleared {count} mock email records")

    def get_sent_count(self) -> int:
        """
        Get count of sent emails.

        Returns:
            Number of emails sent through this provider
        """
        return len(self.sent_emails)
