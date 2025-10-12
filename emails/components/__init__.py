"""
Email Components

Reusable components for building email templates.
All components generate table-based HTML for maximum email client compatibility.
"""
from .base import email_layout, EmailLayoutProps, render_email
from .button import (
    button,
    ButtonProps,
    primary_button,
    secondary_button,
    success_button,
    danger_button
)
from .header import header, HeaderProps, simple_header, branded_header
from .footer import footer, FooterProps, FooterLink, simple_footer, standard_footer

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
