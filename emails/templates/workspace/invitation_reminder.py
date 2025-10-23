"""
Workspace Invitation Reminder Template

Sent 2 days before an invitation expires to remind the recipient.
"""
from typing import Optional
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def create_invitation_reminder_email(
    workspace_name: str,
    inviter_name: str,
    invitation_token: str,
    role_name: str = "Member",
    days_until_expiry: int = 2,
    workspace_description: Optional[str] = None,
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Create invitation reminder email template.

    Sent to remind users about pending invitations that are about to expire.

    Args:
        workspace_name: Name of the workspace
        inviter_name: Name of person who sent invitation
        invitation_token: Invitation token
        role_name: Role being assigned
        days_until_expiry: Days remaining until expiration
        workspace_description: Optional workspace description
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string

    Example:
        >>> html = create_invitation_reminder_email(
        ...     workspace_name="Acme Inc",
        ...     inviter_name="John Doe",
        ...     invitation_token="abc123",
        ...     role_name="Editor",
        ...     days_until_expiry=2
        ... )
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

    # Determine urgency level for messaging
    if days_until_expiry <= 1:
        urgency_message = "⚠️ Your invitation expires <strong>tomorrow</strong>!"
        urgency_color = "#dc2626"  # Red
        urgency_bg = "#fee2e2"
    else:
        urgency_message = f"⏰ Your invitation expires in <strong>{days_until_expiry} days</strong>"
        urgency_color = "#f59e0b"  # Amber
        urgency_bg = "#fef3c7"

    email_html = compose_email([
        simple_header(workspace_name),
        """
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            ⏰ Reminder: Your workspace invitation is expiring soon
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            This is a friendly reminder that <strong>{inviter_name}</strong> has invited you to join <strong>{workspace_name}</strong>.
        </p>
        """,
        f"""
        <div style="margin: 24px 0; padding: 20px; background-color: {urgency_bg}; border-radius: 6px; border-left: 4px solid {urgency_color};">
            <p style="color: {urgency_color}; font-size: 16px; line-height: 24px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {urgency_message}
            </p>
        </div>
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
        """
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Don't miss this opportunity! Click the button below to accept your invitation now:
        </p>
        """,
        primary_button("Accept Invitation Now", invitation_url),
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
        <div style="margin-top: 32px; padding: 20px; background-color: #f0fdf4; border-radius: 6px; border: 1px solid #86efac;">
            <p style="color: #166534; font-size: 14px; line-height: 20px; margin: 0 0 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>💡 What happens next:</strong>
            </p>
            <ul style="color: #166534; font-size: 14px; line-height: 20px; margin: 0; padding-left: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <li>Click "Accept Invitation Now"</li>
                <li>Sign up for a new account or sign in if you already have one</li>
                <li>Start collaborating with {inviter_name} on {workspace_name}</li>
            </ul>
        </div>
        """,
        f"""
        <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
            <p style="color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you don't want to join {workspace_name}, you can safely ignore this email. The invitation will expire automatically.
            </p>
        </div>
        """,
        simple_footer()
    ], preview_text=f"Reminder: Your invitation to {workspace_name} expires soon!")

    return email_html
