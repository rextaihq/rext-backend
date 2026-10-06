"""
Trial Reminder Email Template - Expiring Today

Sent on the day the trial expires.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_trial_reminder_expiring_today_email(
    user_name: str,
    plan_name: str,
    trial_end_date: str,
    upgrade_url: str = "https://app.rext.ai/pricing",
    manage_url: str = "https://app.rext.ai/subscription",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render trial expiring today email template.

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
        <h1 style="color: #dc2626; font-size: 30px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Trial Ends Today! 🚨
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your <strong>{plan_name}</strong> trial ends <strong>today</strong>. Choose a plan today to keep researching keywords and writing articles.
        </p>
        """,
            """
        <div style="margin: 32px 0; padding: 28px; background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); border-radius: 12px; box-shadow: 0 4px 6px rgba(220, 38, 38, 0.2);">
            <h2 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ⚡ Choose a Plan Today
            </h2>
            <p style="color: #ffffff; font-size: 17px; line-height: 26px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your trial ends at the end of today. Nothing in your account is deleted when it does: your workspaces, articles and keyword library stay, and a plan lets you keep writing.
            </p>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                After today
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Your workspaces, articles and keyword library stay in your account.</li>
                <li>Researching keywords and writing articles needs an active plan.</li>
                <li>Choose a plan whenever you're ready and pick up where you left off.</li>
            </ul>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                With a paid plan
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Monthly credits for keyword research and articles</li>
                <li>Workspaces and team members to match the plan you choose</li>
                <li>Every plan and what it includes is on the pricing page</li>
            </ul>
            <p style="color: #374151; font-size: 14px; line-height: 22px; margin: 12px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your workspaces, articles and keyword library stay in your account either way.
            </p>
        </div>
        """,
            primary_button("Choose a Plan", upgrade_url),
            """
        <div style="margin: 32px 0; padding: 16px; background-color: #fffbeb; border-radius: 8px; border: 1px solid #fbbf24;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                💡 <strong>Tip:</strong> annual billing costs less than paying monthly; the pricing page shows both.
            </p>
        </div>
        """,
            f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 24px 0 0 0; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <a href="{manage_url}" style="color: #667eea; text-decoration: none;">Manage your subscription</a>
        </p>
        """,
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Questions or need help? Reply to this email immediately and our team will assist you.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
