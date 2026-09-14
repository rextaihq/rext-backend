"""
Knowledge Base Email Templates

Templates for knowledge base processing and management emails.
"""

from .kb_item_added import render_kb_item_added_email
from .kb_processing_completed import render_kb_processing_completed_email
from .kb_processing_failed import render_kb_processing_failed_email
from .kb_processing_started import render_kb_processing_started_email

__all__ = [
    "render_kb_processing_started_email",
    "render_kb_processing_completed_email",
    "render_kb_processing_failed_email",
    "render_kb_item_added_email",
]
