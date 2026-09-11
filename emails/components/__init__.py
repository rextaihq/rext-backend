"""
Email Components

Reusable components for building email templates.
All components generate table-based HTML for maximum email client compatibility.
"""

from .base import EmailLayoutProps, email_layout, render_email
from .button import (
    ButtonProps,
    button,
    danger_button,
    primary_button,
    secondary_button,
    success_button,
)
from .footer import FooterLink, FooterProps, footer, simple_footer, standard_footer
from .header import HeaderProps, branded_header, header, simple_header

__all__ = [
    # Base layout
    "email_layout",
    "EmailLayoutProps",
    "render_email",
    # Buttons
    "button",
    "ButtonProps",
    "primary_button",
    "secondary_button",
    "success_button",
    "danger_button",
    # Header
    "header",
    "HeaderProps",
    "simple_header",
    "branded_header",
    # Footer
    "footer",
    "FooterProps",
    "FooterLink",
    "simple_footer",
    "standard_footer",
]
