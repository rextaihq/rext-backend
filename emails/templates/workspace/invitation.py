"""
Workspace Invitation Template

Sent when a user is invited to join a workspace.
"""
from typing import Optional
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def get_role_permissions_html(role_name: str) -> str:
    """
    Get HTML describing permissions for a given role.

    Args:
        role_name: Name of the role (e.g., "Admin", "Editor", "Viewer")

    Returns:
        HTML string with role permissions
    """
    role_lower = role_name.lower()

    # Define permissions for common roles
    permissions_map = {
        "owner": [
            "Full workspace access",
            "Manage workspace settings",
            "Invite and remove members",
            "Delete workspace"
        ],
        "admin": [
            "Manage workspace content",
            "Invite and manage members",
            "Configure workspace settings",
            "View analytics and reports"
        ],
        "editor": [
            "Create and edit content",
            "Manage topics and knowledge",
            "Collaborate with team members",
            "Submit content for review"
        ],
        "member": [
            "View workspace content",
            "Create content",
            "Collaborate with team",
            "Access knowledge base"
        ],
        "viewer": [
            "View workspace content",
            "Browse knowledge base",
            "Read-only access",
            "No editing permissions"
        ]
    }

    # Get permissions for this role or default
    permissions = permissions_map.get(role_lower, [
        f"Access as {role_name}",
        "Collaborate with team members"
    ])

    permissions_html = "".join([
        f'<li style="color: #166534; font-size: 14px; line-height: 24px; margin: 4px 0;">{perm}</li>'
        for perm in permissions
    ])

    return f"""
    <div style="margin: 24px 0; padding: 20px; background-color: #f0fdf4; border-radius: 6px; border: 1px solid #86efac;">
        <p style="color: #166534; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>✨ As {role_name}, you can:</strong>
        </p>
        <ul style="margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            {permissions_html}
        </ul>
    </div>
    """


def render_workspace_invitation_email(
    workspace_name: str,
    inviter_name: str,
    invitation_url: str,
    role_name: str = "Member",
    expiry_days: int = 7,
    workspace_description: Optional[str] = None,
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Render workspace invitation email template.

    Args:
        workspace_name: Name of the workspace
        inviter_name: Name of person sending invitation
        invitation_url: Complete URL with invitation token
        role_name: Role being assigned (e.g., "Admin", "Editor", "Viewer")
        expiry_days: Days until invitation expires (default 7)
        workspace_description: Optional workspace description
        frontend_url: Base frontend URL for branding

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_workspace_invitation_email(
        ...     workspace_name="Acme Inc",
        ...     inviter_name="John Doe",
        ...     invitation_url="https://app.wrext.com/invitations/accept?token=abc123",
        ...     role_name="Editor"
        ... )
    """
    description_html = ""
    if workspace_description:
        description_html = f"""
        <div style="margin: 24px 0; padding: 16px; background-color: #f9fafb; border-radius: 6px; border-left: 4px solid #3b82f6;">
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>About this workspace:</strong><br>
                {workspace_description}
            </p>
        </div>
        """

    email_html = compose_email([
        simple_header(workspace_name),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You've been invited to join {workspace_name}
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{inviter_name}</strong> has invited you to collaborate on <strong>{workspace_name}</strong>.
        </p>
        """,
        f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #eff6ff; border-radius: 6px; border: 1px solid #bfdbfe;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #1e40af; font-size: 14px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>Your Role:</strong> {role_name}
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #1e40af; font-size: 14px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>Workspace:</strong> {workspace_name}
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        """,
        description_html,
        get_role_permissions_html(role_name),
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Click the button below to accept this invitation and start collaborating:
        </p>
        """,
        primary_button("Accept Invitation", invitation_url),
        f"""
        <div style="margin-top: 32px; padding: 16px; background-color: #fef3c7; border-radius: 6px; border-left: 4px solid #f59e0b;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>⏱️ This invitation will expire in {expiry_days} days.</strong> Make sure to accept it before it expires.
            </p>
        </div>
        """,
        """
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>If the button doesn't work, copy and paste this link into your browser:</strong>
            </p>
            <p style="color: #3b82f6; font-size: 13px; line-height: 20px; margin: 0; font-family: 'Courier New', monospace; word-break: break-all;">
                {invitation_url}
            </p>
        </div>
        """.format(invitation_url=invitation_url),
        f"""
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you don't know {inviter_name} or weren't expecting this invitation, you can safely ignore this email.
            </p>
        </div>
        """,
        simple_footer()
    ], preview_text=f"You've been invited to join {workspace_name} on WREXT")

    return email_html


