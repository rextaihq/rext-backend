"""
Notification Email Templates

Templates for aggregated / scheduled notification emails.
"""
from .digest import render_digest_email

__all__ = [
    "render_digest_email",
]
