"""
Payment Dunning Email Template - 6 Days After Failure (Final Warning)

Sent 6 days after initial payment failure - final warning before suspension.
This is sent 1 day before the grace period expires.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_payment_dunning_6_days_email(
    user_name: str,
    plan_name: str,
    amount: str,
    grace_period_end_date: str,
    update_payment_url: str = "https://app.rext.ai/settings/billing",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render payment dunning email (6 days after failure - FINAL WARNING).

    This is the final reminder before suspension.
    Tone: Very urgent, emphasizing immediate action needed.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the plan
        amount: Payment amount that failed (e.g., "$29.99")
        grace_period_end_date: Date when access will be suspended (tomorrow, e.g., "January 25, 2025")
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
        <h1 style="color: #dc2626; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            FINAL NOTICE: Account Suspension Tomorrow 🚨
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong style="color: #dc2626;">This is your final notice.</strong> Your <strong>{plan_name}</strong> subscription will be suspended tomorrow if we don't receive payment.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 28px; background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); border-radius: 8px; box-shadow: 0 4px 6px rgba(220, 38, 38, 0.2);">
            <h2 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0 0 16px 0; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                🚨 Account Suspends on {grace_period_end_date}
            </h2>
            <p style="color: #fecaca; font-size: 18px; line-height: 28px; margin: 0 0 8px 0; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong style="color: #ffffff; font-size: 32px; display: block; margin-bottom: 8px;">LESS THAN 24 HOURS</strong>
                to update your payment and keep your account active
            </p>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border: 2px solid #fecaca; border-radius: 8px;">
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
                    <td style="color: #dc2626; font-size: 18px; padding: 6px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {amount}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        <strong>Suspension Date</strong>
                    </td>
                    <td style="color: #dc2626; font-size: 16px; padding: 6px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {grace_period_end_date} ⚠️
                    </td>
                </tr>
            </table>
        </div>
        """,
            primary_button("Update Payment Immediately", payment_update_url),
            """
        <div style="margin: 32px 0; padding: 24px; background-color: #fef2f2; border-left: 4px solid #dc2626; border-radius: 8px;">
            <h3 style="color: #991b1b; font-size: 18px; font-weight: 700; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ⚠️ What You'll Lose Tomorrow:
            </h3>
            <ul style="color: #7f1d1d; font-size: 15px; line-height: 24px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li><strong>All workspace access</strong> - Your team will be locked out</li>
                <li><strong>All content and data</strong> - No longer accessible</li>
                <li><strong>AI features and generation</strong> - Stopped immediately</li>
                <li><strong>Team collaboration</strong> - All members lose access</li>
                <li><strong>API access</strong> - Disabled</li>
            </ul>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #fef3c7; border-radius: 8px;">
            <h3 style="color: #92400e; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                💡 Quick Fix Options:
            </h3>
            <p style="color: #78350f; font-size: 14px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                • Update credit card details<br>
                • Switch to a different payment method<br>
                • Contact your bank to authorize the charge<br>
                • Add funds to your account
            </p>
        </div>
        """,
            """
        <p style="color: #dc2626; font-size: 16px; line-height: 24px; margin: 32px 0 0 0; font-weight: 600; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            ⏰ This is your last chance to prevent suspension.<br>
            Act now to keep your account active.
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Need immediate help? Contact our support team - we're standing by.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
