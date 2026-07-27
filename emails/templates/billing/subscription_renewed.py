"""
Subscription Renewed Email Template

Sent when subscription successfully renews.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_subscription_renewed_email(
    user_name: str,
    plan_name: str,
    amount: str,
    renewal_date: str,
    next_billing_date: str,
    dashboard_url: str = "https://app.rext.ai/settings/billing",
    frontend_url: str = "https://app.rext.ai"
) -> str:
    """
    Render subscription renewed email template.

    Sent when subscription successfully renews for another period.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the plan
        amount: Renewal amount (e.g., "$29.99")
        renewal_date: Date of renewal (e.g., "January 15, 2025")
        next_billing_date: Next billing date (e.g., "February 15, 2025")
        dashboard_url: URL to billing dashboard
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Subscription Renewed 🎉
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Great news! Your <strong>{plan_name}</strong> subscription has been successfully renewed. Thank you for continuing with REXT!
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border-radius: 8px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #ffffff; font-size: 15px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Renewal Date:</strong>
                    </td>
                    <td style="color: #ffffff; font-size: 15px; padding: 8px 0; text-align: right; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {renewal_date}
                    </td>
                </tr>
                <tr>
                    <td style="color: #ffffff; font-size: 15px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Amount Charged:</strong>
                    </td>
                    <td style="color: #ffffff; font-size: 18px; padding: 8px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {amount}
                    </td>
                </tr>
                <tr>
                    <td style="color: #ffffff; font-size: 15px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Next Billing Date:</strong>
                    </td>
                    <td style="color: #ffffff; font-size: 15px; padding: 8px 0; text-align: right; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {next_billing_date}
                    </td>
                </tr>
            </table>
        </div>
        """,
        f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f0fdf4; border-left: 4px solid #10b981; border-radius: 8px;">
            <p style="color: #065f46; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>✓ Your {plan_name} features are active</strong><br>
                Continue creating amazing content with full access to all premium features.
            </p>
        </div>
        """,
        primary_button("View Billing Details", dashboard_url),
        """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You can view your invoice, update payment methods, or manage your subscription from your billing dashboard.
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thank you for being a valued REXT customer!
        </p>
        """,
        simple_footer()
    ])

    return email_html
