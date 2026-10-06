"""
Subscription Cancelled Email Template

Sent when a user cancels their subscription.
"""

from emails.components import primary_button, secondary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_subscription_cancelled_email(
    user_name: str,
    plan_name: str,
    end_date: str,
    workspace_url: str = "https://app.rext.ai",
    reactivate_url: str = "https://app.rext.ai/pricing",
    feedback_url: str = "https://app.rext.ai/feedback",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render subscription cancelled email template.

    Sent when user cancels their subscription.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the cancelled plan
        end_date: Date when access will end (e.g., "February 15, 2025")
        workspace_url: URL to return to the workspace/app
        reactivate_url: URL to reactivate subscription
        feedback_url: URL for user feedback
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Subscription Cancelled
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We're sorry to see you go. Your <strong>{plan_name}</strong> subscription has been cancelled.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fffbeb; border: 2px solid #fcd34d; border-radius: 8px;">
            <h2 style="color: #92400e; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                📅 What This Means
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                You keep your <strong>{plan_name}</strong> plan and its credits until <strong>{end_date}</strong>. After that, your workspaces, articles and keyword library stay in your account, but researching keywords and writing articles needs an active plan.
            </p>
        </div>
        """,
            primary_button("Go to Workspace", workspace_url),
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Changed your mind? You can reactivate your subscription anytime before <strong>{end_date}</strong>.
        </p>
        """,
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
            <tr>
                <td align="center">
        """,
            secondary_button("Reactivate Subscription", reactivate_url),
            """
                </td>
            </tr>
        </table>
        """,
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We'd love to know why you cancelled and how we can improve. Your feedback helps us build a better product for everyone.
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thank you for being part of Rext AI. We hope to see you again soon!
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
