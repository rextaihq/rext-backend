# REXT Email Templates

Python-based email template system with reusable components for generating professional, email-client-compatible HTML emails.

## Overview

This package provides a component-based system for building email templates. All components use table-based layouts and inline styles for maximum compatibility across email clients (Gmail, Outlook, Apple Mail, etc.).

## Features

- ✅ **Table-based layouts** for email client compatibility
- ✅ **Inline styles** for consistent rendering
- ✅ **Reusable components** (buttons, headers, footers)
- ✅ **Variable substitution** with `{{variable}}` syntax
- ✅ **Component composition** for complex emails
- ✅ **Preview text** support for email clients
- ✅ **Outlook VML** compatibility for buttons
- ✅ **Responsive design** (600px max width)

## Directory Structure

```
emails/
├── __init__.py              # Package root
├── components/              # Reusable UI components
│   ├── __init__.py
│   ├── base.py             # Base email layout
│   ├── button.py           # Button components
│   ├── header.py           # Header components
│   └── footer.py           # Footer components
├── templates/               # Email templates (to be created)
│   ├── auth/               # Authentication emails
│   └── workspace/          # Workspace emails
└── utils/                   # Utilities
    ├── __init__.py
    └── renderer.py         # Template rendering
```

## Quick Start

### Simple Email

```python
from emails.utils.renderer import render_email

html = render_email(
    "<h1>Hello World!</h1><p>This is a test email.</p>",
    preview_text="Test email preview"
)
```

### Using Components

```python
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email

html = compose_email([
    simple_header("My Workspace"),
    "<h1>Welcome!</h1>",
    "<p>Thanks for signing up.</p>",
    primary_button("Get Started", "https://app.rext.com"),
    simple_footer()
], preview_text="Welcome to REXT")
```

### Variable Substitution

```python
from emails.utils.renderer import render_template

template = """
<h1>Hello {{name}}!</h1>
<p>Welcome to {{workspace}}.</p>
"""

context = {
    "name": "John Doe",
    "workspace": "Acme Inc"
}

html = render_template(template, context)
```

## Components

### Base Layout

The base layout provides the HTML structure with proper DOCTYPE, meta tags, and responsive container.

```python
from emails.components.base import render_email, EmailLayoutProps

html = render_email(
    content="<h1>My Content</h1>",
    preview_text="Email preview text",
    background_color="#f6f9fc",
    content_background="#ffffff"
)
```

### Buttons

Four button styles available: primary (blue), secondary (gray), success (green), danger (red).

```python
from emails.components.button import primary_button, secondary_button

# Primary button (blue)
btn1 = primary_button("Click Me", "https://example.com")

# Secondary button (gray)
btn2 = secondary_button("Learn More", "https://example.com")

# Custom button
from emails.components.button import button, ButtonProps
btn3 = button(ButtonProps(
    text="Custom Button",
    url="https://example.com",
    background_color="#10b981",
    text_color="#ffffff"
))
```

### Headers

```python
from emails.components.header import simple_header, branded_header

# Simple text header
header1 = simple_header(workspace_name="Acme Inc")

# Branded header with logo
header2 = branded_header(
    logo_url="https://example.com/logo.png",
    workspace_name="Acme Inc"
)
```

### Footers

```python
from emails.components.footer import simple_footer, standard_footer

# Minimal footer
footer1 = simple_footer()

# Standard footer with links
footer2 = standard_footer(
    company_name="REXT",
    company_address="123 Main St, San Francisco, CA 94105",
    unsubscribe_url="https://app.rext.com/unsubscribe"
)

# Custom footer
from emails.components.footer import footer, FooterProps, FooterLink
footer3 = footer(FooterProps(
    company_name="REXT",
    links=[
        FooterLink(text="Help", url="https://help.rext.com"),
        FooterLink(text="Privacy", url="https://rext.com/privacy")
    ]
))
```

## Template Rendering

### TemplateRenderer Class

```python
from emails.utils.renderer import TemplateRenderer
from emails.components.base import EmailLayoutProps

renderer = TemplateRenderer()

# Render with layout
html = renderer.render(
    template_content="<h1>Hello {{name}}</h1>",
    context={"name": "John"},
    layout_props=EmailLayoutProps(preview_text="Hello")
)

# Render without layout
html_fragment = renderer.render_without_layout(
    template_content="<p>Hello {{name}}</p>",
    context={"name": "John"}
)
```

### Convenience Functions

