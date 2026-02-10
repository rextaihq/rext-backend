"""
Downgrade Scheduled Email Template

Sent when a user downgrades their subscription (takes effect at end of billing period).
"""
from emails.components import simple_header, primary_button, secondary_button, simple_footer
from emails.utils.renderer import compose_email


def render_downgrade_scheduled_email(
    user_name: str,
    current_plan_name: str,
    new_plan_name: str,
    effective_date: str,
    features_losing: list[str],
    cancel_downgrade_url: str = "https://app.rext.com/billing",
    pricing_url: str = "https://app.rext.com/pricing",
    frontend_url: str = "https://app.rext.com"
) -> str:
    """
    Render downgrade scheduled email template.

    Sent when user downgrades to a lower-tier plan (effective at end of billing period).

    Args:
        user_name: User's first name or display name
        current_plan_name: Name of the current plan
        new_plan_name: Name of the plan they're downgrading to
        effective_date: Date when downgrade will take effect
        features_losing: List of features that will no longer be available
        cancel_downgrade_url: URL to cancel the downgrade
        pricing_url: URL to view pricing options
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    features_html = "".join([
        f'<li style="margin-bottom: 8px;">❌ {feature}</li>'
        for feature in features_losing
    ])

    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Downgrade Scheduled
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            We've scheduled your downgrade from <strong>{current_plan_name}</strong> to <strong>{new_plan_name}</strong>.
        </p>
        """,
        f"""
        <div style="margin: 32px 0; padding: 24px; background-color: #fffbeb; border: 2px solid #fcd34d; border-radius: 8px;">
            <h2 style="color: #92400e; font-size: 18px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                📅 What Happens Next
            </h2>
            <p style="color: #374151; font-size: 15px; line-height: 22px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                You'll continue to have access to all <strong>{current_plan_name}</strong> features until <strong>{effective_date}</strong>. After that, your plan will automatically change to <strong>{new_plan_name}</strong>.
            </p>
        </div>
        """,
        f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-radius: 8px;">
            <h3 style="color: #111827; font-size: 16px; font-weight: 600; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Features you'll lose access to:
            </h3>
            <ul style="color: #6b7280; font-size: 14px; line-height: 22px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {features_html}
            </ul>
        </div>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Changed your mind? You can cancel the downgrade and keep your <strong>{current_plan_name}</strong> plan anytime before <strong>{effective_date}</strong>.
        </p>
        """,
        primary_button("Cancel Downgrade", cancel_downgrade_url),
        """
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
            <tr>
                <td align="center">
        """,
        secondary_button("View All Plans", pricing_url),
        """
                </td>
            </tr>
        </table>
        """,
        """
        <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 32px 0 0 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Have questions about your plan change? Reply to this email or contact our support team.
        </p>
        """,
        simple_footer()
    ])

    return email_html
