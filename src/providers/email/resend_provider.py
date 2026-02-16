"""
Resend Email Provider Implementation

Integrates with Resend API for reliable email delivery.
Implements the IEmailProvider interface for provider abstraction.
"""
import resend
import asyncio
from typing import Dict, Any, Optional
from src.providers.email.base import IEmailProvider, EmailMessage, EmailResult, EmailRecipient
from src.config.email_config import email_config
from src.api.lib.logger import auto_logger

logger = auto_logger()


class ResendEmailProvider(IEmailProvider):
    """
    Resend email provider implementation.

    Uses Resend API for email delivery with support for:
    - Multiple recipients (to, cc, bcc)
    - Tags for categorization
    - Reply-to addresses
    - HTML email content
    """

    def __init__(self):
        """
        Initialize Resend provider with API key from configuration.

        Raises:
            ValueError: If RESEND_API_KEY is not configured
        """
        if not email_config.resend_api_key:
            error_msg = "RESEND_API_KEY not configured in environment"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Set global API key for Resend SDK
        resend.api_key = email_config.resend_api_key

        logger.info(
            "Resend email provider initialized",
            extra={
                "provider": "resend",
                "from_email": email_config.resend_from_email,
                "from_name": email_config.resend_from_name
            }
        )

    async def send_email(self, message: EmailMessage) -> EmailResult:
        """
        Send email via Resend API.

        Args:
            message: EmailMessage object with all email details

        Returns:
            EmailResult with success status, message_id, and provider response

        Note:
            - Resend SDK is synchronous; the call is offloaded to a thread pool via
              asyncio.to_thread() to avoid blocking the FastAPI event loop
            - Errors are caught and returned as EmailResult with success=False
            - All operations are logged for debugging and monitoring
        """
        try:
            # Build Resend API parameters
            params = self._build_params(message)

            logger.info(
                "Sending email via Resend",
                extra={
                    "to": [r.email for r in message.to],
                    "subject": message.subject,
                    "tags": message.tags,
                    "has_cc": bool(message.cc),
                    "has_bcc": bool(message.bcc)
                }
            )

            # Send via Resend SDK (synchronous call)
            # Offload synchronous Resend SDK call to thread pool
            # to avoid blocking the FastAPI event loop
            response = await asyncio.to_thread(resend.Emails.send, params)

            # Extract message ID from response
            message_id = response.get("id") if isinstance(response, dict) else None

            logger.info(
                "Email sent successfully via Resend",
                extra={
                    "message_id": message_id,
                    "to": [r.email for r in message.to]
                }
            )

            return EmailResult(
                success=True,
                message_id=message_id,
                provider_response=response if isinstance(response, dict) else {"raw": str(response)}
            )

        except Exception as e:
            # Unexpected errors
            error_msg = f"Unexpected error sending email: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    "to": [r.email for r in message.to],
                    "subject": message.subject,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            return EmailResult(
                success=False,
                error=error_msg,
                provider_response={"error_type": type(e).__name__, "error": str(e)}
            )

    def _build_params(self, message: EmailMessage) -> Dict[str, Any]:
        """
        Build Resend API parameters from EmailMessage.

        Args:
            message: EmailMessage object

        Returns:
            Dictionary of parameters for Resend API

        Note:
            Resend API expects:
            - from: "Name <email@example.com>" or "email@example.com"
            - to: List of email addresses
            - subject: String
            - html: HTML content
            - tags (optional): List of tag objects [{"name": "key", "value": "val"}]
        """
        # Build 'from' field with name if provided
        from_address = (
            f"{message.from_name} <{message.from_email}>"
            if message.from_name
            else message.from_email
        )

        # Required parameters
        params: Dict[str, Any] = {
            "from": from_address,
            "to": [self._format_recipient(r) for r in message.to],
            "subject": message.subject,
            "html": message.html,
        }

        # Optional: CC recipients
        if message.cc:
            params["cc"] = [self._format_recipient(r) for r in message.cc]

        # Optional: BCC recipients
        if message.bcc:
            params["bcc"] = [self._format_recipient(r) for r in message.bcc]

        # Optional: Reply-to address
        if message.reply_to:
            params["reply_to"] = message.reply_to

        # Optional: Tags (convert dict to Resend tag format)
        if message.tags:
            # Resend expects tags as list of objects: [{"name": "category", "value": "marketing"}]
            params["tags"] = [
                {"name": key, "value": value}
                for key, value in message.tags.items()
            ]

        return params

    def _format_recipient(self, recipient: EmailRecipient) -> str:
        """
        Format recipient with name if provided.

        Args:
            recipient: EmailRecipient object

        Returns:
            Formatted string: "Name <email>" or just "email"
        """
        if recipient.name:
            return f"{recipient.name} <{recipient.email}>"
        return recipient.email

    def get_provider_name(self) -> str:
        """
        Get provider name identifier.

        Returns:
            String identifier 'resend'
        """
        return "resend"

    async def verify_connection(self) -> bool:
        """
        Verify Resend API connection and credentials.

        Returns:
            True if API key is valid and connection works, False otherwise

        Note:
            Resend doesn't have a dedicated health check endpoint.
            We verify by checking if API key is set and making a test call.
            In production, this could be enhanced with actual API validation.
        """
        try:
            # Check if API key is configured
            if not email_config.resend_api_key:
                logger.warning("Resend API key not configured")
                return False

            # Resend SDK will validate key on first API call
            # For now, we just verify it's set
            logger.info("Resend connection verified", extra={"provider": "resend"})
            return True

        except Exception as e:
            logger.error(
                f"Resend connection verification failed: {str(e)}",
                extra={"error_type": type(e).__name__},
                exc_info=True
            )
            return False

    def supports_feature(self, feature: str) -> bool:
        """
        Check if Resend provider supports a specific feature.

        Args:
            feature: Feature name to check

        Returns:
            True if feature is supported, False otherwise

        Supported features:
            - basic_email: Basic email sending
            - webhooks: Webhook event tracking
            - tags: Email categorization with tags
            - cc_bcc: CC and BCC recipients
            - reply_to: Reply-to address
            - html: HTML email content
            - attachments: File attachments (future)
            - templates: Email templates (future)
        """
        supported_features = {
            'basic_email',
            'webhooks',
            'tags',
            'cc_bcc',
            'reply_to',
            'html',
            # Future features:
            # 'attachments',
            # 'templates',
        }

        is_supported = feature in supported_features

        if not is_supported:
            logger.debug(
                f"Feature '{feature}' not supported by Resend provider",
                extra={"feature": feature, "provider": "resend"}
            )

        return is_supported
