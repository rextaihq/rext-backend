"""The emails use the app's scheme: obsidian and lime, the neutral greys, underlined links (B9c, rext-control#605).

The founder chose obsidian as the app's one accent and lime only as the text on it (rext-control#457,
2026-10-07). The emails' four blues and their gradient panels go; status colours stay where a status
means something. The templates are read from source, as test_email_links.py does, and a few are
rendered for what only the output shows.
"""

import re
from pathlib import Path

from emails import palette
from emails.components.button import danger_button, primary_button, success_button
from emails.templates.auth.verification import render_verification_email
from emails.templates.workspace.invitation import render_workspace_invitation_email
from emails.templates.workspace.role_changed import render_role_changed_email

EMAILS = Path(__file__).resolve().parents[2] / "emails"

GONE = {"#3b82f6", "#2563eb", "#3641f5", "#101828", "#667eea", "#764ba2", "#465fff"}

NEUTRAL = {
    palette.OBSIDIAN,
    palette.LIME,
    palette.INK,
    palette.BODY,
    palette.MUTED,
    palette.BORDER_STRONG,
    palette.LINE,
    palette.PAGE,
    palette.PANEL,
    palette.WHITE,
    "#525252",  # neutral-600, secondary text
}
STATUS = {
    # red: failures and an ending trial
    "#7f1d1d",
    "#991b1b",
    "#b91c1c",
    "#dc2626",
    "#ef4444",
    "#fca5a5",
    "#fecaca",
    "#fee2e2",
    "#fef2f2",
    # amber: warnings
    "#92400e",
    "#b45309",
    "#d97706",
    "#f59e0b",
    "#fbbf24",
    "#fcd34d",
    "#fde68a",
    "#fef3c7",
    "#fffbeb",
    # green: a success that means something (payment recovered, password changed, refund approved)
    "#065f46",
    "#166534",
    "#059669",
    "#22c55e",
    "#6ee7b7",
    "#86efac",
    "#a7f3d0",
    "#ecfdf5",
    "#f0fdf4",
}

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def _sources():
    return {p.relative_to(EMAILS).as_posix(): p.read_text() for p in sorted(EMAILS.rglob("*.py"))}


def test_no_blue_and_no_gradient_is_left():
    found = {}
    for name, text in _sources().items():
        hits = {c.lower() for c in HEX.findall(text)} & GONE
        if "linear-gradient" in text:
            hits.add("linear-gradient")
        if hits:
            found[name] = sorted(hits)

    assert found == {}


def test_every_colour_is_the_schemes_or_a_status():
    stray = {}
    for name, text in _sources().items():
        extra = {c.lower() for c in HEX.findall(text)} - NEUTRAL - STATUS
        if extra:
            stray[name] = sorted(extra)

    assert stray == {}


def test_links_are_underlined():
    # Obsidian is the body text's colour, so a link is told apart by its line. A link drawn as a
    # button carries a background instead; the button component's own link is a button.
    plain = {}
    for name, text in _sources().items():
        if name == "components/button.py":
            continue
        for tag in re.findall(r"<a\b[^>]*>", text, flags=re.S):
            style = re.search(r'style="([^"]*)"', tag)
            if style and "background-color" in style.group(1):
                continue
            if not style or "text-decoration: underline" not in re.sub(
                r":\s*", ": ", style.group(1)
            ):
                plain.setdefault(name, []).append(tag[:80])

    assert plain == {}


def test_every_button_is_lime_on_obsidian():
    for html in (
        primary_button("Verify", "https://app.rext.ai/verify-email?token=t"),
        success_button("Done", "https://app.rext.ai"),
        danger_button("Delete", "https://app.rext.ai"),
    ):
        assert f'fillcolor="{palette.OBSIDIAN}"' in html
        assert f"background-color: {palette.OBSIDIAN};" in html
        assert f"color: {palette.LIME};" in html


def test_lime_is_only_text_on_obsidian():
    # Lime on white is 1.2 : 1. Every style that sets lime text sits on the obsidian fill.
    rendered = [
        render_verification_email("Sam", "https://app.rext.ai/verify-email?token=t"),
        render_workspace_invitation_email(
            "Acme", "Ana", "https://app.rext.ai/invitations/accept?t=x"
        ),
        render_role_changed_email("Acme", "Sam", "Viewer", "Editor", "Ana", workspace_slug="acme"),
    ]
    for html in rendered:
        # Outlook's button (VML) sets the fill on its shape; test_every_button_is_lime_on_obsidian reads it.
        html = re.sub(r"<!--\[if mso\]>.*?<!\[endif\]-->", "", html, flags=re.S)
        styles = [s for s in re.findall(r'style="([^"]*)"', html) if palette.LIME in s]
        assert styles
        for style in styles:
            assert re.search(r"background-color:\s*" + palette.OBSIDIAN, style), style
