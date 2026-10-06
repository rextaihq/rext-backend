"""
Subscription Expiring Soon Email Template

Sent when a subscription is about to expire (e.g., 7 days before end date).
"""

from emails.components import primary_button, secondary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_subscription_expiring_soon_email(
    user_name: str,
    plan_name: str,
    expiry_date: str,
    days_remaining: int,
    renew_url: str = "https://app.rext.ai/settings/subscription",
    pricing_url: str = "https://app.rext.ai/pricing",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render subscription expiring soon email template.

    Sent to remind users their subscription is ending soon.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the expiring plan
        expiry_date: Date when subscription expires (e.g., "February 15, 2025")
        days_remaining: Number of days until expiry
        renew_url: URL to renew subscription
        pricing_url: URL to view pricing options
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    # Also sent when a trial has ended (days_remaining=0).
    ended = days_remaining <= 0
    heading = "Your Plan Has Ended" if ended else "Your Plan Ends Soon"
    if ended:
        intro = f"Your <strong>{plan_name}</strong> plan has ended."
        after = (
            f"Your plan ended on <strong>{expiry_date}</strong>. Your workspaces, articles and "
            "keyword library are still in your account; researching keywords and writing "
            "articles needs an active plan."
        )
        closing = "Choose a plan to pick up where you left off."
    else:
        days = f"{days_remaining} day{'s' if days_remaining != 1 else ''}"
        intro = (
            f"This is a friendly reminder that your <strong>{plan_name}</strong> plan ends in "
            f"<strong>{days}</strong>."
        )
        after = (
            f"Your plan ends on <strong>{expiry_date}</strong>. After that, your workspaces, "
            "articles and keyword library stay in your account, but researching keywords and "
            "writing articles needs an active plan."
        )
        closing = f"Renew to keep your <strong>{plan_name}</strong> plan and its monthly credits."

    email_html = compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            {heading}
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            {intro}
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fef2f2; border: 2px solid #fca5a5; border-radius: 8px;">
            <h2 style="color: #991b1b; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ⏰ Expiration Date
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {after}
            </p>
        </div>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            {closing}
        </p>
        """,
            primary_button("Choose a Plan", pricing_url)
            if ended
            else primary_button("Renew Subscription", renew_url),
            """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
            <tr>
                <td align="center">
        """,
            # Once the plan has ended, the main button already goes to the plans.
            "" if ended else secondary_button("View Pricing", pricing_url),
            """
                </td>
            </tr>
        </table>
        """,
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Questions about your subscription? Reply to this email or contact our support team.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
