"""
Subscription Downgraded Email Template

Sent when a user downgrades to a lower-tier plan.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_subscription_downgraded_email(
    user_name: str,
    old_plan_name: str,
    new_plan_name: str,
    old_price: str,
    new_price: str,
    effective_date: str,
    proration_amount: str = None,
    dashboard_url: str = "https://app.wrext.com/settings/billing",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Render subscription downgraded email template.

    Sent when user downgrades to a lower-tier subscription plan.

    Args:
        user_name: User's first name or display name
        old_plan_name: Previous plan name (e.g., "Pro Plan")
        new_plan_name: New plan name (e.g., "Starter Plan")
        old_price: Previous price (e.g., "$99.99/month")
        new_price: New price (e.g., "$29.99/month")
        effective_date: Date when downgrade takes effect (e.g., "January 20, 2025")
        proration_amount: Credit/refund amount (e.g., "$15.50") - optional
        dashboard_url: URL to billing dashboard (internal)
        customer_portal_url: Optional direct URL to payment provider's customer portal
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    # Prefer customer portal URL over internal dashboard
    manage_url = customer_portal_url or dashboard_url

    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #2563eb; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Subscription Updated
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your subscription has been successfully changed to <strong>{new_plan_name}</strong>. This change will take effect on <strong>{effective_date}</strong>.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fef3c7; border: 2px solid #fcd34d; border-radius: 8px;">
            <h2 style="color: #d97706; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                What's Changing?
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your plan will change from <strong>{old_plan_name}</strong> to <strong>{new_plan_name}</strong>. You'll continue to have access to your current plan features until <strong>{effective_date}</strong>.
            </p>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                After {effective_date}, your features and limits will adjust to match the {new_plan_name}. Make sure to review the new limits to ensure they meet your needs.
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
                    <td style="color: #2563eb; font-size: 16px; padding: 8px 0; text-align: right; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {new_plan_name} ({new_price})
                    </td>
                </tr>
                {"" if not proration_amount else f'''
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Account Credit
                    </td>
                    <td style="color: #059669; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {proration_amount}
                    </td>
                </tr>
                '''}
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Effective Date
                    </td>
                    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        {effective_date}
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
                </tr>
                <tr>
                    <td style="color: #6b7280; font-size: 14px; padding: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Monthly Savings
                    </td>
                    <td style="color: #059669; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                        Save {old_price} → {new_price}
                    </td>
                </tr>
            </table>
        </div>
        """,
        f"""
        {"" if not proration_amount else f'''
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>Account credit:</strong> We've applied a credit of {proration_amount} to your account for the unused portion of your {old_plan_name}. This credit will be applied to your next billing cycle.
        </p>
        '''}
        """,
        primary_button("View Subscription", manage_url),
        f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>Need more features?</strong> You can upgrade back to {old_plan_name} or any other plan at any time from your subscription dashboard.
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Questions about your plan change? Our support team is ready to assist you.
        </p>
        """,
        simple_footer()
    ])

    return email_html
