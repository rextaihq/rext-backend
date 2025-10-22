"""
Trial Reminder Email Template - 1 Day

Sent 1 day before trial period ends.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_trial_reminder_1_day_email(
    user_name: str,
    plan_name: str,
    trial_end_date: str,
    upgrade_url: str = "https://app.wrext.com/pricing",
    manage_url: str = "https://app.wrext.com/subscription",
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Render 1-day trial reminder email template.

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
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #dc2626; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Trial Ends Tomorrow! ⚠️
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            This is your final reminder — your <strong>{plan_name}</strong> trial ends <strong>tomorrow</strong> on <strong>{trial_end_date}</strong>.
        </p>
        """,
        """
        <div style="margin: 32px 0; padding: 24px; background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); border-radius: 8px;">
            <h2 style="color: #ffffff; font-size: 22px; font-weight: 700; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ⏰ Last Chance to Keep Your Access
            </h2>
            <p style="color: #ffffff; font-size: 16px; line-height: 24px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Upgrade now to ensure uninterrupted access to all premium features.
            </p>
        </div>
        """,
        """
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 8px;">
            <h3 style="color: #dc2626; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ⚠️ After Tomorrow:
            </h3>
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Without upgrading, your account will be downgraded to the free plan with limited features:
            </p>
            <ul style="color: #6b7280; font-size: 13px; line-height: 20px; margin: 8px 0 0 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Access to 1 workspace only</li>
                <li>Maximum 3 team members</li>
                <li>Limited API calls and features</li>
                <li>No priority support</li>
            </ul>
        </div>
        """,
        """
        <div style="margin: 24px 0; padding: 20px; background-color: #f0fdf4; border-radius: 8px;">
            <h3 style="color: #059669; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                💎 Keep Everything With a Paid Plan:
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li><strong>Unlimited</strong> workspaces and team collaboration</li>
                <li><strong>Advanced AI</strong> features and analytics</li>
                <li><strong>Priority support</strong> from our team</li>
                <li><strong>Full API access</strong> and integrations</li>
            </ul>
        </div>
        """,
        primary_button("Upgrade Before It's Too Late", upgrade_url),
        f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <a href="{manage_url}" style="color: #667eea; text-decoration: none;">Manage your subscription</a>
        </p>
        """,
        """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Need help deciding? Reply to this email and we'll assist you.
        </p>
        """,
        simple_footer()
    ])

    return email_html
