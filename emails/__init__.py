"""
WREXT Email Templates Package

Python-based email template system with reusable components.
Generates HTML emails compatible with all major email clients.

Usage:
    from emails.utils.renderer import compose_email
    from emails.components.header import simple_header
    from emails.components.button import primary_button
    from emails.components.footer import simple_footer

    html = compose_email([
        simple_header("My Workspace"),
        "<h1>Welcome!</h1>",
        primary_button("Get Started", "https://app.wrext.com"),
        simple_footer()
    ])
"""

__version__ = "1.0.0"
