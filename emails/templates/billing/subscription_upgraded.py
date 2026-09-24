"""
Subscription Upgraded Email Template

Sent when a user upgrades to a higher-tier plan.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_subscription_upgraded_email(
    user_name: str,
    old_plan_name: str,
    new_plan_name: str,
    old_price: str,
    new_price: str,
    billing_date: str,
    proration_amount: str = None,
    dashboard_url: str = "https://app.rext.ai/settings/subscription",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render subscription upgraded email template.

    Sent when user upgrades to a higher-tier subscription plan.

    Args:
        user_name: User's first name or display name
        old_plan_name: Previous plan name (e.g., "Starter Plan")
        new_plan_name: New plan name (e.g., "Pro Plan")
        old_price: Previous price (e.g., "$29.99/month")
        new_price: New price (e.g., "$99.99/month")
        billing_date: Next billing date (e.g., "January 20, 2025")
        proration_amount: Amount charged for proration (e.g., "$15.50") - optional
        dashboard_url: URL to billing dashboard (internal)
        customer_portal_url: Optional direct URL to payment provider's customer portal
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    # Prefer customer portal URL over internal dashboard
    manage_url = customer_portal_url or dashboard_url

    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #059669; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Subscription Upgraded! 🎉
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Congratulations! Your subscription has been successfully upgraded to <strong>{new_plan_name}</strong>. You now have access to more features and higher limits to help you achieve even more.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #ecfdf5; border: 2px solid #6ee7b7; border-radius: 8px;">
            <h2 style="color: #059669; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                What's Changed?
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                You've upgraded from <strong>{old_plan_name}</strong> to <strong>{new_plan_name}</strong>. Your new features and limits are active immediately!
            </p>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Log in now to explore your enhanced capabilities and take advantage of everything your new plan has to offer.
            </p>
        </div>
        """,
            f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Previous Plan
                    </td>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; text-align: right; text-decoration: line-through; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {old_plan_name} ({old_price})
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        New Plan
                    </td>
                    <td style="color: #059669; font-size: 16px; padding: 8px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {new_plan_name} ({new_price})
                    </td>
                </tr>
                {
                ""
                if not proration_amount
                else f'''
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Prorated Charge
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {proration_amount}
                    </td>
                </tr>
                '''
            }
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Next Billing Date
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {billing_date}
                    </td>
                </tr>
            </table>
        </div>
        """,
            f"""
        {
                ""
                if not proration_amount
                else f'''
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>About the prorated charge:</strong> Since you upgraded mid-billing cycle, we've charged you {proration_amount} for the remaining time on your new plan. Your next full billing will occur on {billing_date}.
        </p>
        '''
            }
        """,
            primary_button("View Subscription", manage_url),
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Questions about your upgrade? Our support team is here to help you make the most of your new plan.
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thank you for choosing Rext AI! We're excited to support your growth.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
