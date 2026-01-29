"""
Header Component for Emails

Provides branded header with logo and optional workspace customization.
"""
from typing import Optional
from dataclasses import dataclass


@dataclass
class HeaderProps:
    """Props for email header component"""
    logo_url: Optional[str] = None
    logo_alt: str = "REXT"
    workspace_name: Optional[str] = None
    background_color: str = "#ffffff"
    text_color: str = "#111827"
    border_bottom: str = "1px solid #e5e7eb"


def header(props: Optional[HeaderProps] = None) -> str:
    """
    Render email header component.

    Includes logo (if provided) and optional workspace name.
    Uses table structure for email client compatibility.

    Args:
        props: Header configuration properties

    Returns:
        HTML string for header component
    """
    if props is None:
        props = HeaderProps()

    # Logo section
    logo_html = ""
    if props.logo_url:
        logo_html = f"""
        <img src="{props.logo_url}"
             alt="{props.logo_alt}"
             width="120"
             height="auto"
             style="display: block; max-width: 120px; height: auto;">
        """
    else:
        # Text-based logo if no image provided
        logo_html = f"""
        <div style="font-size: 24px; font-weight: 700; color: {props.text_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            {props.logo_alt}
        </div>
        """

    # Workspace name section
    workspace_html = ""
    if props.workspace_name:
        workspace_html = f"""
        <div style="margin-top: 8px; font-size: 14px; color: #6b7280; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            {props.workspace_name}
        </div>
        """

    return f"""
    <!-- Header -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
            <td style="padding-bottom: 30px; border-bottom: {props.border_bottom};">
                {logo_html}
                {workspace_html}
            </td>
        </tr>
    </table>
    """


def simple_header(workspace_name: Optional[str] = None) -> str:
    """Render a simple header without logo."""
    return header(HeaderProps(workspace_name=workspace_name))


def branded_header(logo_url: str, workspace_name: Optional[str] = None) -> str:
    """Render a branded header with logo."""
    return header(HeaderProps(logo_url=logo_url, workspace_name=workspace_name))
