"""
Welcome Email Template

Sent after a user successfully verifies their email address.
"""

from typing import Optional

from emails.components import primary_button, simple_footer, simple_header
from emails.site_links import SITE_HELP_URL
from emails.utils.renderer import compose_email


def render_welcome_email(
    user_name: str,
    dashboard_url: str = "https://app.rext.ai",
    help_url: str = SITE_HELP_URL,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render welcome email template.

    Sent after email verification to guide new users.

    Args:
        user_name: User's first name or display name
        dashboard_url: URL to user's dashboard
        help_url: URL to help center
        frontend_url: Base frontend URL for branding

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_welcome_email(
        ...     user_name="John",
        ...     dashboard_url="https://app.rext.ai"
        ... )
    """
    email_html = compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Welcome aboard, {user_name}! 🎉
        </h1>
        """,
            """
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your email has been verified and your account is now active! We're thrilled to have you as part of the Rext AI community.
        </p>
        """,
            """
        <div style="margin: 32px 0; padding: 24px; background-color: #fafafa; border: 1px solid #e5e5e5; border-radius: 8px;">
            <h2 style="color: #171717; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                🚀 Get Started with Rext AI
            </h2>
            <p style="color: #404040; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Rext AI helps you create, collaborate, and manage content efficiently. Here's what you can do:
            </p>
        </div>
        """,
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 24px 0;">
            <tr>
                <td style="padding: 16px; background-color: #fafafa; border-radius: 6px; border-left: 4px solid #111a17;">
                    <p style="color: #171717; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        ✅ Create Your First Workspace
                    </p>
                    <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Set up a workspace to organize your projects and collaborate with your team.
                    </p>
                </td>
            </tr>
        </table>
        """,
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 24px 0;">
            <tr>
                <td style="padding: 16px; background-color: #fafafa; border-radius: 6px; border-left: 4px solid #111a17;">
                    <p style="color: #171717; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        📝 Create Content
                    </p>
                    <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Use our AI-powered tools to generate high-quality content quickly and efficiently.
                    </p>
                </td>
            </tr>
        </table>
        """,
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 24px 0;">
            <tr>
                <td style="padding: 16px; background-color: #fafafa; border-radius: 6px; border-left: 4px solid #f59e0b;">
                    <p style="color: #171717; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        👥 Invite Your Team
                    </p>
                    <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Collaborate seamlessly by inviting team members to your workspace.
                    </p>
                </td>
            </tr>
        </table>
        """,
            """
        <div style="margin: 32px 0; text-align: center;">
        """,
            primary_button("Go to Dashboard", dashboard_url),
            """
        </div>
        """,
            """
        <div style="margin-top: 32px; padding: 20px; background-color: #f5f5f5; border-radius: 6px; text-align: center;">
            <p style="color: #404040; font-size: 15px; line-height: 22px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Need help getting started?</strong>
            </p>
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Check out our help center for guides, tutorials, and FAQs.
            </p>
        """,
            f"""
            <a href="{help_url}" style="display: inline-block; color: #171717; text-decoration: underline; font-size: 14px; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Visit Help Center →
            </a>
        </div>
        """,
            """
        <div style="margin-top: 32px; border-top: 1px solid #e5e5e5; padding-top: 24px;">
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                We're here to help you succeed. If you have any questions or feedback, feel free to reach out to our support team.
            </p>
        </div>
        """,
            simple_footer(),
        ],
        preview_text=f"Welcome to Rext AI, {user_name}! Your account is ready.",
    )

    return email_html


# Convenience function for use with EmailService
def create_welcome_email(
    user_name: str,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
) -> str:
    """
    Create welcome email after email verification.

    Args:
        user_name: User's first name or display name
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token for user preferences

    Returns:
        Complete HTML email string
    """
    # Send newly verified users to workspace creation — their first onboarding step
    dashboard_url = f"{frontend_url}/w/create"
    help_url = SITE_HELP_URL

    # Build unsubscribe footer
    unsubscribe_html = ""
    if unsubscribe_token:
        unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
        unsubscribe_html = f"""
        <div style="margin-top: 32px; padding: 20px; text-align: center; background-color: #fafafa; border-radius: 6px;">
            <p style="margin: 0; font-size: 12px; color: #737373; line-height: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Don't want to receive these emails?
                <a href="{unsubscribe_url}" style="color: #737373; text-decoration: underline;">Unsubscribe</a>
            </p>
        </div>
        """

    email_html = compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Welcome aboard, {user_name}! 🎉
        </h1>
        """,
            """
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your email has been verified and your account is now active! We're thrilled to have you as part of the Rext AI community.
        </p>
        """,
            """
        <div style="margin: 32px 0; padding: 24px; background-color: #fafafa; border: 1px solid #e5e5e5; border-radius: 8px;">
            <h2 style="color: #171717; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                🚀 Get Started with Rext AI
            </h2>
            <p style="color: #404040; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Rext AI helps you create, collaborate, and manage content efficiently. Here's what you can do:
            </p>
        </div>
        """,
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 24px 0;">
            <tr>
                <td style="padding: 16px; background-color: #fafafa; border-radius: 6px; border-left: 4px solid #111a17;">
                    <p style="color: #171717; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        ✅ Create Your First Workspace
                    </p>
                    <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Set up a workspace to organize your projects and collaborate with your team.
                    </p>
                </td>
            </tr>
        </table>
        """,
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 24px 0;">
            <tr>
                <td style="padding: 16px; background-color: #fafafa; border-radius: 6px; border-left: 4px solid #111a17;">
                    <p style="color: #171717; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        📝 Create Content
                    </p>
                    <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Use our AI-powered tools to generate high-quality content quickly and efficiently.
                    </p>
                </td>
            </tr>
        </table>
        """,
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 24px 0;">
            <tr>
                <td style="padding: 16px; background-color: #fafafa; border-radius: 6px; border-left: 4px solid #f59e0b;">
                    <p style="color: #171717; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        👥 Invite Your Team
                    </p>
                    <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Collaborate seamlessly by inviting team members to your workspace.
                    </p>
                </td>
            </tr>
        </table>
        """,
            """
        <div style="margin: 32px 0; text-align: center;">
        """,
            primary_button("Go to Dashboard", dashboard_url),
            """
        </div>
        """,
            f"""
        <div style="margin-top: 32px; padding: 20px; background-color: #f5f5f5; border-radius: 6px; text-align: center;">
            <p style="color: #404040; font-size: 15px; line-height: 22px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Need help getting started?</strong>
            </p>
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Check out our help center for guides, tutorials, and FAQs.
            </p>
            <a href="{help_url}" style="display: inline-block; color: #171717; text-decoration: underline; font-size: 14px; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Visit Help Center →
            </a>
        </div>
        """,
            """
        <div style="margin-top: 32px; border-top: 1px solid #e5e5e5; padding-top: 24px;">
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                We're here to help you succeed. If you have any questions or feedback, feel free to reach out to our support team.
            </p>
        </div>
        """,
            unsubscribe_html,
            simple_footer(),
        ],
        preview_text=f"Welcome to Rext AI, {user_name}! Your account is ready.",
    )

    return email_html
