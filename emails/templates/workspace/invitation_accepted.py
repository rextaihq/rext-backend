"""
Invitation Accepted Notification Template

Sent to the workspace owner/admin when someone accepts an invitation.
"""
from typing import Optional
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_invitation_accepted_email(
    workspace_name: str,
    new_member_name: str,
    new_member_email: str,
    role_name: str = "Member",
    workspace_url: str = None,
    accepted_by_name: Optional[str] = None,
    frontend_url: str = "https://app.rext.com"
) -> str:
    """
    Render invitation accepted notification email template.

    Sent to workspace admins/owners when invitation is accepted.

    Args:
        workspace_name: Name of the workspace
        new_member_name: Name of person who accepted
        new_member_email: Email of person who accepted
        role_name: Role assigned to new member
        workspace_url: URL to workspace members page
        accepted_by_name: Name of person who accepted (if different from member name)
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_invitation_accepted_email(
        ...     workspace_name="Acme Inc",
        ...     new_member_name="Jane Smith",
        ...     new_member_email="jane@example.com",
        ...     role_name="Editor"
        ... )
    """
    if workspace_url is None:
        workspace_url = f"{frontend_url}/workspaces"

    member_display = new_member_name if new_member_name else new_member_email
    accepted_by_display = accepted_by_name if accepted_by_name else member_display

    email_html = compose_email([
        simple_header(workspace_name),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            New member joined {workspace_name} ✅
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{accepted_by_display}</strong> has accepted your invitation and joined <strong>{workspace_name}</strong>.
        </p>
        """,
        f"""
        <div style="margin: 24px 0; padding: 24px; background-color: #f0fdf4; border-radius: 8px; border: 1px solid #86efac;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #166534; font-size: 15px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>New Member:</strong> {member_display}
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #166534; font-size: 15px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>Email:</strong> {new_member_email}
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #166534; font-size: 15px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>Role:</strong> {role_name}
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            They can now access workspace resources and collaborate with your team.
        </p>
        """,
        primary_button("View Workspace Members", workspace_url),
        f"""
        <div style="margin-top: 32px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>💡 Quick Actions:</strong>
            </p>
            <ul style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li style="margin-bottom: 8px;">Adjust member permissions if needed</li>
                <li style="margin-bottom: 8px;">Share workspace resources and guidelines</li>
                <li>Send a welcome message to introduce the team</li>
            </ul>
        </div>
        """,
        simple_footer()
    ], preview_text=f"{accepted_by_display} joined {workspace_name}")

    return email_html


# Convenience function for use with EmailService
def create_invitation_accepted_email(
    workspace_name: str,
    new_member_name: str,
    new_member_email: str,
    role_name: str = "Member",
    workspace_id: Optional[str] = None,
    frontend_url: str = "https://app.rext.com",
    unsubscribe_token: Optional[str] = None
) -> str:
    """
    Create invitation accepted notification email.

    Args:
        workspace_name: Name of the workspace
        new_member_name: Name of person who accepted
        new_member_email: Email of person who accepted
        role_name: Role assigned to new member
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

    member_display = new_member_name if new_member_name else new_member_email

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
            New member joined {workspace_name} ✅
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{member_display}</strong> has accepted your invitation and joined <strong>{workspace_name}</strong>.
        </p>
        """,
        f"""
        <div style="margin: 24px 0; padding: 24px; background-color: #f0fdf4; border-radius: 8px; border: 1px solid #86efac;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #166534; font-size: 15px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>New Member:</strong> {member_display}
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #166534; font-size: 15px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>Email:</strong> {new_member_email}
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #166534; font-size: 15px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>Role:</strong> {role_name}
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            They can now access workspace resources and collaborate with your team.
        </p>
        """,
        primary_button("View Workspace Members", workspace_url),
        """
        <div style="margin-top: 32px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>💡 Quick Actions:</strong>
            </p>
            <ul style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li style="margin-bottom: 8px;">Adjust member permissions if needed</li>
                <li style="margin-bottom: 8px;">Share workspace resources and guidelines</li>
                <li>Send a welcome message to introduce the team</li>
            </ul>
        </div>
        """,
        unsubscribe_html,
        simple_footer()
    ], preview_text=f"{member_display} joined {workspace_name}")

    return email_html
