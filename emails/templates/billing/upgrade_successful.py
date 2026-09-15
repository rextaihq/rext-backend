"""
Upgrade Successful Email Template

Sent when a user successfully upgrades their subscription plan.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_upgrade_successful_email(
    user_name: str,
    old_plan_name: str,
    new_plan_name: str,
    new_features: list[str],
    effective_date: str,
    manage_url: str = "https://app.rext.ai/settings/subscription",
    docs_url: str = "https://docs.rext.ai",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render upgrade successful email template.

    Sent when user upgrades to a higher-tier plan.

    Args:
        user_name: User's first name or display name
        old_plan_name: Name of the previous plan
        new_plan_name: Name of the new plan
        new_features: List of new features now available
        effective_date: Date when upgrade took effect
        manage_url: URL to manage subscription
        docs_url: URL to documentation
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    features_html = "".join(
        [f'<li style="margin-bottom: 8px;">✅ {feature}</li>' for feature in new_features]
    )

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            🎉 Upgrade Successful!
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Congratulations! You've successfully upgraded from <strong>{old_plan_name}</strong> to <strong>{new_plan_name}</strong>.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #ecfdf5; border: 2px solid #6ee7b7; border-radius: 8px;">
            <h2 style="color: #065f46; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your Upgrade is Active
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                All new features are now available in your account as of <strong>{effective_date}</strong>.
            </p>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                What's New:
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {features_html}
            </ul>
        </div>
        """,
            """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We're excited to help you get the most out of your upgraded plan. Check out our documentation to learn about all the new features.
        </p>
        """,
            primary_button("Explore New Features", docs_url),
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
            <tr>
                <td align="center">
                    <a href="{}" style="display: inline-block; padding: 12px 32px; color: #4b5563; font-size: 14px; font-weight: 500; text-decoration: none; border-radius: 6px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Manage Subscription
                    </a>
                </td>
            </tr>
        </table>
        """.replace("{}", manage_url),
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thank you for choosing Rext AI. We're here to help you succeed!
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
