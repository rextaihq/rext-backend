"""
Trial Expired Email Template

Sent after the trial has expired.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.site_links import SITE_CONTACT_URL
from emails.utils.renderer import compose_email


def render_trial_expired_email(
    user_name: str,
    plan_name: str,
    upgrade_url: str = "https://app.rext.ai/pricing",
    support_url: str = SITE_CONTACT_URL,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render trial expired email template.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the expired trial plan
        upgrade_url: URL to upgrade/add payment method
        support_url: URL to support page
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Trial Has Ended
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your <strong>{plan_name}</strong> trial has ended. Your workspaces, articles and keyword library are still in your account; researching keywords and writing articles needs an active plan.
        </p>
        """,
            """
        <div style="margin: 24px 0; padding: 24px; background-color: #fafafa; border: 1px solid #e5e5e5; border-radius: 8px;">
            <h2 style="color: #171717; font-size: 20px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                It's Not Too Late! 🚀
            </h2>
            <p style="color: #404040; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Choose a plan and pick up where you left off.
            </p>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #fafafa; border-radius: 8px;">
            <h3 style="color: #171717; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                With a paid plan
            </h3>
            <ul style="color: #404040; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Monthly credits for keyword research and articles</li>
                <li>Workspaces and team members to match the plan you choose</li>
                <li>Every plan and what it includes is on the pricing page</li>
            </ul>
            <p style="color: #404040; font-size: 14px; line-height: 22px; margin: 12px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your workspaces, articles and keyword library stay in your account either way.
            </p>
        </div>
        """,
            primary_button("Choose a Plan", upgrade_url),
            """
        <div style="margin: 32px 0; padding: 16px; background-color: #fffbeb; border-radius: 8px; border: 1px solid #fbbf24;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                💡 Annual billing costs less than paying monthly; the pricing page shows both.
            </p>
        </div>
        """,
            f"""
        <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Have questions about pricing or features? <a href="{support_url}" style="color: #171717; text-decoration: underline;">Visit our support center</a> or reply to this email.
        </p>
        """,
            """
        <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We're here to help you get the most out of Rext AI. Thank you for trying our platform!
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
