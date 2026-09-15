"""
Payment Dunning Email Template - 1 Day After Failure

Sent 1 day after initial payment failure to remind user to update payment method.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_payment_dunning_1_day_email(
    user_name: str,
    plan_name: str,
    amount: str,
    grace_period_end_date: str,
    update_payment_url: str = "https://app.rext.ai/settings/billing",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render payment dunning email (1 day after failure).

    This is the first reminder after payment failure.
    Tone: Helpful and informative.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the plan
        amount: Payment amount that failed (e.g., "$29.99")
        grace_period_end_date: Date when access will be suspended (e.g., "January 25, 2025")
        update_payment_url: URL to update payment method (internal)
        customer_portal_url: Optional direct URL to payment provider's portal
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
        <h1 style="color: #f59e0b; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Payment Issue - Action Needed 💳
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We wanted to follow up regarding the payment issue for your <strong>{plan_name}</strong> subscription. Your payment of <strong>{amount}</strong> couldn't be processed.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 8px;">
            <h2 style="color: #92400e; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ⏰ You Have Until {grace_period_end_date}
            </h2>
            <p style="color: #78350f; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your account remains active with full access. Please update your payment method before <strong>{grace_period_end_date}</strong> to avoid service interruption.
            </p>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Subscription
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 6px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {plan_name}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Amount Due
                    </td>
                    <td style="color: #111827; font-size: 16px; padding: 6px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {amount}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Access Until
                    </td>
                    <td style="color: #f59e0b; font-size: 14px; padding: 6px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {grace_period_end_date}
                    </td>
                </tr>
            </table>
        </div>
        """,
            primary_button("Update Payment Method", payment_update_url),
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>Common reasons for payment failures:</strong><br>
            • Insufficient funds<br>
            • Expired credit card<br>
            • Bank security check<br>
            • Incorrect billing information
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            If you need assistance, we're here to help. Just reply to this email.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
