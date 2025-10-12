"""
Button Component for Emails

Provides a styled, email-client-compatible button component.
Uses table-based structure for consistent rendering.
"""
from typing import Optional
from dataclasses import dataclass


@dataclass
class ButtonProps:
    """Props for email button component"""
    text: str
    url: str
    background_color: str = "#3b82f6"  # Blue-600
    text_color: str = "#ffffff"
    border_radius: str = "6px"
    padding: str = "12px 24px"
    font_size: str = "16px"
    font_weight: str = "600"
    align: str = "center"  # left, center, right


def button(props: ButtonProps) -> str:
    """
    Render a button component.

    Uses table structure and VML for Outlook compatibility.
    Inline styles for maximum email client support.

    Args:
        props: Button configuration properties

    Returns:
        HTML string for button component
    """
    return f"""
    <!-- Button -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
            <td align="{props.align}" style="padding: 20px 0;">
                <!--[if mso]>
                <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word"
                    href="{props.url}"
                    style="height:44px;v-text-anchor:middle;width:200px;"
                    arcsize="14%"
                    strokecolor="{props.background_color}"
                    fillcolor="{props.background_color}">
                    <w:anchorlock/>
                    <center style="color:{props.text_color};font-family:sans-serif;font-size:{props.font_size};font-weight:{props.font_weight};">
                        {props.text}
                    </center>
                </v:roundrect>
                <![endif]-->
                <!--[if !mso]><!-->
                <a href="{props.url}"
                   target="_blank"
                   style="display: inline-block;
                          background-color: {props.background_color};
                          color: {props.text_color};
                          font-size: {props.font_size};
                          font-weight: {props.font_weight};
                          text-decoration: none;
                          border-radius: {props.border_radius};
                          padding: {props.padding};
                          border: 1px solid {props.background_color};
                          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                    {props.text}
                </a>
                <!--<![endif]-->
            </td>
        </tr>
    </table>
    """


def primary_button(text: str, url: str) -> str:
    """Render a primary button (blue)."""
    return button(ButtonProps(
        text=text,
        url=url,
        background_color="#3b82f6",
        text_color="#ffffff"
    ))


def secondary_button(text: str, url: str) -> str:
    """Render a secondary button (gray)."""
    return button(ButtonProps(
        text=text,
        url=url,
        background_color="#6b7280",
        text_color="#ffffff"
    ))


def success_button(text: str, url: str) -> str:
    """Render a success button (green)."""
    return button(ButtonProps(
        text=text,
        url=url,
        background_color="#10b981",
        text_color="#ffffff"
    ))


def danger_button(text: str, url: str) -> str:
    """Render a danger button (red)."""
    return button(ButtonProps(
        text=text,
        url=url,
        background_color="#ef4444",
        text_color="#ffffff"
    ))
