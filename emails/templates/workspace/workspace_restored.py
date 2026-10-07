"""
Workspace Restored Notification Template

Sent to workspace owner when a soft-deleted workspace is restored.
"""

import os
from typing import Optional

from emails.components import primary_button, simple_footer, simple_header
from emails.utils.renderer import compose_email


def render_workspace_restored_email(
    workspace_name: str,
    user_name: str,
    frontend_url: str = os.getenv("FRONTEND_URL"),
    unsubscribe_token: Optional[str] = None,
) -> str:
    """
    Render workspace restored notification email template.

    Args:
        workspace_name: Name of the restored workspace
        user_name: Name of the workspace owner
        frontend_url: Base frontend URL
        unsubscribe_token: Optional unsubscribe token

    Returns:
        Complete HTML email string
    """

    unsubscribe_html = ""
    if unsubscribe_token:
        unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
        unsubscribe_html = f"""
        <div style="margin-top: 32px; padding: 20px; text-align: center; background-color: #fafafa; border-radius: 6px;">
            <p style="margin: 0; font-size: 12px; color: #737373; line-height: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                Don't want to receive these notifications?
                <a href="{unsubscribe_url}" style="color: #737373; text-decoration: underline;">Unsubscribe</a>
            </p>
        </div>
        """

    email_html = compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #171717; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Workspace '{workspace_name}' has been restored
        </h1>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Hi {user_name},
        </p>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 24px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Your workspace <strong>{workspace_name}</strong> has been successfully restored and is active again. All of its content and settings are exactly as you left them.
        </p>
        """,
            """
        <div style="margin: 24px 0; padding: 20px; background-color: #ecfdf5; border-radius: 8px; border: 1px solid #a7f3d0;">
            <p style="color: #065f46; font-size: 14px; line-height: 20px; margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                If you didn't request this restoration, please contact support immediately.
            </p>
        </div>
        """,
            """
        <div style="text-align: center; margin: 32px 0;">
        """,
            primary_button("Back to Workspaces", f"{frontend_url}/w"),
            """
        </div>
        """,
            unsubscribe_html,
            simple_footer(),
        ],
        preview_text=f"Workspace '{workspace_name}' restored",
    )

    return email_html


def create_workspace_restored_email(
    workspace_name: str,
    user_name: str,
    frontend_url: str = os.getenv("FRONTEND_URL"),
    unsubscribe_token: Optional[str] = None,
    **kwargs,
) -> str:
    """Convenience function for use with EmailService."""
    return render_workspace_restored_email(
        workspace_name=workspace_name,
        user_name=user_name,
        frontend_url=frontend_url,
        unsubscribe_token=unsubscribe_token,
    )
