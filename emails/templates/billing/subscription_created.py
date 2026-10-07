"""
Subscription Created Email Template

Sent when a user successfully subscribes to a paid plan.
"""

from typing import List

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_subscription_created_email(
    user_name: str,
    plan_name: str,
    plan_price: str,
    billing_period: str,
    features: List[str],
    dashboard_url: str = "https://app.rext.ai/settings/subscription",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render subscription created email template.

    Sent when user successfully subscribes to a plan.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the subscribed plan (e.g., "Pro Plan")
        plan_price: Formatted price (e.g., "$29.99")
        billing_period: "monthly" or "yearly"
        features: List of key features included in the plan
        dashboard_url: URL to billing dashboard
        customer_portal_url: Optional LemonSqueezy customer portal URL for easy subscription management
        frontend_url: Base frontend URL for branding

    Returns:
        Complete HTML email string
    """
    # Build features list
    features_html = ""
    for feature in features[:5]:  # Show top 5 features
        features_html += f"""
        <tr>
            <td style="padding: 12px 16px; background-color: #fafafa; border-radius: 6px; border-left: 4px solid #111a17;">
                <p style="color: #171717; font-size: 15px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                    ✓ {feature}
                </p>
            </td>
        </tr>
        <tr><td style="height: 8px;"></td></tr>
        """

    email_content = [
        simple_header(),
        f"""
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Welcome to {plan_name}! 🎉
        </h1>
        """,
        f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thank you for subscribing to <strong>{plan_name}</strong>! Your subscription is now active and you have access to all premium features.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fafafa; border: 1px solid #e5e5e5; border-radius: 8px;">
            <h2 style="color: #171717; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                📋 Subscription Details
            </h2>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #404040; font-size: 15px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Plan:</strong>
                    </td>
                    <td style="color: #404040; font-size: 15px; padding: 8px 0; text-align: right; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {plan_name}
                    </td>
                </tr>
                <tr>
                    <td style="color: #404040; font-size: 15px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Price:</strong>
                    </td>
                    <td style="color: #404040; font-size: 15px; padding: 8px 0; text-align: right; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {plan_price}/{billing_period}
                    </td>
                </tr>
            </table>
        </div>
        """,
        f"""
        <h2 style="color: #171717; font-size: 20px; font-weight: 600; margin: 32px 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            What's Included:
        </h2>
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
            {features_html}
        </table>
        """,
        primary_button("Go to Dashboard", dashboard_url),
    ]

    # Add customer portal button if URL is provided
    if customer_portal_url:
        email_content.append(f"""
        <div style="margin: 24px 0;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td align="center">
                        <a href="{customer_portal_url}" style="display: inline-block; padding: 14px 32px; background-color: #ffffff; color: #171717; text-decoration: none; border-radius: 6px; border: 1px solid #d4d4d4; font-weight: 600; font-size: 15px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            Manage Subscription →
                        </a>
                    </td>
                </tr>
            </table>
        </div>
        """)

    # Add footer note with portal mention if available
    portal_text = " or customer portal" if customer_portal_url else ""
    email_content.append(f"""
        <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You can manage your subscription, update payment methods, and view invoices from your billing dashboard{portal_text}.
        </p>
        """)

    # Add footer
    email_content.append(simple_footer())

    # Compose final email
    email_html = compose_email(email_content)

    return email_html
