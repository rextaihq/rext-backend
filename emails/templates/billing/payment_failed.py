"""
Payment Failed Email Template

Sent when a payment attempt fails.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_payment_failed_email(
    user_name: str,
    plan_name: str,
    amount: str,
    failed_on: str,
    update_payment_url: str = "https://app.rext.ai/settings/billing",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render payment failed email template.

    Sent when payment processing fails.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the plan
        amount: Payment amount that failed (e.g., "$29.99")
        failed_on: When the renewal first failed (e.g., "January 18, 2025"); Lemon Squeezy
            retries it for about two weeks from then and gives no next-retry time
        update_payment_url: URL to update payment method (internal billing dashboard)
        customer_portal_url: Optional direct URL to payment provider's customer portal for updating payment method
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    # Prefer customer portal URL (one-click update) over internal dashboard
    payment_update_url = customer_portal_url or update_payment_url
    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #dc2626; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Payment Failed ⚠️
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We were unable to process your payment for <strong>{plan_name}</strong>. This could be due to insufficient funds, an expired card, or your bank declining the charge.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fef2f2; border: 2px solid #fecaca; border-radius: 8px;">
            <h2 style="color: #dc2626; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                What Happens Next?
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your renewal payment failed on <strong>{failed_on}</strong>. We'll keep retrying it automatically for up to two weeks from then. Update your card to avoid an interruption; your plan keeps working meanwhile.
            </p>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Plan
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 6px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {plan_name}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Amount Due
                    </td>
                    <td style="color: #dc2626; font-size: 16px; padding: 6px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {amount}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Failed On
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 6px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {failed_on}
                    </td>
                </tr>
            </table>
        </div>
        """,
            primary_button("Update Payment Method", payment_update_url),
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>Common solutions:</strong><br>
            • Check that your card has sufficient funds<br>
            • Verify the card hasn't expired<br>
            • Contact your bank to authorize the charge<br>
            • Try a different payment method
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Need help? Our support team is ready to assist you.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
