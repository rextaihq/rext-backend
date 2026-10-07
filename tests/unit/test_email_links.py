"""Every dashboard link an email builds opens a page that exists (D20, rext-control#541).

The emails build their dashboard links from frontend_url. A path the dashboard doesn't serve
(it had no /support or /help) opens nothing, so the paths are read from the templates' source and
checked against the dashboard's routes. Support and help are rext.ai's pages (emails/site_links.py).
"""

import re
from pathlib import Path

from emails.site_links import SITE_CONTACT_URL, SITE_HELP_URL

TEMPLATES = Path(__file__).resolve().parents[2] / "emails" / "templates"

# The first segment of each dashboard path an email may link to (revnix/rext-admin's app/ routes;
# /billing is a redirect in its next.config.ts, and /unsubscribe a public page since D20).
DASHBOARD_ROUTES = {
    "account-recovery",
    "billing",
    "invitations",
    "login",
    "reset-password",
    "settings",
    "unsubscribe",
    "verify-email",
    "w",
}

FRONTEND_PATH = re.compile(r"\{frontend_url\}/([A-Za-z0-9_\-]+)")


def _template_sources():
    return sorted(TEMPLATES.rglob("*.py"))


def test_every_dashboard_path_an_email_builds_is_a_dashboard_route():
    unknown = {}
    for source in _template_sources():
        for segment in FRONTEND_PATH.findall(source.read_text()):
            if segment not in DASHBOARD_ROUTES:
                unknown.setdefault(segment, []).append(source.relative_to(TEMPLATES).as_posix())

    assert unknown == {}, f"dashboard paths with no page: {unknown}"


def test_support_and_help_link_to_the_site():
    sources = {s.relative_to(TEMPLATES).as_posix(): s.read_text() for s in _template_sources()}

    assert "SITE_CONTACT_URL" in sources["auth/password_changed.py"]
    assert "SITE_CONTACT_URL" in sources["workspace/member_removed.py"]
    assert "SITE_HELP_URL" in sources["auth/welcome.py"]
    assert all("help.rext.ai" not in text for text in sources.values())
    assert SITE_CONTACT_URL == "https://rext.ai/contact"
    assert SITE_HELP_URL == "https://rext.ai/help"


def test_the_rendered_emails_carry_the_site_links():
    from emails.templates.auth.password_changed import create_password_changed_email
    from emails.templates.auth.welcome import create_welcome_email

    welcome = create_welcome_email(user_name="Mary", frontend_url="https://app.example.test")
    password = create_password_changed_email(
        user_name="Mary",
        changed_at="7 October 2026, 04:30 UTC",
        frontend_url="https://app.example.test",
    )

    assert SITE_HELP_URL in str(welcome)
    assert "https://app.example.test/help" not in str(welcome)
    assert SITE_CONTACT_URL in str(password)
    assert "https://app.example.test/support" not in str(password)
