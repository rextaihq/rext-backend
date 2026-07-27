"""
Workspace Invitation Template

Sent when a user is invited to join a workspace.
"""
from typing import Optional
from emails.components import simple_header, simple_footer
from emails.components.button import button, ButtonProps
from emails.utils.renderer import compose_email

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def _role_badge(role_name: str) -> str:
    return f"""
    <div style="display:inline-block; background-color:#eef0fe; color:#3641f5;
                font-size:13px; font-weight:600; padding:4px 12px; border-radius:9999px;
                font-family:{_FONT}; letter-spacing:0.01em;">
        {role_name}
    </div>
    """


def render_workspace_invitation_email(
    workspace_name: str,
    inviter_name: str,
    invitation_url: str,
    role_name: str = "Member",
    expiry_days: int = 7,
    workspace_description: Optional[str] = None,
    frontend_url: str = "https://staging.rext.ai"
) -> str:
    description_html = ""
    if workspace_description:
        description_html = f"""
        <div style="margin:24px 0; padding:16px 20px; background-color:#f8f9ff;
                    border-radius:8px; border-left:3px solid #3641f5;">
            <p style="color:#344054; font-size:14px; line-height:22px; margin:0;
                      font-family:{_FONT};">
                <strong>About this workspace:</strong><br>{workspace_description}
            </p>
        </div>
        """

    return compose_email([
        simple_header(workspace_name),
        f"""
        <h1 style="color:#101828; font-size:26px; font-weight:700; margin:32px 0 12px 0;
                   font-family:{_FONT}; letter-spacing:-0.02em; line-height:1.3;">
            You've been invited to join<br><span style="color:#3641f5;">{workspace_name}</span>
        </h1>
        """,
        f"""
        <p style="color:#475467; font-size:16px; line-height:26px; margin:0 0 24px 0;
                  font-family:{_FONT};">
            <strong style="color:#101828;">{inviter_name}</strong> has invited you to
            collaborate on <strong style="color:#101828;">{workspace_name}</strong>.
            You'll be joining as:
        </p>
        """,
        _role_badge(role_name),
        description_html,
        f"""
        <p style="color:#475467; font-size:15px; line-height:24px; margin:28px 0 8px 0;
                  font-family:{_FONT};">
            Accept the invitation to get started:
        </p>
        """,
        button(ButtonProps(text="Accept Invitation", url=invitation_url, background_color="#3641f5")),
        f"""
        <p style="color:#98a2b3; font-size:13px; line-height:20px; margin:24px 0 0 0;
                  font-family:{_FONT};">
            This invitation expires in <strong style="color:#475467;">{expiry_days} days</strong>.
            If the button above doesn't work, copy and paste this link into your browser:
        </p>
        <p style="color:#3641f5; font-size:12px; line-height:20px; margin:6px 0 0 0;
                  font-family:'Courier New', monospace; word-break:break-all;">
            {invitation_url}
        </p>
        """,
        f"""
        <div style="margin-top:32px; padding-top:24px; border-top:1px solid #e4e7ec;">
            <p style="color:#98a2b3; font-size:13px; line-height:20px; margin:0;
                      font-family:{_FONT};">
                If you don't know {inviter_name} or weren't expecting this, you can safely ignore this email.
            </p>
        </div>
        """,
        simple_footer()
    ], preview_text=f"{inviter_name} invited you to join {workspace_name} on REXT")


def create_workspace_invitation_email(
    workspace_name: str,
    inviter_name: str,
    invitation_token: str,
    role_name: str = "Member",
    expiry_days: int = 7,
    workspace_description: Optional[str] = None,
    frontend_url: str = "https://staging.rext.ai",
    unsubscribe_token: Optional[str] = None,
    **kwargs
) -> str:
    invitation_url = f"{frontend_url}/invitations/accept?token={invitation_token}"

    unsubscribe_html = ""
    if unsubscribe_token:
        unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
        unsubscribe_html = f"""
        <div style="margin-top:24px; text-align:center;">
            <p style="margin:0; font-size:12px; color:#98a2b3; font-family:{_FONT};">
                Don't want these emails?
                <a href="{unsubscribe_url}" style="color:#98a2b3; text-decoration:underline;">Unsubscribe</a>
            </p>
        </div>
        """

    description_html = ""
    if workspace_description:
        description_html = f"""
        <div style="margin:24px 0; padding:16px 20px; background-color:#f8f9ff;
                    border-radius:8px; border-left:3px solid #3641f5;">
            <p style="color:#344054; font-size:14px; line-height:22px; margin:0;
                      font-family:{_FONT};">
                <strong>About this workspace:</strong><br>{workspace_description}
            </p>
        </div>
        """

    return compose_email([
        simple_header(workspace_name),
        f"""
        <h1 style="color:#101828; font-size:26px; font-weight:700; margin:32px 0 12px 0;
                   font-family:{_FONT}; letter-spacing:-0.02em; line-height:1.3;">
            You've been invited to join<br><span style="color:#3641f5;">{workspace_name}</span>
        </h1>
        """,
        f"""
        <p style="color:#475467; font-size:16px; line-height:26px; margin:0 0 24px 0;
                  font-family:{_FONT};">
            <strong style="color:#101828;">{inviter_name}</strong> has invited you to
            collaborate on <strong style="color:#101828;">{workspace_name}</strong>.
            You'll be joining as:
        </p>
        """,
        _role_badge(role_name),
        description_html,
        f"""
        <p style="color:#475467; font-size:15px; line-height:24px; margin:28px 0 8px 0;
                  font-family:{_FONT};">
            Accept the invitation to get started:
        </p>
        """,
        button(ButtonProps(text="Accept Invitation", url=invitation_url, background_color="#3641f5")),
        f"""
        <p style="color:#98a2b3; font-size:13px; line-height:20px; margin:24px 0 0 0;
                  font-family:{_FONT};">
            This invitation expires in <strong style="color:#475467;">{expiry_days} days</strong>.
            If the button above doesn't work, copy and paste this link into your browser:
        </p>
        <p style="color:#3641f5; font-size:12px; line-height:20px; margin:6px 0 0 0;
                  font-family:'Courier New', monospace; word-break:break-all;">
            {invitation_url}
        </p>
        """,
        f"""
        <div style="margin-top:32px; padding-top:24px; border-top:1px solid #e4e7ec;">
            <p style="color:#98a2b3; font-size:13px; line-height:20px; margin:0;
                      font-family:{_FONT};">
                If you don't know {inviter_name} or weren't expecting this, you can safely ignore this email.
            </p>
        </div>
        """,
        unsubscribe_html,
        simple_footer()
    ], preview_text=f"{inviter_name} invited you to join {workspace_name} on REXT")
