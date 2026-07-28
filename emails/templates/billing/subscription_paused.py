"""
Subscription Paused Email Template

Sent when a subscription is paused by the user or an admin.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def render_subscription_paused_email(
    user_name: str,
    plan_name: str,
    resumes_at: str = None,
    dashboard_url: str = "https://app.rext.com/settings/billing",
    customer_portal_url: str = None,
    frontend_url: str = "https://app.rext.com"
) -> str:
    """
    Render subscription paused email template.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the paused plan
        resumes_at: Date billing resumes (e.g., "February 15, 2025"), or None if indefinite
        dashboard_url: URL to billing dashboard
        customer_portal_url: Optional payment provider portal URL
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    resume_line = (
        f"Billing is scheduled to resume on <strong>{resumes_at}</strong>."
        if resumes_at
        else "Billing is paused until you choose to resume it."
    )

    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: {_FONT};">
            Subscription Paused
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {_FONT};">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {_FONT};">
            Your <strong>{plan_name}</strong> subscription has been paused. You won't be charged while it's paused.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fffbeb; border: 2px solid #fcd34d; border-radius: 8px;">
            <h2 style="color: #92400e; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: {_FONT};">
                ⏸️ What This Means
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: {_FONT};">
                {resume_line} Your data and settings are kept safe, and paid features are unavailable until the subscription resumes.
            </p>
        </div>
        """,
        primary_button("Manage Subscription", customer_portal_url or dashboard_url),
        f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: {_FONT};">
            You can resume your subscription at any time from your billing settings.
        </p>
        """,
        simple_footer()
    ])

    return email_html
