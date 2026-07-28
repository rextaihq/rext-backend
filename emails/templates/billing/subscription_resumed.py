"""
Subscription Resumed Email Template

Sent when a previously paused subscription is resumed.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def render_subscription_resumed_email(
    user_name: str,
    plan_name: str,
    next_billing_date: str = None,
    dashboard_url: str = "https://app.rext.com/settings/billing",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.rext.com"
) -> str:
    """
    Render subscription resumed email template.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the resumed plan
        next_billing_date: Next billing date (e.g., "February 15, 2025")
        dashboard_url: URL to billing dashboard
        customer_portal_url: Optional payment provider portal URL
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    billing_line = (
        f"Your next billing date is <strong>{next_billing_date}</strong>."
        if next_billing_date
        else "Your regular billing schedule has resumed."
    )

    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: {_FONT};">
            Welcome Back!
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {_FONT};">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {_FONT};">
            Your <strong>{plan_name}</strong> subscription is active again and all your features are restored.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #ecfdf5; border: 2px solid #6ee7b7; border-radius: 8px;">
            <h2 style="color: #065f46; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: {_FONT};">
                ✅ You're All Set
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: {_FONT};">
                {billing_line}
            </p>
        </div>
        """,
        primary_button("Go to Dashboard", dashboard_url),
        f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: {_FONT};">
            Thanks for sticking with REXT — it's good to have you back.
        </p>
        """,
        simple_footer()
    ])

    return email_html