# Convenience function for use with EmailService
def create_workspace_invitation_email(
    workspace_name: str,
    inviter_name: str,
    invitation_token: str,
    role_name: str = "Member",
    expiry_days: int = 7,
    workspace_description: Optional[str] = None,
    frontend_url: str = "https://app.wrext.com",
    unsubscribe_token: Optional[str] = None
) -> str:
    """
    Create workspace invitation email with token.

    Builds the invitation URL from token and renders the email.

    Args:
        workspace_name: Name of the workspace
        inviter_name: Name of person sending invitation
        invitation_token: Invitation token
        role_name: Role being assigned
        expiry_days: Days until expiration
        workspace_description: Optional workspace description
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token (only for existing users)

    Returns:
        Complete HTML email string
    """
    invitation_url = f"{frontend_url}/invitations/accept?token={invitation_token}"

    description_html = ""
    if workspace_description:
        description_html = f"""
        <div style="margin: 24px 0; padding: 16px; background-color: #f9fafb; border-radius: 6px; border-left: 4px solid #3b82f6;">
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>About this workspace:</strong><br>
                {workspace_description}
            </p>
        </div>
        """

    # Build unsubscribe footer (only for existing users with preferences)
    unsubscribe_html = ""
    if unsubscribe_token:
        unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
        unsubscribe_html = f"""
        <div style="margin-top: 32px; padding: 20px; text-align: center; background-color: #f9fafb; border-radius: 6px;">
            <p style="margin: 0; font-size: 12px; color: #6b7280; line-height: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Don't want to receive workspace invitation emails?
                <a href="{unsubscribe_url}" style="color: #6b7280; text-decoration: underline;">Unsubscribe</a>
            </p>
        </div>
        """

    email_html = compose_email([
        simple_header(workspace_name),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You've been invited to join {workspace_name}
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{inviter_name}</strong> has invited you to collaborate on <strong>{workspace_name}</strong>.
        </p>
        """,
        f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #eff6ff; border-radius: 6px; border: 1px solid #bfdbfe;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #1e40af; font-size: 14px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>Your Role:</strong> {role_name}
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="color: #1e40af; font-size: 14px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>Workspace:</strong> {workspace_name}
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        """,
        description_html,
        get_role_permissions_html(role_name),
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Click the button below to accept this invitation and start collaborating:
        </p>
        """,
        primary_button("Accept Invitation", invitation_url),
        f"""
        <div style="margin-top: 32px; padding: 16px; background-color: #fef3c7; border-radius: 6px; border-left: 4px solid #f59e0b;">
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>⏱️ This invitation will expire in {expiry_days} days.</strong> Make sure to accept it before it expires.
            </p>
        </div>
        """,
        f"""
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>If the button doesn't work, copy and paste this link into your browser:</strong>
            </p>
            <p style="color: #3b82f6; font-size: 13px; line-height: 20px; margin: 0; font-family: 'Courier New', monospace; word-break: break-all;">
                {invitation_url}
            </p>
        </div>
        """,
        f"""
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you don't know {inviter_name} or weren't expecting this invitation, you can safely ignore this email.
            </p>
        </div>
        """,
        unsubscribe_html,
        simple_footer()
    ], preview_text=f"You've been invited to join {workspace_name} on WREXT")

    return email_html
