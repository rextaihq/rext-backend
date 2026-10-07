"""
Member Removed Notification Template

Sent when a member is removed from a workspace.
"""

from typing import Optional

from emails.components import primary_button, simple_footer, simple_header
from emails.site_links import SITE_CONTACT_URL
from emails.utils.renderer import compose_email


def render_member_removed_email(
    workspace_name: str,
    member_name: str,
    removed_by_name: str,
    reason: Optional[str] = None,
    support_url: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
) -> str:
    """
    Render member removed notification email template.

    Sent to member when they are removed from a workspace.

    Args:
        workspace_name: Name of the workspace
        member_name: Name of removed member
        removed_by_name: Name of person who removed the member
        reason: Optional reason for removal
        support_url: URL to support/contact page
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_member_removed_email(
        ...     workspace_name="Acme Inc",
        ...     member_name="Jane",
        ...     removed_by_name="John Doe",
        ...     reason="Project concluded"
        ... )
    """
    if support_url is None:
        support_url = SITE_CONTACT_URL

    reason_html = ""
    if reason:
        reason_html = f"""
        <div style="margin: 24px 0; padding: 16px; background-color: #fffbeb; border-radius: 6px; border-left: 4px solid #fbbf24;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Reason for removal:</strong>
            </p>
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {reason}
            </p>
        </div>
        """

    email_html = compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You've been removed from {workspace_name}
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {member_name},
        </p>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{removed_by_name}</strong> has removed you from the <strong>{workspace_name}</strong> workspace.
        </p>
        """,
            reason_html,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-radius: 8px; border: 1px solid #fecaca;">
            <p style="color: #991b1b; font-size: 15px; line-height: 22px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>⚠️ What this means:</strong>
            </p>
            <ul style="color: #991b1b; font-size: 14px; line-height: 20px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li style="margin-bottom: 8px;">You no longer have access to this workspace</li>
                <li style="margin-bottom: 8px;">You cannot view or edit workspace content</li>
                <li>You will not receive notifications about this workspace</li>
            </ul>
        </div>
        """,
            """
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your other workspaces remain unaffected, and you can continue using Rext AI normally.
        </p>
        """,
            """
        <div style="text-align: center; margin: 32px 0;">
        """,
            primary_button("View My Workspaces", f"{frontend_url}/w"),
            """
        </div>
        """,
            f"""
        <div style="margin-top: 32px; padding: 16px; background-color: #f5f5f5; border-radius: 6px;">
            <p style="color: #404040; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Have questions or concerns?</strong>
            </p>
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you believe this was a mistake or have questions about this removal, please contact {removed_by_name} or reach out to our support team.
            </p>
            <a href="{support_url}" style="color: #171717; text-decoration: underline; font-size: 14px; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Contact Support →
            </a>
        </div>
        """,
            """
        <div style="margin-top: 32px; border-top: 1px solid #e5e5e5; padding-top: 24px;">
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                This is an automated notification. No action is required from you unless you wish to discuss this change.
            </p>
        </div>
        """,
            simple_footer(),
        ],
        preview_text=f"You've been removed from {workspace_name}",
    )

    return email_html


# Convenience function for use with EmailService
def create_member_removed_email(
    workspace_name: str,
    member_name: str,
    removed_by_name: str,
    reason: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Create member removed notification email.

    Args:
        workspace_name: Name of the workspace
        member_name: Name of removed member
        removed_by_name: Name of person who removed the member
        reason: Optional reason for removal
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token for user preferences

    Returns:
        Complete HTML email string
    """
    support_url = SITE_CONTACT_URL

    reason_html = ""
    if reason:
        reason_html = f"""
        <div style="margin: 24px 0; padding: 16px; background-color: #fffbeb; border-radius: 6px; border-left: 4px solid #fbbf24;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Reason for removal:</strong>
            </p>
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {reason}
            </p>
        </div>
        """

    # Build unsubscribe footer
    unsubscribe_html = ""
    if unsubscribe_token:
        unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
        unsubscribe_html = f"""
        <div style="margin-top: 32px; padding: 20px; text-align: center; background-color: #fafafa; border-radius: 6px;">
            <p style="margin: 0; font-size: 12px; color: #737373; line-height: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Don't want to receive workspace notifications?
                <a href="{unsubscribe_url}" style="color: #737373; text-decoration: underline;">Unsubscribe</a>
            </p>
        </div>
        """

    email_html = compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You've been removed from {workspace_name}
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {member_name},
        </p>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{removed_by_name}</strong> has removed you from the <strong>{workspace_name}</strong> workspace.
        </p>
        """,
            reason_html,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-radius: 8px; border: 1px solid #fecaca;">
            <p style="color: #991b1b; font-size: 15px; line-height: 22px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>⚠️ What this means:</strong>
            </p>
            <ul style="color: #991b1b; font-size: 14px; line-height: 20px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li style="margin-bottom: 8px;">You no longer have access to this workspace</li>
                <li style="margin-bottom: 8px;">You cannot view or edit workspace content</li>
                <li>You will not receive notifications about this workspace</li>
            </ul>
        </div>
        """,
            """
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your other workspaces remain unaffected, and you can continue using Rext AI normally.
        </p>
        """,
            """
        <div style="text-align: center; margin: 32px 0;">
        """,
            primary_button("View My Workspaces", f"{frontend_url}/w"),
            """
        </div>
        """,
            f"""
        <div style="margin-top: 32px; padding: 16px; background-color: #f5f5f5; border-radius: 6px;">
            <p style="color: #404040; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>Have questions or concerns?</strong>
            </p>
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you believe this was a mistake or have questions about this removal, please contact {removed_by_name} or reach out to our support team.
            </p>
            <a href="{support_url}" style="color: #171717; text-decoration: underline; font-size: 14px; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Contact Support →
            </a>
        </div>
        """,
            """
        <div style="margin-top: 32px; border-top: 1px solid #e5e5e5; padding-top: 24px;">
            <p style="color: #737373; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                This is an automated notification. No action is required from you unless you wish to discuss this change.
            </p>
        </div>
        """,
            unsubscribe_html,
            simple_footer(),
        ],
        preview_text=f"You've been removed from {workspace_name}",
    )

    return email_html
