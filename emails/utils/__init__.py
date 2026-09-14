"""
Email Template Utilities

Utilities for rendering and composing email templates.
"""

from .renderer import TemplateRenderer, compose_email, render_template

__all__ = [
    "TemplateRenderer",
    "render_template",
    "compose_email",
]
