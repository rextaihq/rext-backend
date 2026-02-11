"""
SMTP Email Provider Implementation

Async SMTP email provider for fallback and compatibility.
Implements the IEmailProvider interface for provider abstraction.
Uses aiosmtplib to avoid blocking the FastAPI event loop.
"""
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from src.providers.email.base import IEmailProvider, EmailMessage, EmailResult, EmailRecipient
from src.config.email_config import email_config
from src.api.lib.logger import auto_logger

logger = auto_logger()


class SMTPEmailProvider(IEmailProvider):
    """
    Async SMTP email provider implementation.

    Uses aiosmtplib for non-blocking SMTP delivery.
    Serves as fallback provider when Resend is unavailable.

    Supports:
    - Multiple recipients (to, cc, bcc)
    - HTML email content
    - TLS/STARTTLS encryption
    """

    def __init__(self):
        """
        Initialize SMTP provider with configuration.

        Raises:
            ValueError: If SMTP configuration is incomplete
        """
        # Validate required configuration
        if not email_config.smtp_server:
            error_msg = "SMTP_SERVER not configured in environment"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not email_config.smtp_username or not email_config.smtp_password:
            error_msg = "SMTP_USERNAME and SMTP_PASSWORD required"
            logger.error(error_msg)
            raise ValueError(error_msg)

        self.server = email_config.smtp_server
        self.port = email_config.smtp_port
        self.username = email_config.smtp_username
        self.password = email_config.smtp_password
        self.use_tls = email_config.smtp_use_tls

        logger.info(
            "SMTP email provider initialized",
            extra={
                "provider": "smtp",
                "server": self.server,
                "port": self.port,
                "use_tls": self.use_tls
            }
        )

    async def send_email(self, message: EmailMessage) -> EmailResult:
        """
        Send email via async SMTP.

        Args:
            message: EmailMessage object with all email details

        Returns:
            EmailResult with success status and error information if any
        """
        try:
            # Build MIME message
            mime_message = self._build_mime_message(message)

            # Collect all recipients
            all_recipients = [r.email for r in message.to]
            if message.cc:
                all_recipients.extend([r.email for r in message.cc])
            if message.bcc:
                all_recipients.extend([r.email for r in message.bcc])

            logger.info(
                "Sending email via SMTP",
                extra={
                    "to": [r.email for r in message.to],
                    "subject": message.subject,
                    "server": self.server,
                    "port": self.port,
                    "total_recipients": len(all_recipients)
                }
            )

            # Send via async SMTP
            smtp = aiosmtplib.SMTP(
                hostname=self.server,
                port=self.port,
                timeout=30,
                start_tls=self.use_tls,
            )
            async with smtp:
                await smtp.login(self.username, self.password)
                await smtp.sendmail(
                    message.from_email,
                    all_recipients,
                    mime_message.as_string()
                )

            logger.info(
                "Email sent successfully via SMTP",
                extra={
                    "to": [r.email for r in message.to],
                    "recipients_count": len(all_recipients)
                }
            )

            return EmailResult(
                success=True,
                message_id=self._generate_message_id(message),
                provider_response={"status": "sent", "recipients": len(all_recipients)}
            )

        except aiosmtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP authentication failed: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    "to": [r.email for r in message.to],
                    "server": self.server,
                    "error_type": type(e).__name__
                }
            )
            return EmailResult(
                success=False,
                error=error_msg,
                provider_response={"error_type": "authentication", "error": str(e)}
            )

        except aiosmtplib.SMTPRecipientsRefused as e:
            error_msg = f"All recipients refused: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    "to": [r.email for r in message.to],
                    "error_type": type(e).__name__
                }
            )
            return EmailResult(
                success=False,
                error=error_msg,
                provider_response={"error_type": "recipients_refused", "error": str(e)}
            )

        except aiosmtplib.SMTPException as e:
            error_msg = f"SMTP error: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    "to": [r.email for r in message.to],
                    "server": self.server,
                    "error_type": type(e).__name__
                }
            )
            return EmailResult(
                success=False,
                error=error_msg,
                provider_response={"error_type": type(e).__name__, "error": str(e)}
            )

        except Exception as e:
            error_msg = f"Unexpected error sending email: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    "to": [r.email for r in message.to],
                    "server": self.server,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            return EmailResult(
                success=False,
                error=error_msg,
                provider_response={"error_type": type(e).__name__, "error": str(e)}
            )

    def _build_mime_message(self, message: EmailMessage) -> MIMEMultipart:
        """
        Build MIME message from EmailMessage.

        Args:
            message: EmailMessage object

        Returns:
            MIMEMultipart message ready to send
        """
        mime_msg = MIMEMultipart('alternative')

        # Set headers
        mime_msg['From'] = (
            f"{message.from_name} <{message.from_email}>"
            if message.from_name
            else message.from_email
        )
        mime_msg['To'] = ', '.join([r.email for r in message.to])
        mime_msg['Subject'] = message.subject

        # Optional headers
        if message.cc:
            mime_msg['Cc'] = ', '.join([r.email for r in message.cc])

        if message.reply_to:
            mime_msg['Reply-To'] = message.reply_to

        # Add tags as custom headers (X-Tags)
        if message.tags:
            tags_str = ', '.join([f"{k}={v}" for k, v in message.tags.items()])
            mime_msg['X-Tags'] = tags_str

        # Attach HTML content
        html_part = MIMEText(message.html, 'html', 'utf-8')
        mime_msg.attach(html_part)

        return mime_msg

    def _generate_message_id(self, message: EmailMessage) -> str:
        """
        Generate a message ID for tracking.

        Args:
            message: EmailMessage object

        Returns:
            Simple message ID based on recipient and timestamp
        """
        import hashlib
        from datetime import datetime

        # Create a simple message ID from recipient and timestamp
        to_email = message.to[0].email if message.to else "unknown"
        timestamp = datetime.now(timezone.utc).isoformat()
        content = f"{to_email}:{message.subject}:{timestamp}"

        msg_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        return f"smtp-{msg_hash}"

    def get_provider_name(self) -> str:
        """
        Get provider name identifier.

        Returns:
            String identifier 'smtp'
        """
        return "smtp"

    async def verify_connection(self) -> bool:
        """
        Verify SMTP connection and credentials asynchronously.

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            logger.info(
                "Verifying SMTP connection",
                extra={"server": self.server, "port": self.port}
            )

            smtp = aiosmtplib.SMTP(
                hostname=self.server,
                port=self.port,
                timeout=10,
                start_tls=self.use_tls,
            )
            async with smtp:
                await smtp.login(self.username, self.password)

            logger.info(
                "SMTP connection verified successfully",
                extra={"server": self.server}
            )
            return True

        except aiosmtplib.SMTPAuthenticationError as e:
            logger.error(
                f"SMTP authentication failed: {str(e)}",
                extra={"server": self.server, "error_type": "authentication"}
            )
            return False

        except Exception as e:
            logger.error(
                f"SMTP connection verification failed: {str(e)}",
                extra={
                    "server": self.server,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            return False

    def supports_feature(self, feature: str) -> bool:
        """
        Check if SMTP provider supports a specific feature.

        Args:
            feature: Feature name to check

        Returns:
            True if feature is supported, False otherwise
        """
        supported_features = {
            'basic_email',
            'html',
            'cc_bcc',
            'reply_to',
        }

        is_supported = feature in supported_features

        if not is_supported:
            logger.debug(
                f"Feature '{feature}' not supported by SMTP provider",
                extra={"feature": feature, "provider": "smtp"}
            )

        return is_supported
