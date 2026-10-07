"""
Trial Reminder Email Template - 3 Days

Sent 3 days before trial period ends.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_trial_reminder_3_days_email(
    user_name: str,
    plan_name: str,
    trial_end_date: str,
    upgrade_url: str = "https://app.rext.ai/pricing",
    manage_url: str = "https://app.rext.ai/subscription",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render 3-day trial reminder email template.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the trial plan
        trial_end_date: Date when trial ends (e.g., "January 18, 2025")
        upgrade_url: URL to upgrade/add payment method
        manage_url: URL to manage subscription
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Trial Ends in 3 Days ⏰
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your <strong>{plan_name}</strong> trial will end on <strong>{trial_end_date}</strong> — just 3 days from now!
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fafafa; border: 1px solid #e5e5e5; border-radius: 8px;">
            <h2 style="color: #171717; font-size: 20px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Keep Going After Your Trial
            </h2>
            <p style="color: #404040; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Choose a plan before {trial_end_date} to keep researching keywords and writing articles without a break.
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
            f"""
        <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <a href="{manage_url}" style="color: #171717; text-decoration: underline;">Manage your subscription</a>
        </p>
        """,
            """
        <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Questions? Our team is here to help. Reply to this email or visit our support center.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
