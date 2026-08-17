"""
Base Email Layout Component

Provides the foundational HTML structure for all email templates.
Follows email client best practices with table-based layout and inline styles.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class EmailLayoutProps:
    """Props for base email layout"""
    preview_text: Optional[str] = None  # Text shown in email preview
    title: str = "Rext AI"
    background_color: str = "#f6f9fc"
    content_background: str = "#ffffff"


def email_layout(
    content: str,
    props: Optional[EmailLayoutProps] = None
) -> str:
    """
    Render base email layout with content.

    Uses table-based layout for maximum email client compatibility.
    Inline styles for consistent rendering across clients.

    Args:
        content: HTML content to render inside layout
        props: Layout configuration properties

    Returns:
        Complete HTML email string
    """
    if props is None:
        props = EmailLayoutProps()

    preview_text_html = ""
    if props.preview_text:
        # Preview text with hidden spacer to prevent email clients from showing more
        preview_text_html = f"""
        <div style="display: none; max-height: 0px; overflow: hidden;">
            {props.preview_text}
        </div>
        <div style="display: none; max-height: 0px; overflow: hidden;">
            &nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{props.title}</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
    <style>
        body {{
            margin: 0;
            padding: 0;
            -webkit-text-size-adjust: 100%;
            -ms-text-size-adjust: 100%;
        }}
        table {{
            border-collapse: collapse;
            mso-table-lspace: 0pt;
            mso-table-rspace: 0pt;
        }}
        img {{
            border: 0;
            height: auto;
            line-height: 100%;
            outline: none;
            text-decoration: none;
            -ms-interpolation-mode: bicubic;
        }}
        a {{
            color: #3b82f6;
            text-decoration: underline;
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: {props.background_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    {preview_text_html}

    <!-- Main wrapper table -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: {props.background_color};">
        <tr>
            <td align="center" style="padding: 40px 10px;">

                <!-- Content container -->
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width: 600px; background-color: {props.content_background}; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);">
                    <tr>
                        <td style="padding: 40px 30px;">
                            {content}
                        </td>
                    </tr>
                </table>

            </td>
        </tr>
    </table>
</body>
</html>"""


def render_email(content: str, **kwargs) -> str:
    """
    Convenience function to render email with layout.

    Args:
        content: HTML content to render
        **kwargs: Additional props for EmailLayoutProps

    Returns:
        Complete HTML email string
    """
    props = EmailLayoutProps(**kwargs)
    return email_layout(content, props)
