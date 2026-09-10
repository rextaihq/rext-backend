"""
Account Recovery Review Templates

Emails for the admin-reviewed account recovery workflow (the "Account Recovery"
tab in admin User Management):

- received: the request landed and is awaiting review
- approved: an admin approved it and the account is active again
- rejected: an admin declined it

The time-limited self-service recovery link (account_recovery.py) is a separate
flow and keeps its own template.
"""
from typing import Optional

from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email

_P = (
    "color: #374151; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; "
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif;"
)
_MUTED = (
    "color: #6b7280; font-size: 14px; line-height: 20px; margin: 0; "
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif;"
)
_H1 = (
    "color: #111827; font-size: 28px; font-weight: 700; margin: 0 0 16px 0; "
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif;"
)


def _unsubscribe_block(frontend_url: str, unsubscribe_token: Optional[str]) -> str:
    if not unsubscribe_token:
        return ""
    unsubscribe_url = f"{frontend_url}/unsubscribe?token={unsubscribe_token}"
    return f"""
    <div style="margin-top: 32px; padding: 20px; text-align: center; background-color: #f9fafb; border-radius: 6px;">
        <p style="margin: 0; font-size: 12px; color: #6b7280; line-height: 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            Don't want to receive these emails?
            <a href="{unsubscribe_url}" style="color: #6b7280; text-decoration: underline;">Unsubscribe</a>
        </p>
    </div>
    """


# ---------------------------------------------------------------------------
# Account deleted by an admin — how to ask for it back
# ---------------------------------------------------------------------------
def create_account_deleted_email(
    user_name: str,
    user_email: Optional[str] = None,
    retention_days: int = 14,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
) -> str:
    recovery_url = f"{frontend_url}/account-recovery"
    if user_email:
        recovery_url = f"{recovery_url}?email={user_email}"
    account_info = ""
    if user_email:
        account_info = (
            f'<p style="{_MUTED} margin-bottom: 16px;">Account: <strong>{user_email}</strong></p>'
        )
    return compose_email(
        [
            simple_header(),
            f'<h1 style="{_H1}">Your Account Has Been Deleted</h1>',
            f'<p style="{_P}">Hi {user_name},</p>',
            f'<p style="{_P}">Your Rext AI account has been deleted by an administrator. '
            f'If you think this was a mistake, you can ask our team to restore it.</p>',
            account_info,
            primary_button("Request Account Recovery", recovery_url),
            f'<p style="{_MUTED}">You have {retention_days} days to request recovery. '
            f'After that the account and its data are permanently deleted and cannot be '
            f'recovered. An administrator reviews every request and will email you the '
            f'decision.</p>',
            _unsubscribe_block(frontend_url, unsubscribe_token),
            simple_footer(),
        ],
        preview_text="Your Rext AI account was deleted — how to request recovery",
    )


# ---------------------------------------------------------------------------
# Request received
# ---------------------------------------------------------------------------
def create_account_recovery_received_email(
    user_name: str,
    user_email: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
) -> str:
    account_info = ""
    if user_email:
        account_info = (
            f'<p style="{_MUTED} margin-bottom: 16px;">Account: <strong>{user_email}</strong></p>'
        )
    return compose_email(
        [
            simple_header(),
            f'<h1 style="{_H1}">We\'ve Received Your Recovery Request</h1>',
            f'<p style="{_P}">Hi {user_name},</p>',
            f'<p style="{_P}">We\'ve received your request to recover your Rext AI account. '
            f'Our team will review it shortly and email you as soon as a decision is made.</p>',
            account_info,
            f'<p style="{_MUTED}">You don\'t need to do anything else right now. '
            f'If you didn\'t make this request, you can safely ignore this email.</p>',
            _unsubscribe_block(frontend_url, unsubscribe_token),
            simple_footer(),
        ],
        preview_text="Your Rext AI account recovery request is being reviewed",
    )


# ---------------------------------------------------------------------------
# Approved
# ---------------------------------------------------------------------------
def create_account_recovery_approved_email(
    user_name: str,
    review_note: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
) -> str:
    login_url = f"{frontend_url}/login"
    note_block = ""
    if review_note:
        note_block = f"""
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="{_MUTED}"><strong>Note from our team:</strong><br>{review_note}</p>
        </div>
        """
    return compose_email(
        [
            simple_header(),
            f'<h1 style="{_H1}">Your Account Has Been Restored</h1>',
            f'<p style="{_P}">Hi {user_name},</p>',
            f'<p style="{_P}">Good news — your account recovery request was approved and your '
            f'Rext AI account is active again. Everything is right where you left it.</p>',
            primary_button("Sign In", login_url),
            note_block,
            f"""
            <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 24px;">
                <p style="{_MUTED}">
                    If you didn't request this, contact our support team right away —
                    someone else may have access to your details.
                </p>
            </div>
            """,
            _unsubscribe_block(frontend_url, unsubscribe_token),
            simple_footer(),
        ],
        preview_text="Your Rext AI account has been restored — you can sign in again",
    )


# ---------------------------------------------------------------------------
# Rejected
# ---------------------------------------------------------------------------
def create_account_recovery_rejected_email(
    user_name: str,
    review_note: Optional[str] = None,
    frontend_url: str = "https://app.rext.ai",
    unsubscribe_token: Optional[str] = None,
) -> str:
    note_block = ""
    if review_note:
        note_block = f"""
        <div style="margin-top: 24px; padding: 16px; background-color: #f3f4f6; border-radius: 6px;">
            <p style="{_MUTED}"><strong>Reason:</strong><br>{review_note}</p>
        </div>
        """
    return compose_email(
        [
            simple_header(),
            f'<h1 style="{_H1}">We Couldn\'t Approve Your Recovery Request</h1>',
            f'<p style="{_P}">Hi {user_name},</p>',
            f'<p style="{_P}">We\'ve reviewed your request to recover your Rext AI account and '
            f'weren\'t able to approve it at this time.</p>',
            note_block,
            f'<p style="{_MUTED}">If you believe this is a mistake, reply to this email or '
            f'contact our support team and we\'ll take another look.</p>',
            _unsubscribe_block(frontend_url, unsubscribe_token),
            simple_footer(),
        ],
        preview_text="Update on your Rext AI account recovery request",
    )
