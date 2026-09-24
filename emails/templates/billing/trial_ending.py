"""
Trial Ending Email Template

Sent 3 days before trial period ends.
"""

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_trial_ending_email(
    user_name: str,
    plan_name: str,
    trial_end_date: str,
    days_remaining: int,
    upgrade_url: str = "https://app.rext.ai/pricing",
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render trial ending email template.

    Sent 3 days before trial expires.

    Args:
        user_name: User's first name or display name
        plan_name: Name of the trial plan
        trial_end_date: Date when trial ends (e.g., "January 18, 2025")
        days_remaining: Number of days left in trial
        upgrade_url: URL to upgrade/add payment method
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email(
        [
            simple_header(),
            """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Trial is Ending Soon ⏰
        </h1>
        """,
            f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your <strong>{plan_name}</strong> trial will end in <strong>{days_remaining} days</strong> on <strong>{trial_end_date}</strong>.
        </p>
        """,
            f"""
        <div style="margin: 32px 0; padding: 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px;">
            <h2 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Don't Lose Access!
            </h2>
            <p style="color: #ffffff; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                To continue enjoying all premium features after {trial_end_date}, add a payment method to your account.
            </p>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #f9fafb; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ✨ What You'll Keep:
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Unlimited workspaces</li>
                <li>Unlimited team members</li>
                <li>Unlimited topics and content</li>
                <li>Advanced AI features</li>
                <li>Priority support</li>
            </ul>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 8px;">
            <h3 style="color: #dc2626; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ⚠️ After Trial Ends:
            </h3>
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your account will be downgraded to the free plan with limited features:
            </p>
            <ul style="color: #6b7280; font-size: 13px; line-height: 20px; margin: 8px 0 0 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>1 workspace only</li>
                <li>3 team members maximum</li>
                <li>Limited API calls</li>
            </ul>
        </div>
        """,
            primary_button("Continue with Premium", upgrade_url),
            """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Have questions? Our team is here to help. Reply to this email or visit our support center.
        </p>
        """,
            simple_footer(),
        ]
    )

    return email_html
