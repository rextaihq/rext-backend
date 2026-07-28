"""
Subscription Expired Email Template

Sent when a subscription has expired and access has ended — distinct from the
"expiring soon" reminder, which warns *before* expiry.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def render_subscription_expired_email(
    user_name: str,
    plan_name: str,
    expiry_date: str = None,
    resubscribe_url: str = "https://app.rext.com/pricing",
    dashboard_url: str = "https://app.rext.com/settings/billing",
    frontend_url: str = "https://app.rext.com"
) -> str:
    """
    Render subscription expired email template.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the expired plan
        expiry_date: Date the subscription expired (e.g., "July 24, 2026")
        resubscribe_url: URL to choose a plan again
        dashboard_url: URL to billing dashboard
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    expiry_line = (
        f"Your <strong>{plan_name}</strong> subscription expired on <strong>{expiry_date}</strong>."
        if expiry_date
        else f"Your <strong>{plan_name}</strong> subscription has expired."
    )

    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: {_FONT};">
            Your Subscription Has Expired
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {_FONT};">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {_FONT};">
            {expiry_line} Your account has been moved to the free plan and paid features are no longer available.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fef2f2; border: 2px solid #fca5a5; border-radius: 8px;">
            <h2 style="color: #991b1b; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: {_FONT};">
                What You Can Do
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: {_FONT};">
                Resubscribe at any time to restore full access to your workspaces, team members and generation credits. Your data is safe and will be waiting for you.
            </p>
        </div>
        """,
        primary_button("Choose a Plan", resubscribe_url),
        f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: {_FONT};">
            Questions about your account? Reach out any time — we're happy to help you pick up where you left off.
        </p>
        """,
        simple_footer()
    ])

    return email_html
