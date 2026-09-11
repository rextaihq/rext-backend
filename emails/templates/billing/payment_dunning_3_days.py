"""
Payment Dunning Email Template - 3 Days After Failure

Sent 3 days after initial payment failure with increased urgency.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_payment_dunning_3_days_email(
    user_name: str,
    plan_name: str,
    amount: str,
    days_until_suspension: int,
    grace_period_end_date: str,
    update_payment_url: str = "https://app.rext.ai/settings/billing",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render payment dunning email (3 days after failure).

    This is the second reminder with moderate urgency.
    Tone: More urgent, emphasizing time remaining.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the plan
        amount: Payment amount that failed (e.g., "$29.99")
        days_until_suspension: Days remaining until suspension (typically 4)
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
        <h1 style="color: #ea580c; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Urgent: Update Payment Method ⚠️
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            This is an urgent reminder that your payment for <strong>{plan_name}</strong> is still outstanding. We've attempted to process your payment multiple times without success.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fff7ed; border-left: 4px solid #ea580c; border-radius: 8px;">
            <h2 style="color: #9a3412; font-size: 20px; font-weight: 700; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ⏰ Only {days_until_suspension} Days Left
            </h2>
            <p style="color: #7c2d12; font-size: 16px; line-height: 24px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your account will be suspended on <strong>{grace_period_end_date}</strong> if payment is not received.
            </p>
            <p style="color: #7c2d12; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Once suspended, you'll lose access to all workspaces, content, and team features.
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
                    <td style="color: #dc2626; font-size: 16px; padding: 6px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {amount}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Suspension Date
                    </td>
                    <td style="color: #dc2626; font-size: 14px; padding: 6px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {grace_period_end_date}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 6px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Days Remaining
                    </td>
                    <td style="color: #ea580c; font-size: 18px; padding: 6px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {days_until_suspension}
                    </td>
                </tr>
            </table>
        </div>
        """,
            primary_button("Update Payment Now", payment_update_url),
            """
        <div style="margin: 32px 0; padding: 20px; background-color: #fef2f2; border-radius: 8px;">
            <h3 style="color: #991b1b; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                What Happens If Payment Isn't Updated?
            </h3>
            <ul style="color: #7f1d1d; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Your subscription will be suspended</li>
                <li>All workspaces and content will become inaccessible</li>
                <li>Team members will lose access</li>
                <li>Ongoing content generation will stop</li>
            </ul>
        </div>
        """,
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>Need help?</strong> Contact our support team immediately. We're here to assist you.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
