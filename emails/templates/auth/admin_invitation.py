"""
Platform Admin Invitation Template

Sent when a super admin invites someone to a platform role (super admin, admin or
support), and again when the invitation is resent.
"""

from html import escape
from typing import Optional

from emails.components import simple_footer, simple_header
from emails.components.button import ButtonProps, button
from emails.utils.renderer import compose_email

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

# The role as the email names it, by the role's own name.
ROLE_LABELS = {"super_admin": "Super admin", "admin": "Admin", "support": "Support"}


def render_admin_invitation_email(
    inviter_name: Optional[str],
    admin_role: str,
    invitation_url: str,
    expiry_days: int = 7,
    message: Optional[str] = None,
) -> str:
    """
    Render the platform admin invitation.

    Everything a person typed (the inviter's name, the message) goes in as text.

    Args:
        inviter_name: Who sent it, or None when that isn't known
        admin_role: The role's name (a key of ROLE_LABELS)
        invitation_url: The dashboard's accept page with the token
        expiry_days: Days until the link stops working
        message: The inviter's own words, optional

    Returns:
        Complete HTML email string
    """
    inviter = escape(inviter_name) if inviter_name else "A Rext AI super admin"
    role = escape(ROLE_LABELS.get(admin_role, admin_role))
    url = escape(invitation_url, quote=True)
    days = "1 day" if expiry_days == 1 else f"{int(expiry_days)} days"

    message_html = ""
    if message and message.strip():
        message_html = f"""
        <div style="margin:24px 0; padding:16px 20px; background-color:#fafafa;
                    border-radius:8px; border-left:3px solid #111a17;">
            <p style="color:#404040; font-size:14px; line-height:22px; margin:0;
                      font-family:{_FONT}; white-space:pre-wrap;">{escape(message.strip())}</p>
        </div>
        """

    return compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color:#171717; font-size:26px; font-weight:700; margin:32px 0 12px 0;
                   font-family:{_FONT}; letter-spacing:-0.02em; line-height:1.3;">
            You've been invited to help run Rext AI
        </h1>
        """,
            f"""
        <p style="color:#525252; font-size:16px; line-height:26px; margin:0 0 24px 0;
                  font-family:{_FONT};">
            <strong style="color:#171717;">{inviter}</strong> has invited you to the
            Rext AI admin area. You'll have the role:
        </p>
        """,
            f"""
        <div style="display:inline-block; background-color:#111a17; color:#cff88a;
                    font-size:13px; font-weight:600; padding:4px 12px; border-radius:9999px;
                    font-family:{_FONT}; letter-spacing:0.01em;">
            {role}
        </div>
        """,
            message_html,
            f"""
        <p style="color:#525252; font-size:15px; line-height:24px; margin:28px 0 8px 0;
                  font-family:{_FONT};">
            Sign in, or create an account, with this email address, then accept:
        </p>
        """,
            button(ButtonProps(text="Accept invitation", url=invitation_url)),
            f"""
        <p style="color:#737373; font-size:13px; line-height:20px; margin:24px 0 0 0;
                  font-family:{_FONT};">
            This invitation expires in <strong style="color:#525252;">{days}</strong> and
            works once. If the button above doesn't work, copy and paste this link into
            your browser:
        </p>
        <p style="color:#171717; font-size:12px; line-height:20px; margin:6px 0 0 0;
                  font-family:'Courier New', monospace; word-break:break-all;">
            {url}
        </p>
        """,
            f"""
        <div style="margin-top:32px; padding-top:24px; border-top:1px solid #e5e5e5;">
            <p style="color:#737373; font-size:13px; line-height:20px; margin:0;
                      font-family:{_FONT};">
                If you weren't expecting this, ignore this email: nothing changes unless
                you accept.
            </p>
        </div>
        """,
            simple_footer(),
        ],
        preview_text=f"{inviter} invited you to the Rext AI admin area",
    )
