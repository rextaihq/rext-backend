"""
Subscription Suspended Email Template

Sent when a subscription is automatically suspended after grace period expires.
This is sent when payment couldn't be collected after multiple reminders.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_subscription_suspended_email(
    user_name: str,
    plan_name: str,
    amount: str,
    suspension_date: str,
    update_payment_url: str = "https://app.rext.ai/settings/subscription",
    customer_portal_url: str = None,
    reactivate_url: str = "https://app.rext.ai/settings/subscription",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render subscription suspended email template.

    Sent after grace period expires without payment resolution.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the suspended plan
        amount: Outstanding payment amount (e.g., "$29.99")
        suspension_date: Date of suspension (e.g., "January 25, 2025")
        update_payment_url: URL to update payment method (internal)
        customer_portal_url: Optional direct URL to payment provider's portal
        reactivate_url: URL to reactivate subscription
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    # Prefer customer portal URL over internal dashboard
    payment_update_url = customer_portal_url or update_payment_url

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #dc2626; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Subscription Has Been Suspended
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We're writing to inform you that your <strong>{plan_name}</strong> subscription has been suspended as of <strong>{suspension_date}</strong> due to an unresolved payment issue.
        </p>
        """,
            """
        <div style="margin: 32px 0; padding: 28px; background-color: #fef2f2; border: 2px solid #fecaca; border-radius: 8px;">
            <h2 style="color: #991b1b; font-size: 20px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                What This Means
            </h2>
            <ul style="color: #7f1d1d; font-size: 15px; line-height: 24px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li><strong>Access Suspended:</strong> You can no longer access your workspaces and content</li>
                <li><strong>Data Preserved:</strong> All your data is safely stored and will be restored upon reactivation</li>
                <li><strong>Team Access:</strong> Team members can no longer collaborate on your workspaces</li>
                <li><strong>Reactivation:</strong> Update your payment method to restore full access immediately</li>
            </ul>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Subscription
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {plan_name}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Outstanding Amount
                    </td>
                    <td style="color: #dc2626; font-size: 16px; padding: 8px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {amount}
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Status
                    </td>
                    <td style="color: #dc2626; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Suspended
                    </td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Suspension Date
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {suspension_date}
                    </td>
                </tr>
            </table>
        </div>
        """,
            """
        <div style="margin: 32px 0; padding: 24px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border-radius: 8px;">
            <h2 style="color: #ffffff; font-size: 20px; font-weight: 700; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ✨ Reactivate in Minutes
            </h2>
            <p style="color: #d1fae5; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Update your payment method now and regain instant access to all your workspaces, content, and team collaboration features.
            </p>
        </div>
        """,
            primary_button("Reactivate Subscription", payment_update_url),
            """
        <div style="margin: 32px 0; padding: 20px; background-color: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 8px;">
            <h3 style="color: #92400e; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your Data is Safe
            </h3>
            <p style="color: #78350f; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                All your workspaces, content, research, and team data remain securely stored. Nothing has been deleted. Simply reactivate your subscription to restore full access.
            </p>
        </div>
        """,
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>Need help?</strong> Our support team is here to assist with payment issues or account questions. Reply to this email or visit our help center.
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>Want to cancel instead?</strong> If you'd prefer to cancel your subscription permanently, please let us know and we'll process your request.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
