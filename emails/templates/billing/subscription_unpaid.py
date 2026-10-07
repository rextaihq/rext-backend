"""
Subscription Unpaid Email Template

Sent when Lemon Squeezy's payment retries run out and the subscription becomes
unpaid: the plan stops until the card is updated.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def render_subscription_unpaid_email(
    user_name: str,
    plan_name: str,
    update_payment_url: str = "https://app.rext.ai/settings/subscription",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render the subscription unpaid email.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the plan that stopped
        update_payment_url: The billing page, which opens a fresh card-update link
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    return compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: {_FONT};">
            Your plan has stopped
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {_FONT};">
            Hi {user_name},
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {_FONT};">
            We tried your renewal payment for <strong>{plan_name}</strong> several times over the past two weeks and couldn't collect it, so your plan has stopped.
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: {_FONT};">
            Update your card to reactivate it. Your workspaces and content are kept.
        </p>
        """,
            primary_button("Update your card", update_payment_url),
            f"""
        <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: {_FONT};">
            <strong>Need help?</strong> Reply to this email and our support team will help with the payment.
        </p>
        """,
            simple_footer(),
        ]
    )
