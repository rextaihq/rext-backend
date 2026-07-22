"""
Subscription Reactivated Email Template

Sent when a user reactivates a subscription that was scheduled to cancel.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_subscription_reactivated_email(
    user_name: str,
    plan_name: str,
    dashboard_url: str = "https://app.rext.com/settings/subscription",
    frontend_url: str = "https://app.rext.com"
) -> str:
    """
    Render subscription reactivated email template.

    Sent when a user undoes a pending cancellation before it takes effect.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the reactivated plan
        dashboard_url: URL to subscription settings
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Subscription Reactivated 🎉
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Good news — your pending cancellation has been undone. Your <strong>{plan_name}</strong> subscription is active and will continue to renew as normal.
        </p>
        """,
        f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #f0fdf4; border-left: 4px solid #10b981; border-radius: 8px;">
            <p style="color: #065f46; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>✓ Your {plan_name} features remain active</strong><br>
                Nothing else changes — your billing cycle and credits continue uninterrupted.
            </p>
        </div>
        """,
        primary_button("View Subscription", dashboard_url),
        """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Thanks for staying with REXT!
        </p>
        """,
        simple_footer()
    ])

    return email_html
