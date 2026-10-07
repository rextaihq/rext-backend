"""
Button Component for Emails

Provides a styled, email-client-compatible button component.
Uses table-based structure for consistent rendering.
"""

from dataclasses import dataclass
from typing import Optional

from emails.palette import BORDER_STRONG, INK, LIME, OBSIDIAN, WHITE


@dataclass
class ButtonProps:
    """Props for email button component"""

    text: str
    url: str
    background_color: str = OBSIDIAN
    text_color: str = LIME
    border_color: Optional[str] = None  # defaults to the fill
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
    border_color = props.border_color or props.background_color
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
                    strokecolor="{border_color}"
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
                          border: 1px solid {border_color};
                          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                    {props.text}
                </a>
                <!--<![endif]-->
            </td>
        </tr>
    </table>
    """


def primary_button(text: str, url: str) -> str:
    """Render the primary button: lime text on obsidian, the emails' one button colour."""
    return button(ButtonProps(text=text, url=url))


def secondary_button(text: str, url: str) -> str:
    """Render a secondary button: ink text on white, outlined."""
    return button(
        ButtonProps(
            text=text, url=url, background_color=WHITE, text_color=INK, border_color=BORDER_STRONG
        )
    )


def success_button(text: str, url: str) -> str:
    """Render a success button (the primary button: the emails have one button colour)."""
    return primary_button(text, url)


def danger_button(text: str, url: str) -> str:
    """Render a danger button (the primary button: the emails have one button colour)."""
    return primary_button(text, url)
