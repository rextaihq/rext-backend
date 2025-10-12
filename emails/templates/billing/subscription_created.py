"""
Subscription Created Email Template

Sent when a user successfully subscribes to a paid plan.
"""
from typing import List
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_subscription_created_email(
    user_name: str,
    plan_name: str,
    plan_price: str,
    billing_period: str,
    features: List[str],
    dashboard_url: str = "https://app.wrext.com/settings/billing",
    frontend_url: str = "https://app.wrext.com"
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
        frontend_url: Base frontend URL for branding

    Returns:
        Complete HTML email string
    """
    # Build features list
    features_html = ""
    for feature in features[:5]:  # Show top 5 features
        features_html += f"""
        <tr>
            <td style="padding: 12px 16px; background-color: #f9fafb; border-radius: 6px; border-left: 4px solid #10b981;">
                <p style="color: #111827; font-size: 15px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                    ✓ {feature}
                </p>
            </td>
        </tr>
        <tr><td style="height: 8px;"></td></tr>
        """

    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Welcome to {plan_name}! 🎉
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thank you for subscribing to <strong>{plan_name}</strong>! Your subscription is now active and you have access to all premium features.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px;">
            <h2 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                📋 Subscription Details
            </h2>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #ffffff; font-size: 15px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Plan:</strong>
                    </td>
                    <td style="color: #ffffff; font-size: 15px; padding: 8px 0; text-align: right; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {plan_name}
                    </td>
                </tr>
                <tr>
                    <td style="color: #ffffff; font-size: 15px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Price:</strong>
                    </td>
                    <td style="color: #ffffff; font-size: 15px; padding: 8px 0; text-align: right; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {plan_price}/{billing_period}
                    </td>
                </tr>
            </table>
        </div>
        """,
        f"""
        <h2 style="color: #111827; font-size: 20px; font-weight: 600; margin: 32px 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            What's Included:
        </h2>
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
            {features_html}
        </table>
        """,
        primary_button("Go to Dashboard", dashboard_url),
        """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You can manage your subscription, update payment methods, and view invoices from your billing dashboard.
        </p>
        """,
        simple_footer()
    ])

    return email_html
