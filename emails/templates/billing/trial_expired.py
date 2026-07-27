"""
Trial Expired Email Template

Sent after the trial has expired.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_trial_expired_email(
    user_name: str,
    plan_name: str,
    upgrade_url: str = "https://app.rext.ai/pricing",
    support_url: str = "https://app.rext.ai/support",
    frontend_url: str = "https://app.rext.ai"
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
    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your Trial Has Expired
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your <strong>{plan_name}</strong> trial has expired. Your account has been downgraded to our free plan.
        </p>
        """,
        """
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 8px;">
            <h3 style="color: #dc2626; font-size: 16px; font-weight: 600; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Your Current Free Plan Includes:
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 20px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Access to 1 workspace</li>
                <li>Up to 3 team members</li>
                <li>Limited API calls per month</li>
                <li>Basic features only</li>
            </ul>
        </div>
        """,
        """
        <div style="margin: 24px 0; padding: 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px;">
            <h2 style="color: #ffffff; font-size: 20px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                It's Not Too Late! 🚀
            </h2>
            <p style="color: #ffffff; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Upgrade now and regain access to all premium features, unlimited workspaces, and priority support.
            </p>
        </div>
        """,
        """
        <div style="margin: 24px 0; padding: 20px; background-color: #f0fdf4; border-radius: 8px;">
            <h3 style="color: #059669; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                ✨ Upgrade to Premium and Get:
            </h3>
            <ul style="color: #374151; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li><strong>Unlimited workspaces</strong> and team collaboration</li>
                <li><strong>Unlimited content</strong> creation and topics</li>
                <li><strong>Advanced AI features</strong> and analytics</li>
                <li><strong>Priority support</strong> from our team</li>
                <li><strong>Full API access</strong> and integrations</li>
                <li><strong>Export capabilities</strong> and data portability</li>
            </ul>
        </div>
        """,
        primary_button("Upgrade to Premium", upgrade_url),
        """
        <div style="margin: 32px 0; padding: 16px; background-color: #fffbeb; border-radius: 8px; border: 1px solid #fbbf24;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                💡 <strong>Save 20%</strong> with annual billing! Lock in your rate today.
            </p>
        </div>
        """,
        f"""
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Have questions about pricing or features? <a href="{support_url}" style="color: #667eea; text-decoration: none;">Visit our support center</a> or reply to this email.
        </p>
        """,
        """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 16px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We're here to help you get the most out of REXT. Thank you for trying our platform!
        </p>
        """,
        simple_footer()
    ])

    return email_html
