"""
Invitation Declined Notification Template

Sent to the workspace owner/admin when someone declines an invitation.
"""
from typing import Optional
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_invitation_declined_email(
    workspace_name: str,
    declined_by_email: str,
    decline_reason: Optional[str] = None,
    workspace_url: str = None,
    frontend_url: str = "https://app.rext.com"
) -> str:
    """
    Render invitation declined notification email template.

    Sent to workspace admins/owners when invitation is declined.

    Args:
        workspace_name: Name of the workspace
        declined_by_email: Email of person who declined
        decline_reason: Optional reason for declining
        workspace_url: URL to workspace members page
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_invitation_declined_email(
        ...     workspace_name="Acme Inc",
        ...     declined_by_email="jane@example.com",
        ...     decline_reason="Not interested at this time"
        ... )
    """
    if workspace_url is None:
        workspace_url = f"{frontend_url}/workspaces"

    # Build reason section
    reason_html = ""
    if decline_reason:
        reason_html = f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-radius: 8px; border: 1px solid #fecaca;">
            <p style="color: #991b1b; font-size: 15px; margin: 0 0 8px 0; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Reason provided:
            </p>
            <p style="color: #7f1d1d; font-size: 14px; margin: 0; font-style: italic; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                "{decline_reason}"
            </p>
        </div>
        """

    email_html = compose_email([
        simple_header(workspace_name),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Invitation to {workspace_name} was declined
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{declined_by_email}</strong> has declined your invitation to join <strong>{workspace_name}</strong>.
        </p>
        """,
        reason_html,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            No further action is required. You may send a new invitation in the future if circumstances change.
        </p>
        """,
        primary_button("View Workspace Settings", workspace_url),
        f"""
        <div style="margin-top: 32px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>💡 Next Steps:</strong>
            </p>
            <ul style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li style="margin-bottom: 8px;">Review if a different role might be more appropriate</li>
                <li style="margin-bottom: 8px;">Consider reaching out directly to discuss their concerns</li>
                <li>You can send a new invitation anytime from workspace settings</li>
            </ul>
        </div>
        """,
        simple_footer()
    ], preview_text=f"{declined_by_email} declined invitation to {workspace_name}")

    return email_html


# Convenience function for use with EmailService
def create_invitation_declined_email(
    workspace_name: str,
    declined_by_email: str,
    decline_reason: Optional[str] = None,
    workspace_id: Optional[str] = None,
    frontend_url: str = "https://app.rext.com",
    unsubscribe_token: Optional[str] = None
) -> str:
    """
    Create invitation declined notification email.

    Args:
        workspace_name: Name of the workspace
        declined_by_email: Email of person who declined
        decline_reason: Optional reason for declining
        workspace_id: Workspace UUID (optional, for direct link)
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token for user preferences

    Returns:
        Complete HTML email string
    """
    if workspace_id:
        workspace_url = f"{frontend_url}/workspaces/{workspace_id}/members"
    else:
        workspace_url = f"{frontend_url}/workspaces"

    # Build reason section
    reason_html = ""
    if decline_reason:
        reason_html = f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #fef2f2; border-radius: 8px; border: 1px solid #fecaca;">
            <p style="color: #991b1b; font-size: 15px; margin: 0 0 8px 0; font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Reason provided:
            </p>
            <p style="color: #7f1d1d; font-size: 14px; margin: 0; font-style: italic; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                "{decline_reason}"
            </p>
        </div>
        """

    # Build unsubscribe footer
    unsubscribe_html = ""
    if unsubscribe_token:
        unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
        unsubscribe_html = f"""
        <div style="margin-top: 32px; padding: 20px; text-align: center; background-color: #f9fafb; border-radius: 6px;">
            <p style="margin: 0; font-size: 12px; color: #6b7280; line-height: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Don't want to receive workspace notifications?
                <a href="{unsubscribe_url}" style="color: #6b7280; text-decoration: underline;">Unsubscribe</a>
            </p>
        </div>
        """

    email_html = compose_email([
        simple_header(workspace_name),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Invitation to {workspace_name} was declined
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{declined_by_email}</strong> has declined your invitation to join <strong>{workspace_name}</strong>.
        </p>
        """,
        reason_html,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            No further action is required. You may send a new invitation in the future if circumstances change.
        </p>
        """,
        primary_button("View Workspace Settings", workspace_url),
        """
        <div style="margin-top: 32px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>💡 Next Steps:</strong>
            </p>
            <ul style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li style="margin-bottom: 8px;">Review if a different role might be more appropriate</li>
                <li style="margin-bottom: 8px;">Consider reaching out directly to discuss their concerns</li>
                <li>You can send a new invitation anytime from workspace settings</li>
            </ul>
        </div>
        """,
        unsubscribe_html,
        simple_footer()
    ], preview_text=f"{declined_by_email} declined invitation to {workspace_name}")

    return email_html
