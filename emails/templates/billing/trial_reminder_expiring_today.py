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
            Your <strong>{plan_name}</strong> trial ends <strong>today</strong>. This is your last chance to upgrade and keep all your premium features!
        </p>
        """,
            """
        <div style="margin: 32px 0; padding: 28px; background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); border-radius: 12px; box-shadow: 0 4px 6px rgba(220, 38, 38, 0.2);">
            <h2 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ⚡ Urgent: Upgrade Now
            </h2>
            <p style="color: #ffffff; font-size: 17px; line-height: 26px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your trial expires at the end of today. Upgrade now to avoid losing access to your premium features and data.
            </p>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-left: 4px solid #dc2626; border-radius: 8px;">
            <h3 style="color: #dc2626; font-size: 17px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                🔒 What Happens After Today:
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Your account will be downgraded to the <strong>free plan</strong></li>
                <li>Access limited to <strong>1 workspace</strong> and <strong>3 team members</strong></li>
                <li><strong>Restricted API calls</strong> and feature access</li>
                <li><strong>No priority support</strong></li>
            </ul>
        </div>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #f0fdf4; border-radius: 8px;">
            <h3 style="color: #059669; font-size: 17px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ✅ Upgrade Today and Keep:
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li><strong>Unlimited workspaces</strong> and team members</li>
                <li><strong>All premium features</strong> and AI capabilities</li>
                <li><strong>Priority support</strong> and dedicated assistance</li>
                <li><strong>Full API access</strong> and integrations</li>
                <li><strong>All your data and content</strong> preserved</li>
            </ul>
        </div>
        """,
            primary_button("Upgrade Right Now - Don't Wait!", upgrade_url),
            """
        <div style="margin: 32px 0; padding: 16px; background-color: #fffbeb; border-radius: 8px; border: 1px solid #fbbf24;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                💡 <strong>Pro tip:</strong> Choose annual billing and save 20% compared to monthly!
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
