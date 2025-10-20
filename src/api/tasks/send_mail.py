import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import warnings
from src.api.lib.logger import auto_logger
from src.api.config import get_settings

logger = auto_logger()

# Get settings instance
settings = get_settings()

SMTP_SERVER = settings.SMTP_SERVER
SMTP_PORT = settings.SMTP_PORT
EMAIL_ADDRESS = settings.EMAIL_ADDRESS
EMAIL_PASSWORD = settings.EMAIL_PASSWORD


def send_email(to: str, subject: str, body: str):
    """
    Send an email using SMTP

    DEPRECATED: This function is deprecated and maintained for backwards compatibility only.

    Please use src.services.email_service.EmailService instead, which provides:
    - Better deliverability via Resend
    - Database logging for audit trails
    - Automatic retry logic with fallback
    - Email event tracking via webhooks
    - Support for workspace and user context

    Example migration:
        # Old way:
        from src.api.tasks.send_mail import send_email
        background_tasks.add_task(send_email, to="user@example.com", subject="Test", body="<p>Test</p>")

        # New way:
        from src.services.email_service import EmailService
        async def send_email_task(email, subject, html, user_id):
            from src.api.database.async_database import get_async_db_context
            async with get_async_db_context() as db:
                email_service = EmailService(db)
                await email_service.send_email(to=email, subject=subject, html=html, user_id=user_id)
        background_tasks.add_task(send_email_task, "user@example.com", "Test", "<p>Test</p>", user_id)

    This function will be removed in a future version.
    """
    # Emit deprecation warning
    warnings.warn(
        "send_mail.send_email() is deprecated. Use src.services.email_service.EmailService instead. "
        "See function docstring for migration guide.",
        DeprecationWarning,
        stacklevel=2
    )
    logger.warning(
        "DEPRECATED: Using old send_mail.send_email(). "
        "Please migrate to src.services.email_service.EmailService for better features and tracking."
    )
    logger.info("Preparing to send email...")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to
    msg['Subject'] = subject

    # Body
    msg.attach(MIMEText(body, 'html'))

    # Send email
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to, msg.as_string())
        logger.info(f"Email sent to {to}")
    except Exception as e:
        logger.info(f"Error sending email: {e}")


# if __name__ == "__main__":
#     # Example usage
#     send_email(
#         to="sami606713@gmail.com",
#         subject="Test Email",
#         body="<h1>This is a test email</h1><p>Sent using Python</p>"
#     )