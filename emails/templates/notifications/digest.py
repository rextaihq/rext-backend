"""
Account Activity Digest Email Template

Sent on a schedule (daily / weekly / monthly) to users who have enabled the
digest in their notification preferences. Summarises the notifications that
were generated in their account during the period.
"""

from html import escape
from typing import Dict, List

from emails.components import primary_button, simple_header, standard_footer
from emails.utils.renderer import compose_email

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def _section_html(section: Dict) -> str:
    """Render one grouped section: a heading + up to a handful of items."""
    title = escape(str(section.get("title", "Activity")))
    items: List[Dict] = section.get("items", [])
    count = section.get("count", len(items))

    rows = ""
    for item in items:
        headline = escape(str(item.get("title", "")))
        detail = escape(str(item.get("message", "")))
        when = escape(str(item.get("when", "")))
        rows += f"""
        <tr>
            <td style="padding: 10px 0; border-bottom: 1px solid #f5f5f5;">
                <p style="color: #171717; font-size: 14px; font-weight: 600; margin: 0 0 2px 0; font-family: {_FONT};">{headline}</p>
                <p style="color: #737373; font-size: 13px; line-height: 19px; margin: 0; font-family: {_FONT};">{detail}</p>
                <p style="color: #737373; font-size: 12px; margin: 4px 0 0 0; font-family: {_FONT};">{when}</p>
            </td>
        </tr>
        """

    more = ""
    remaining = count - len(items)
    if remaining > 0:
        more = f"""
        <p style="color: #737373; font-size: 13px; margin: 8px 0 0 0; font-family: {_FONT};">
            + {remaining} more
        </p>
        """

    return f"""
    <div style="margin: 24px 0 0 0;">
        <h3 style="color: #171717; font-size: 16px; font-weight: 700; margin: 0 0 6px 0; font-family: {_FONT};">
            {title} <span style="color: #737373; font-weight: 500;">({count})</span>
        </h3>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
            {rows}
        </table>
        {more}
    </div>
    """


def render_digest_email(
    user_name: str,
    period_label: str,
    period_range: str,
    total_count: int,
    sections: List[Dict],
    notifications_url: str,
    unsubscribe_url: str,
) -> str:
    """
    Render the account activity digest email.

    Args:
        user_name: Recipient's name for the greeting.
        period_label: Human label for the cadence, e.g. "Daily", "Weekly".
        period_range: Human date range covered, e.g. "Aug 27 – Aug 28, 2026".
        total_count: Total number of activity items in the period.
        sections: List of {"title": str, "count": int, "items": [
                  {"title": str, "message": str, "when": str}, ...]}.
        notifications_url: Link to the in-app notifications view.
        unsubscribe_url: Link to disable the digest / manage preferences.

    Returns:
        Complete HTML email string.
    """
    safe_name = escape(str(user_name or "there"))
    safe_label = escape(str(period_label))
    safe_range = escape(str(period_range))

    sections_html = "".join(_section_html(s) for s in sections)

    return compose_email(
        [
            simple_header(),
            f"""
        <h1 style="color: #171717; font-size: 26px; font-weight: 700; margin: 0 0 8px 0; font-family: {_FONT};">
            Your {safe_label} Digest
        </h1>
        <p style="color: #737373; font-size: 14px; margin: 0 0 24px 0; font-family: {_FONT};">
            {safe_range}
        </p>
        """,
            f"""
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 16px 0; font-family: {_FONT};">
            Hi {safe_name},
        </p>
        <p style="color: #404040; font-size: 16px; line-height: 24px; margin: 0 0 8px 0; font-family: {_FONT};">
            Here's what happened in your account — <strong>{total_count}</strong>
            update{"s" if total_count != 1 else ""} in this period.
        </p>
        """,
            sections_html,
            primary_button("View all activity", notifications_url),
            f"""
        <p style="color: #737373; font-size: 13px; line-height: 19px; margin: 32px 0 0 0; font-family: {_FONT};">
            You're receiving this because the {safe_label.lower()} digest is enabled
            in your notification settings.
        </p>
        """,
            standard_footer(unsubscribe_url=unsubscribe_url),
        ]
    )
