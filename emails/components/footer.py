"""
Footer Component for Emails

Provides standard email footer with links and legal text.
"""
from typing import Optional, List, Dict
from dataclasses import dataclass, field


@dataclass
class FooterLink:
    """Link in footer"""
    text: str
    url: str


@dataclass
class FooterProps:
    """Props for email footer component"""
    company_name: str = "WREXT"
    company_address: Optional[str] = None
    links: List[FooterLink] = field(default_factory=list)
    unsubscribe_url: Optional[str] = None
    text_color: str = "#6b7280"
    link_color: str = "#3b82f6"
    border_top: str = "1px solid #e5e7eb"


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
            f'<a href="{link.url}" style="color: {props.link_color}; text-decoration: none;">{link.text}</a>'
            for link in props.links
        ]
        links_html = f"""
        <tr>
            <td style="padding: 10px 0; text-align: center; font-size: 14px; color: {props.text_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                {' • '.join(link_items)}
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
                <a href="{props.unsubscribe_url}" style="color: {props.link_color}; text-decoration: none;">Unsubscribe</a>
            </td>
        </tr>
        """

    # Copyright notice
    copyright_html = f"""
    <tr>
        <td style="padding: 10px 0; text-align: center; font-size: 12px; color: {props.text_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
            © {props.company_name}. All rights reserved.
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
    company_name: str = "WREXT",
    company_address: Optional[str] = None,
    unsubscribe_url: Optional[str] = None
) -> str:
    """Render a standard footer with common links."""
    default_links = [
        FooterLink(text="Help Center", url="https://help.wrext.com"),
        FooterLink(text="Privacy Policy", url="https://wrext.com/privacy"),
        FooterLink(text="Terms of Service", url="https://wrext.com/terms"),
    ]

    return footer(FooterProps(
        company_name=company_name,
        company_address=company_address,
        links=default_links,
        unsubscribe_url=unsubscribe_url
    ))
