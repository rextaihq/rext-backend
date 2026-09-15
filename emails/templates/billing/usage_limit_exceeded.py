"""
Usage Limit Exceeded Email Template

Sent when a user exceeds their plan's usage limits.
"""

from emails.components import primary_button, secondary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_usage_limit_exceeded_email(
    user_name: str,
    resource_type: str,
    current_usage: int,
    usage_limit: int,
    plan_name: str,
    restrictions: list[str],
    upgrade_url: str = "https://app.rext.ai/pricing",
    usage_url: str = "https://app.rext.ai/usage",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render usage limit exceeded email template.

    Sent when user exceeds their plan's usage limits.

    Args:
        user_name: User's first name or display name
        resource_type: Type of resource (e.g., "API calls", "workspaces", "team members")
        current_usage: Current usage amount
        usage_limit: Maximum allowed usage
        plan_name: Name of the current plan
        restrictions: List of features that are now restricted
        upgrade_url: URL to upgrade plan
        usage_url: URL to view detailed usage
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    restrictions_html = "".join(
        [f'<li style="margin-bottom: 8px;">🚫 {restriction}</li>' for restriction in restrictions]
    )

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            🚨 Usage Limit Exceeded
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You've exceeded your <strong>{resource_type}</strong> limit on your <strong>{plan_name}</strong> plan. Some features have been temporarily restricted.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fef2f2; border: 2px solid #fca5a5; border-radius: 8px;">
            <h2 style="color: #991b1b; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Current Usage
            </h2>
            <p style="color: #374151; font-size: 24px; font-weight: 700; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {current_usage:,} / {usage_limit:,} (Limit Exceeded)
            </p>
            <div style="width: 100%; height: 8px; background-color: #e5e7eb; border-radius: 4px; overflow: hidden; margin-top: 12px;">
                <div style="width: 100%; height: 100%; background-color: #ef4444;"></div>
            </div>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Currently Restricted:
            </h3>
            <ul style="color: #6b7280; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {restrictions_html}
            </ul>
        </div>
        """,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            To restore full access and increase your limits, upgrade to a higher plan now.
        </p>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #ecfdf5; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ✨ Upgrade Benefits:
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Immediate access restoration</li>
                <li>Higher usage limits</li>
                <li>Advanced features</li>
                <li>Priority support</li>
            </ul>
        </div>
        """,
            primary_button("Upgrade Now", upgrade_url),
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
            <tr>
                <td align="center">
        """,
            secondary_button("View Detailed Usage", usage_url),
            """
                </td>
            </tr>
        </table>
        """,
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Questions about your usage or plan options? Our support team is ready to help.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
