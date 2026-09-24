"""
Data Export Ready Template

Sent when a user's data export is ready for download.
"""

from emails.components import simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_data_export_email(
    user_name: str,
) -> str:
    """
    Render data export ready email template.

    Args:
        user_name: User's first name or display name

    Returns:
        Complete HTML email string
    """
    email_html = compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Data Export is Ready, {user_name}
        </h1>
        """,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We have finished processing your request to export your account data. 
            The exported data is attached to this email in JSON format.
        </p>
        """,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            If you requested this by mistake, you can simply ignore this email. Keep this file safe as it contains your personal information.
        </p>
        """,
            """
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Thank you for using Rext AI.
            </p>
        </div>
        """,
            simple_footer(),
        ],
        preview_text="Your requested data export is ready and attached.",
    )

    return email_html


def create_data_export_ready_email(
    user_name: str,
) -> str:
    """
    Create data export ready email.

    Args:
        user_name: User's first name or display name

    Returns:
        Complete HTML email string
    """
    return render_data_export_email(user_name=user_name)
