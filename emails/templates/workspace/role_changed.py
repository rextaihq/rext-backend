"""
Role Changed Notification Template

Sent when a workspace member's role is changed.
"""
from typing import Optional
from emails.components import simple_footer
from emails.components.button import button, ButtonProps
from emails.utils.renderer import compose_email

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
_ROLE_HIERARCHY = {"owner": 4, "admin": 3, "editor": 2, "member": 1, "viewer": 1}


def _branded_header() -> str:
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
            <td style="padding-bottom:32px; border-bottom:2px solid #3641f5;">
                <span style="font-size:22px; font-weight:700; color:#3641f5;
                             font-family:{_FONT}; letter-spacing:-0.02em;">REXT</span>
            </td>
        </tr>
    </table>
    """


def _role_badge(role_name: str, muted: bool = False) -> str:
    bg = "#f2f4f7" if muted else "#eef0fe"
    color = "#667085" if muted else "#3641f5"
    strike = "text-decoration:line-through;" if muted else ""
    return f"""<div style="display:inline-block; background-color:{bg}; color:{color};
                font-size:13px; font-weight:600; padding:4px 12px; border-radius:9999px;
                font-family:{_FONT}; {strike}">{role_name}</div>"""


def _role_change_card(old_role_name: str, new_role_name: str) -> str:
    return f"""
    <div style="margin:24px 0; padding:24px; background-color:#f8f9ff;
                border-radius:8px; border:1px solid #c7d0fd; text-align:center;">
        <p style="color:#667085; font-size:12px; font-weight:500; margin:0 0 10px 0;
                  text-transform:uppercase; letter-spacing:0.05em; font-family:{_FONT};">
            Previous role
        </p>
        {_role_badge(old_role_name, muted=True)}
        <p style="color:#3641f5; font-size:18px; margin:12px 0; font-family:{_FONT};">&#8595;</p>
        <p style="color:#667085; font-size:12px; font-weight:500; margin:0 0 10px 0;
                  text-transform:uppercase; letter-spacing:0.05em; font-family:{_FONT};">
            New role
        </p>
        {_role_badge(new_role_name)}
    </div>
    """


def render_role_changed_email(
    workspace_name: str,
    member_name: str,
    old_role_name: str,
    new_role_name: str,
    changed_by_name: str,
    workspace_url: Optional[str] = None,
    frontend_url: str = "https://staging.rext.ai"
) -> str:
    if workspace_url is None:
        workspace_url = f"{frontend_url}/workspaces"

    old_level = _ROLE_HIERARCHY.get(old_role_name.lower(), 0)
    new_level = _ROLE_HIERARCHY.get(new_role_name.lower(), 0)
    action_word = "upgraded" if new_level > old_level else "updated"

    return compose_email([
        _branded_header(),
        f"""
        <h1 style="color:#101828; font-size:26px; font-weight:700; margin:32px 0 12px 0;
                   font-family:{_FONT}; letter-spacing:-0.02em; line-height:1.3;">
            Your role in <span style="color:#3641f5;">{workspace_name}</span><br>has been {action_word}
        </h1>
        """,
        f"""
        <p style="color:#475467; font-size:16px; line-height:26px; margin:0 0 4px 0;
                  font-family:{_FONT};">
            Hi <strong style="color:#101828;">{member_name}</strong>,
        </p>
        <p style="color:#475467; font-size:16px; line-height:26px; margin:0 0 4px 0;
                  font-family:{_FONT};">
            <strong style="color:#101828;">{changed_by_name}</strong> has updated your role
            in <strong style="color:#101828;">{workspace_name}</strong>.
        </p>
        """,
        _role_change_card(old_role_name, new_role_name),
        f"""
        <p style="color:#475467; font-size:15px; line-height:24px; margin:0 0 8px 0;
                  font-family:{_FONT};">
            Visit your workspace to see your updated access:
        </p>
        """,
        button(ButtonProps(text="Go to Workspace", url=workspace_url, background_color="#3641f5")),
        f"""
        <div style="margin-top:32px; padding-top:24px; border-top:1px solid #e4e7ec;">
            <p style="color:#98a2b3; font-size:13px; line-height:20px; margin:0;
                      font-family:{_FONT};">
                Questions about this change? Contact {changed_by_name} or your workspace administrator.
            </p>
        </div>
        """,
        simple_footer()
    ], preview_text=f"Your role in {workspace_name} changed from {old_role_name} to {new_role_name}")


def create_role_changed_email(
    workspace_name: str,
    member_name: str,
    old_role_name: str,
    new_role_name: str,
    changed_by_name: str,
    workspace_id: Optional[str] = None,
    frontend_url: str = "https://staging.rext.ai",
    unsubscribe_token: Optional[str] = None,
    **kwargs
) -> str:
    workspace_url = (
        f"{frontend_url}/workspaces/{workspace_id}" if workspace_id
        else f"{frontend_url}/workspaces"
    )

    old_level = _ROLE_HIERARCHY.get(old_role_name.lower(), 0)
    new_level = _ROLE_HIERARCHY.get(new_role_name.lower(), 0)
    action_word = "upgraded" if new_level > old_level else "updated"

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

    return compose_email([
        _branded_header(),
        f"""
        <h1 style="color:#101828; font-size:26px; font-weight:700; margin:32px 0 12px 0;
                   font-family:{_FONT}; letter-spacing:-0.02em; line-height:1.3;">
            Your role in <span style="color:#3641f5;">{workspace_name}</span><br>has been {action_word}
        </h1>
        """,
        f"""
        <p style="color:#475467; font-size:16px; line-height:26px; margin:0 0 4px 0;
                  font-family:{_FONT};">
            Hi <strong style="color:#101828;">{member_name}</strong>,
        </p>
        <p style="color:#475467; font-size:16px; line-height:26px; margin:0 0 4px 0;
                  font-family:{_FONT};">
            <strong style="color:#101828;">{changed_by_name}</strong> has updated your role
            in <strong style="color:#101828;">{workspace_name}</strong>.
        </p>
        """,
        _role_change_card(old_role_name, new_role_name),
        f"""
        <p style="color:#475467; font-size:15px; line-height:24px; margin:0 0 8px 0;
                  font-family:{_FONT};">
            Visit your workspace to see your updated access:
        </p>
        """,
        button(ButtonProps(text="Go to Workspace", url=workspace_url, background_color="#3641f5")),
        f"""
        <div style="margin-top:32px; padding-top:24px; border-top:1px solid #e4e7ec;">
            <p style="color:#98a2b3; font-size:13px; line-height:20px; margin:0;
                      font-family:{_FONT};">
                Questions about this change? Contact {changed_by_name} or your workspace administrator.
            </p>
        </div>
        """,
        unsubscribe_html,
        simple_footer()
    ], preview_text=f"Your role in {workspace_name} changed from {old_role_name} to {new_role_name}")
