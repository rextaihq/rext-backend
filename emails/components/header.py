"""
Header Component for Emails

Provides branded header with logo and optional workspace customization.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from emails.palette import INK, LINE, MUTED
from src.utils.storage import storage_service

# Object key for the official Rext AI logo in MinIO storage, and the file it's published from.
LOGO_OBJECT_NAME = "branding/rext-logo.png"
LOGO_FILE = Path(__file__).resolve().parent.parent / "assets" / "rext-logo.png"

# True once this process has published LOGO_FILE to storage (publish_logo, at the server's start). Until then, and
# whenever publishing fails, the header writes the name as text: an email never shows a broken image.
_logo_published = False


def publish_logo() -> bool:
    """Upload LOGO_FILE to storage under LOGO_OBJECT_NAME; True when the copy there is the current one."""
    global _logo_published
    _logo_published = bool(
        storage_service.upload_file(
            LOGO_FILE.read_bytes(), LOGO_OBJECT_NAME, content_type="image/png"
        )
    )
    return _logo_published


def _default_logo_url() -> Optional[str]:
    """The official logo's URL in storage, or None while it isn't published there."""
    if not _logo_published:
        return None
    return storage_service.get_file_url(LOGO_OBJECT_NAME) or None


@dataclass
class HeaderProps:
    """Props for email header component"""

    logo_url: Optional[str] = None
    logo_alt: str = "Rext AI"
    workspace_name: Optional[str] = None
    background_color: str = "#ffffff"
    text_color: str = INK
    border_bottom: str = f"1px solid {LINE}"


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

    # Logo section - falls back to the official logo in storage, then to a text logo
    logo_url = props.logo_url if props.logo_url is not None else _default_logo_url()

    logo_html = ""
    if logo_url:
        logo_html = f"""
        <img src="{logo_url}"
             alt="{props.logo_alt}"
             width="137"
             height="24"
             style="display: block; width: 137px; max-width: 137px; height: auto;">
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
        <div style="margin-top: 8px; font-size: 14px; color: {MUTED}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
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
