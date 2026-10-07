"""
Payment Recovered Email Template

Sent when a previously failed payment is successfully recovered.
This restores full access to the subscription.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_payment_recovered_email(
    user_name: str,
    plan_name: str,
    amount: str,
    recovery_date: str,
    next_billing_date: str,
    manage_subscription_url: str = "https://app.rext.ai/subscription",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render payment recovered email template.

    Sent when payment is successfully recovered after failure.
    Tone: Positive, welcoming back, reassuring.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the plan
        amount: Payment amount recovered (e.g., "$29.99")
        recovery_date: Date when payment was recovered (e.g., "January 22, 2025")
        next_billing_date: Next billing date (e.g., "February 22, 2025")
        manage_subscription_url: URL to manage subscription
        customer_portal_url: Optional direct URL to payment provider's portal
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    # Prefer customer portal URL over internal dashboard
    manage_url = customer_portal_url or manage_subscription_url

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Payment Successful - Welcome Back! 🎉
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Great news! Your payment for <strong>{plan_name}</strong> has been successfully processed and your subscription is now fully active.
        </p>
        """,
            """
        <div style="margin: 32px 0; padding: 28px; background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 8px;">
            <h2 style="color: #166534; font-size: 24px; font-weight: 700; margin: 0 0 16px 0; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ✅ Full Access Restored
            </h2>
            <p style="color: #065f46; font-size: 16px; line-height: 24px; margin: 0; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                You can now access all your workspaces, content, and premium features without any restrictions.
            </p>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #fafafa; border-radius: 8px;">
            <h3 style="color: #171717; font-size: 18px; font-weight: 600; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Payment Details
            </h3>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #737373; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Subscription
                    </td>
                    <td style="color: #171717; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {plan_name}
                    </td>
                </tr>
                <tr>
                    <td style="color: #737373; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Amount Paid
                    </td>
                    <td style="color: #171717; font-size: 16px; padding: 8px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {amount}
                    </td>
                </tr>
                <tr>
                    <td style="color: #737373; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Payment Date
                    </td>
                    <td style="color: #171717; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {recovery_date}
                    </td>
                </tr>
                <tr>
                    <td style="color: #737373; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Status
                    </td>
                    <td style="color: #171717; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Active ✓
                    </td>
                </tr>
                <tr>
                    <td style="color: #737373; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Next Billing Date
                    </td>
                    <td style="color: #171717; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {next_billing_date}
                    </td>
                </tr>
            </table>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #fafafa; border-radius: 8px;">
            <h3 style="color: #171717; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                What's Restored
            </h3>
            <ul style="color: #404040; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>✅ Your plan and its monthly credits</li>
                <li>✅ Researching keywords and writing articles</li>
                <li>✅ Your workspaces and your team's access to them</li>
            </ul>
        </div>
        """,
            primary_button("Access Your Dashboard", frontend_url),
            f"""
        <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <a href="{manage_url}" style="color: #171717; text-decoration: underline; font-weight: 600;">Manage your subscription</a>
        </p>
        """,
            """
        <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thank you for continuing with us! If you have any questions or need assistance, our support team is always here to help.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
