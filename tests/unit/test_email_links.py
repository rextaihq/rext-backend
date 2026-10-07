"""Every dashboard link an email builds opens a page that exists (D20, rext-control#541).

The emails build their dashboard links from frontend_url, and some renderers default to a written
https://app.rext.ai/… address. A path the dashboard doesn't serve (it had no /support, /help or
/feedback) opens nothing, so both kinds are read from the templates' source and checked against the
dashboard's routes. Support and help are rext.ai's pages (emails/site_links.py).
"""

import re
from pathlib import Path

from emails.site_links import SITE_CONTACT_URL, SITE_HELP_URL

TEMPLATES = Path(__file__).resolve().parents[2] / "emails" / "templates"

# The first segment of each dashboard path an email may link to (revnix/rext-admin's app/ routes;
# /billing, /subscription and /usage are redirects in its next.config.ts, and /unsubscribe a public
# page since D20).
DASHBOARD_ROUTES = {
    "account-recovery",
    "billing",
    "invitations",
    "login",
    "pricing",
    "reset-password",
    "settings",
    "subscription",
    "unsubscribe",
    "usage",
    "verify-email",
    "w",
}

DASHBOARD_PATH = re.compile(r"(?:\{frontend_url\}|https://app\.rext\.ai)/([A-Za-z0-9_\-]+)")


def _template_sources():
    return sorted(TEMPLATES.rglob("*.py"))


def test_every_dashboard_path_an_email_builds_is_a_dashboard_route():
    unknown = {}
    for source in _template_sources():
        for segment in DASHBOARD_PATH.findall(source.read_text()):
            if segment not in DASHBOARD_ROUTES:
                unknown.setdefault(segment, []).append(source.relative_to(TEMPLATES).as_posix())

    assert unknown == {}, f"dashboard paths with no page: {unknown}"


def test_support_and_help_link_to_the_site():
    sources = {s.relative_to(TEMPLATES).as_posix(): s.read_text() for s in _template_sources()}

    for name in (
        "auth/password_changed.py",
        "workspace/member_removed.py",
        "billing/trial_expired.py",
        "billing/subscription_cancelled.py",
        "content/content_generation_failed.py",
        "content/content_publish_failed.py",
    ):
        assert "SITE_CONTACT_URL" in sources[name], name
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


def test_the_publish_failed_email_links_the_contact_page():
    # Its sender passes no support address, so the renderer's default is what's sent.
    from emails.templates.content.content_publish_failed import render_content_publish_failed_email

    html = render_content_publish_failed_email(
        user_name="Mary",
        content_title="Spring menu",
        site_url="https://blog.example.test",
        error_message="The site didn't answer.",
        will_retry=False,
        attempt_number=3,
        max_retries=3,
        retry_url="https://app.example.test/w/acme/content/1",
        reschedule_url="https://app.example.test/w/acme/content/calendar",
    )

    assert SITE_CONTACT_URL in html
    assert "app.rext.ai/support" not in html
