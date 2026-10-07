"""
Footer Component for Emails

Provides standard email footer with links and legal text.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from emails.palette import LINE, MUTED


@dataclass
class FooterLink:
    """Link in footer"""

    text: str
    url: str


@dataclass
class FooterProps:
    """Props for email footer component"""

    # The copyright holder: Rext AI is a product of Revnix LLC (rext.ai's terms).
    company_name: str = "Revnix LLC"
    company_address: Optional[str] = None
    links: List[FooterLink] = field(default_factory=list)
    unsubscribe_url: Optional[str] = None
    text_color: str = MUTED
    link_color: str = MUTED  # told apart by its underline
    border_top: str = f"1px solid {LINE}"


def footer(props: Optional[FooterProps] = None) -> str:
    """
    Render email footer component.

    Includes company info, links, and optional unsubscribe link.
    Uses table structure for email client compatibility.

    Args:
        props: Footer configuration properties

    Returns:
        HTML string for footer component
    """
    if props is None:
        props = FooterProps()

    # Build links section
    links_html = ""
    if props.links:
        link_items = [
            f'<a href="{link.url}" style="color: {props.link_color}; text-decoration: underline;">{link.text}</a>'
            for link in props.links
        ]
        links_html = f"""
        <tr>
            <td style="padding: 10px 0; text-align: center; font-size: 14px; color: {props.text_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {" • ".join(link_items)}
            </td>
        </tr>
        """

    # Company address
    address_html = ""
    if props.company_address:
        address_html = f"""
        <tr>
            <td style="padding: 10px 0; text-align: center; font-size: 12px; color: {props.text_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {props.company_address}
            </td>
        </tr>
        """

    # Unsubscribe link
    unsubscribe_html = ""
    if props.unsubscribe_url:
        unsubscribe_html = f"""
        <tr>
            <td style="padding: 10px 0; text-align: center; font-size: 12px; color: {props.text_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <a href="{props.unsubscribe_url}" style="color: {props.link_color}; text-decoration: underline;">Unsubscribe</a>
            </td>
        </tr>
        """

    # Copyright notice
    copyright_html = f"""
    <tr>
        <td style="padding: 10px 0; text-align: center; font-size: 12px; color: {props.text_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            © {props.company_name}, the company behind Rext AI. All rights reserved.
        </td>
    </tr>
    """

    return f"""
    <!-- Footer -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top: 40px; border-top: {props.border_top};">
        {links_html}
        {address_html}
        {unsubscribe_html}
        {copyright_html}
    </table>
    """


def simple_footer() -> str:
    """Render a simple footer with just copyright."""
    return footer(FooterProps())


def standard_footer(
    company_name: str = "Revnix LLC",
    company_address: Optional[str] = None,
    unsubscribe_url: Optional[str] = None,
) -> str:
    """Render a standard footer with common links."""
    default_links = [
        FooterLink(text="Help", url="https://rext.ai/help"),
        FooterLink(text="Privacy policy", url="https://rext.ai/privacy-policy"),
        FooterLink(text="Terms", url="https://rext.ai/terms-and-conditions"),
    ]

    return footer(
        FooterProps(
            company_name=company_name,
            company_address=company_address,
            links=default_links,
            unsubscribe_url=unsubscribe_url,
        )
    )
