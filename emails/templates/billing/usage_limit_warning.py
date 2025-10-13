"""
Usage Limit Warning Email Template

Sent when a user is approaching their plan's usage limits (e.g., 80% of quota used).
"""
from emails.components import simple_header, primary_button, secondary_button, simple_footer
from emails.utils.renderer import compose_email


def render_usage_limit_warning_email(
    user_name: str,
    resource_type: str,
    current_usage: int,
    usage_limit: int,
    percentage_used: int,
    plan_name: str,
    upgrade_url: str = "https://app.wrext.com/pricing",
    usage_url: str = "https://app.wrext.com/usage",
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Render usage limit warning email template.

    Sent when user approaches their plan's usage limits.

    Args:
        user_name: User's first name or display name
        resource_type: Type of resource (e.g., "API calls", "workspaces", "team members")
        current_usage: Current usage amount
        usage_limit: Maximum allowed usage
        percentage_used: Percentage of quota used (e.g., 80)
        plan_name: Name of the current plan
        upgrade_url: URL to upgrade plan
        usage_url: URL to view detailed usage
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            ⚠️ Usage Limit Warning
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You're approaching your <strong>{resource_type}</strong> limit on your <strong>{plan_name}</strong> plan.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fffbeb; border: 2px solid #fcd34d; border-radius: 8px;">
            <h2 style="color: #92400e; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Current Usage
            </h2>
            <p style="color: #374151; font-size: 24px; font-weight: 700; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {current_usage:,} / {usage_limit:,} ({percentage_used}%)
            </p>
            <div style="width: 100%; height: 8px; background-color: #e5e7eb; border-radius: 4px; overflow: hidden; margin-top: 12px;">
                <div style="width: {percentage_used}%; height: 100%; background-color: #f59e0b; transition: width 0.3s ease;"></div>
            </div>
        </div>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            When you reach your limit, some features may be temporarily restricted. To avoid interruptions, consider upgrading to a higher plan with increased limits.
        </p>
        """,
        """
        <div style="margin: 24px 0; padding: 20px; background-color: #ecfdf5; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                💡 Upgrade for More:
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Higher usage limits</li>
                <li>Advanced features</li>
                <li>Priority support</li>
                <li>No interruptions</li>
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
            Need help choosing the right plan? Our team is here to assist you.
        </p>
        """,
        simple_footer()
    ])

    return email_html
