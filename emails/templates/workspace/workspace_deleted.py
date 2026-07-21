"""
Workspace Deleted Notification Template

Sent to workspace owner when a workspace is soft-deleted.
"""
from typing import Optional
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email
from dotenv import load_dotenv
import os

def render_workspace_deleted_email(
    workspace_name: str,
    user_name: str,
    recovery_deadline: str,
    remaining_workspaces: int,
    frontend_url: str = os.getenv("FRONTEND_URL"),
    unsubscribe_token: Optional[str] = None
) -> str:
    """
    Render workspace deleted notification email template.

    Args:
        workspace_name: Name of the deleted workspace
        user_name: Name of the workspace owner
        recovery_deadline: Date until which the workspace can be recovered
        remaining_workspaces: Number of workspaces the user still has
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token

    Returns:
        Complete HTML email string
    """
    
    unsubscribe_html = ""
    if unsubscribe_token:
        unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
        unsubscribe_html = f"""
        <div style="margin-top: 32px; padding: 20px; text-align: center; background-color: #f9fafb; border-radius: 6px;">
            <p style="margin: 0; font-size: 12px; color: #6b7280; line-height: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Don't want to receive these notifications?
                <a href="{unsubscribe_url}" style="color: #6b7280; text-decoration: underline;">Unsubscribe</a>
            </p>
        </div>
        """

    email_html = compose_email([
        simple_header(),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Workspace '{workspace_name}' has been deleted
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your workspace <strong>{workspace_name}</strong> has been successfully moved to the trash.
        </p>
        """,
        f"""
        <div style="margin: 24px 0; padding: 20px; background-color: #fffbeb; border-radius: 8px; border: 1px solid #fde68a;">
            <p style="color: #92400e; font-size: 15px; line-height: 22px; margin: 0 0 12px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <strong>🗓️ Important Recovery Information:</strong>
            </p>
            <p style="color: #92400e; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                You have 30 days to recover this workspace. If no action is taken, it will be permanently deleted on <strong>{recovery_deadline}</strong>.
            </p>
        </div>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            You currently have {remaining_workspaces} other active workspace(s).
        </p>
        """,
        """
        <div style="text-align: center; margin: 32px 0;">
        """,
        primary_button("Back to Workspaces", f"{frontend_url}/w"),
        """
        </div>
        """,
        unsubscribe_html,
        simple_footer()
    ], preview_text=f"Workspace '{workspace_name}' deleted")

    return email_html


def create_workspace_deleted_email(
    workspace_name: str,
    user_name: str,
    recovery_deadline: str,
    remaining_workspaces: int,
    frontend_url: str = os.getenv("FRONTEND_URL"),
    unsubscribe_token: Optional[str] = None,
    **kwargs
) -> str:
    """Convenience function for use with EmailService."""
    return render_workspace_deleted_email(
        workspace_name=workspace_name,
        user_name=user_name,
        recovery_deadline=recovery_deadline,
        remaining_workspaces=remaining_workspaces,
        frontend_url=frontend_url,
        unsubscribe_token=unsubscribe_token
    )
