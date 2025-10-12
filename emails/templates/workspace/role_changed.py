"""
Role Changed Notification Template

Sent when a workspace member's role is changed.
"""
from typing import Optional
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def render_role_changed_email(
    workspace_name: str,
    member_name: str,
    old_role_name: str,
    new_role_name: str,
    changed_by_name: str,
    workspace_url: Optional[str] = None,
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Render role changed notification email template.

    Sent to member when their workspace role is changed.

    Args:
        workspace_name: Name of the workspace
        member_name: Name of member whose role changed
        old_role_name: Previous role name
        new_role_name: New role name
        changed_by_name: Name of person who made the change
        workspace_url: URL to workspace
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_role_changed_email(
        ...     workspace_name="Acme Inc",
        ...     member_name="Jane",
        ...     old_role_name="Viewer",
        ...     new_role_name="Editor",
        ...     changed_by_name="John Doe"
        ... )
    """
    if workspace_url is None:
        workspace_url = f"{frontend_url}/workspaces"

    # Determine if this is a promotion or demotion (simple heuristic)
    role_hierarchy = {
        "owner": 4,
        "admin": 3,
        "editor": 2,
        "viewer": 1,
        "member": 1
    }

    old_level = role_hierarchy.get(old_role_name.lower(), 0)
    new_level = role_hierarchy.get(new_role_name.lower(), 0)

    is_promotion = new_level > old_level
    emoji = "🎉" if is_promotion else "🔄"
    action_word = "upgraded" if is_promotion else "changed"

    email_html = compose_email([
        simple_header(workspace_name),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your role in {workspace_name} has been {action_word} {emoji}
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {member_name},
        </p>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{changed_by_name}</strong> has updated your role in <strong>{workspace_name}</strong>.
        </p>
        """,
        f"""
        <div style="margin: 24px 0; padding: 24px; background-color: #eff6ff; border-radius: 8px; border: 1px solid #93c5fd;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding: 12px 0; text-align: center;">
                        <p style="color: #9ca3af; font-size: 14px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            Previous Role
                        </p>
                        <p style="color: #6b7280; font-size: 18px; font-weight: 600; margin: 0; text-decoration: line-through; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            {old_role_name}
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 12px 0; text-align: center;">
                        <p style="color: #1e40af; font-size: 24px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            ↓
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 12px 0; text-align: center;">
                        <p style="color: #1e40af; font-size: 14px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>New Role</strong>
                        </p>
                        <p style="color: #1e40af; font-size: 22px; font-weight: 700; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            {new_role_name}
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your new role may come with different permissions and access levels. Visit the workspace to see what you can do.
        </p>
        """,
        primary_button("Go to Workspace", workspace_url),
        """
        <div style="margin-top: 32px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>📋 What's changed?</strong>
            </p>
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Different roles have different permissions. Check your workspace settings to see what actions you can now perform with your new role.
            </p>
        </div>
        """,
        f"""
        <div style="margin-top: 24px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you have questions about this change, please contact {changed_by_name} or your workspace administrator.
            </p>
        </div>
        """,
        simple_footer()
    ], preview_text=f"Your role in {workspace_name} changed from {old_role_name} to {new_role_name}")

    return email_html


# Convenience function for use with EmailService
def create_role_changed_email(
    workspace_name: str,
    member_name: str,
    old_role_name: str,
    new_role_name: str,
    changed_by_name: str,
    workspace_id: Optional[str] = None,
    frontend_url: str = "https://app.wrext.com",
    unsubscribe_token: Optional[str] = None
) -> str:
    """
    Create role changed notification email.

    Args:
        workspace_name: Name of the workspace
        member_name: Name of member whose role changed
        old_role_name: Previous role name
        new_role_name: New role name
        changed_by_name: Name of person who made the change
        workspace_id: Workspace UUID (optional, for direct link)
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token for user preferences

    Returns:
        Complete HTML email string
    """
    if workspace_id:
        workspace_url = f"{frontend_url}/workspaces/{workspace_id}"
    else:
        workspace_url = f"{frontend_url}/workspaces"

    # Determine if this is a promotion or demotion
    role_hierarchy = {
        "owner": 4,
        "admin": 3,
        "editor": 2,
        "viewer": 1,
        "member": 1
    }

    old_level = role_hierarchy.get(old_role_name.lower(), 0)
    new_level = role_hierarchy.get(new_role_name.lower(), 0)
    is_promotion = new_level > old_level
    emoji = "🎉" if is_promotion else "🔄"
    action_word = "upgraded" if is_promotion else "changed"

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
            Your role in {workspace_name} has been {action_word} {emoji}
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {member_name},
        </p>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            <strong>{changed_by_name}</strong> has updated your role in <strong>{workspace_name}</strong>.
        </p>
        """,
        f"""
        <div style="margin: 24px 0; padding: 24px; background-color: #eff6ff; border-radius: 8px; border: 1px solid #93c5fd;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                    <td style="padding: 12px 0; text-align: center;">
                        <p style="color: #9ca3af; font-size: 14px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            Previous Role
                        </p>
                        <p style="color: #6b7280; font-size: 18px; font-weight: 600; margin: 0; text-decoration: line-through; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            {old_role_name}
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 12px 0; text-align: center;">
                        <p style="color: #1e40af; font-size: 24px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            ↓
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 12px 0; text-align: center;">
                        <p style="color: #1e40af; font-size: 14px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            <strong>New Role</strong>
                        </p>
                        <p style="color: #1e40af; font-size: 22px; font-weight: 700; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                            {new_role_name}
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        """,
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your new role may come with different permissions and access levels. Visit the workspace to see what you can do.
        </p>
        """,
        primary_button("Go to Workspace", workspace_url),
        """
        <div style="margin-top: 32px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="color: #374151; font-size: 14px; line-height: 20px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>📋 What's changed?</strong>
            </p>
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Different roles have different permissions. Check your workspace settings to see what actions you can now perform with your new role.
            </p>
        </div>
        """,
        f"""
        <div style="margin-top: 24px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you have questions about this change, please contact {changed_by_name} or your workspace administrator.
            </p>
        </div>
        """,
        unsubscribe_html,
        simple_footer()
    ], preview_text=f"Your role in {workspace_name} changed from {old_role_name} to {new_role_name}")

    return email_html