```python
from emails.utils.renderer import render_template, compose_email

# Simple template rendering
html = render_template(
    "<h1>Hello {{name}}</h1>",
    {"name": "John"},
    preview_text="Welcome"
)

# Compose multiple components
html = compose_email([
    header_html,
    content_html,
    button_html,
    footer_html
], preview_text="Email preview")
```

## Email Client Compatibility

All components are tested for compatibility with:

- ✅ Gmail (Web, iOS, Android)
- ✅ Outlook (Windows, Mac, Web)
- ✅ Apple Mail (iOS, macOS)
- ✅ Yahoo Mail
- ✅ ProtonMail
- ✅ Thunderbird

### Key Compatibility Features

1. **Table-based layouts** - Works in all email clients
2. **Inline styles** - No external CSS needed
3. **VML for Outlook** - Button rendering in Outlook
4. **Max-width 600px** - Optimal for mobile and desktop
5. **System fonts** - Fallback font stack
6. **Minimal CSS** - Only essential styles

## Best Practices

### 1. Use Preview Text

Always include preview text to control what appears in email inbox previews:

```python
html = render_email(
    content,
    preview_text="This text appears in inbox preview"
)
```

### 2. Inline Styles

All styles should be inline. The components handle this automatically:

```python
# Good - inline styles
"<p style='color: #374151; font-size: 16px;'>Text</p>"

# Bad - external CSS (won't work in many email clients)
"<style>.text { color: #374151; }</style><p class='text'>Text</p>"
```

### 3. Use Tables for Layout

```python
# Good - table layout
"""
<table role="presentation" width="100%">
    <tr><td>Content</td></tr>
</table>
"""

# Avoid - div-based layout (unreliable in email clients)
"<div style='display: flex;'>Content</div>"
```

### 4. Test Variables

Always provide fallback values for template variables:

```python
context = {
    "name": user.name or "there",  # Fallback to "there"
    "workspace": workspace.name or "your workspace"
}
```

### 5. Keep It Simple

- Use system fonts (no custom fonts)
- Avoid complex layouts
- Test in multiple email clients
- Keep total email size under 100KB

## Integration with EmailService

The email templates integrate seamlessly with the existing EmailService:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.email_service import EmailService
from emails.utils.renderer import compose_email
from emails.components import simple_header, primary_button, simple_footer

async def send_invitation_email(
    db: AsyncSession,
    to_email: str,
    inviter_name: str,
    workspace_name: str,
    invite_url: str
):
    # Build email HTML
    html = compose_email([
        simple_header(workspace_name),
        f"<h1>You've been invited!</h1>",
        f"<p>{inviter_name} invited you to join {workspace_name}.</p>",
        primary_button("Accept Invitation", invite_url),
        simple_footer()
    ], preview_text=f"You've been invited to {workspace_name}")

    # Send via EmailService
    email_service = EmailService(db)
    await email_service.send_email(
        to=to_email,
        subject=f"Invitation to join {workspace_name}",
        html=html,
        template_type="workspace_invitation",
        tags={"type": "invitation"}
    )
```

## Testing

Run the test suite to verify all components:

```bash
python3 test_email_components.py
```

This will:
1. Test all imports
2. Test component rendering
3. Generate a sample email HTML file
4. Save output to `test_email_output.html`

Open `test_email_output.html` in a browser to preview the email.

## Next Steps

### Phase 3, Task 3.2: Create Auth Email Templates

Create templates for authentication flows:
- Email verification
- Password reset
- Welcome email

### Phase 3, Task 3.3: Create Workspace Email Templates

Create templates for workspace operations:
- Workspace invitation
- Invitation accepted
- Role changed
- Member removed

### Phase 3, Task 3.4: Template Preview Endpoint

Create FastAPI endpoint for previewing email templates in the admin UI.

## Troubleshooting

### Import Errors

Make sure the project root is in your Python path:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### Missing Variables

The renderer will replace missing variables with `[variable_name]`:

```python
template = "Hello {{name}}"
context = {}  # Missing 'name'
# Result: "Hello [name]"
```

Provide all required variables in the context dictionary.

### Email Not Rendering Correctly

1. Check for inline styles (not external CSS)
2. Use table-based layouts
3. Test in different email clients
4. Validate HTML structure

## Resources

- [Email Client CSS Support](https://www.caniemail.com/)
- [Really Good Emails](https://reallygoodemails.com/) - Inspiration
- [HTML Email Best Practices](https://www.emailonacid.com/blog/)
- [Litmus Email Testing](https://www.litmus.com/)

## Version

Current version: **1.0.0**

## License

Internal use only - REXT
