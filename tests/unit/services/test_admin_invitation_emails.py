"""The platform admin invitation's email: what it holds, and what happens when it can't
be sent (revnix/rext-control#915)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.services.admin_invitation_emails as emails
from emails.templates.auth.admin_invitation import render_admin_invitation_email
from src.api.middleware.exceptions import RextExternalServiceException

URL = "https://app.example/accept-admin-invitation?token=abc123"


def _invitation(**fields):
    return SimpleNamespace(
        **{
            "id": uuid4(),
            "email": "invited@example.com",
            "admin_role": "admin",
            "invitation_token": "tok_" + uuid4().hex,
            "message": None,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "invited_by": SimpleNamespace(display_name="Ada Admin", full_name="Ada A. Admin"),
            **fields,
        }
    )


@pytest.mark.parametrize(
    ("role", "label"), [("super_admin", "Super admin"), ("admin", "Admin"), ("support", "Support")]
)
def test_the_email_names_the_role_the_inviter_and_the_link(role, label):
    html = render_admin_invitation_email("Ada Admin", role, URL, expiry_days=7)

    assert label in html and "Ada Admin" in html
    assert f'href="{URL}"' in html
    assert "expires in" in html and "7 days" in html and "works once" in html


def test_what_people_typed_goes_into_the_email_as_text():
    html = render_admin_invitation_email(
        '<a href="https://evil.example">Ada</a>',
        "admin",
        URL,
        message='Welcome <script>alert(1)</script> & "hello"',
    )

    assert "<script>" not in html and '<a href="https://evil.example">' not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;hello&quot;" in html
    assert "&lt;a href=&quot;https://evil.example&quot;&gt;Ada&lt;/a&gt;" in html


def test_an_inviter_who_is_gone_and_a_one_day_invitation_still_read_right():
    html = render_admin_invitation_email(None, "support", URL, expiry_days=1)

    assert "A Rext AI super admin" in html and "1 day</strong>" in html


def test_a_person_is_named_as_they_chose_to_be_called():
    assert emails.person_name(SimpleNamespace(display_name="Ada", full_name="Ada Admin")) == "Ada"
    assert emails.person_name(SimpleNamespace(display_name=None, full_name="Ada Admin")) == (
        "Ada Admin"
    )
    assert emails.person_name(SimpleNamespace(display_name="", full_name=None)) is None
    assert emails.person_name(None) is None


def test_the_link_is_the_dashboards_accept_page_with_the_token(monkeypatch):
    monkeypatch.setattr(
        emails, "get_settings", lambda: SimpleNamespace(FRONTEND_URL="https://app.example/")
    )

    assert emails.accept_url("tok123") == "https://app.example/accept-admin-invitation?token=tok123"


@pytest.fixture
def service(monkeypatch):
    """The email service's stand-in: what it is asked to send, and how the send ends."""
    state = SimpleNamespace(sent=[], status="sent", raises=None)

    class _Emails:
        def __init__(self, _db):
            pass

        async def send_email(self, **email):
            if state.raises:
                raise state.raises
            state.sent.append(email)
            return SimpleNamespace(status=state.status)

    monkeypatch.setattr(emails, "EmailService", _Emails)
    monkeypatch.setattr(
        emails, "get_settings", lambda: SimpleNamespace(FRONTEND_URL="https://app.example")
    )
    return state


@pytest.mark.asyncio
async def test_the_invitation_goes_to_the_invited_address_with_its_own_link(service):
    invitation = _invitation(message="See you Monday.")

    await emails.send_admin_invitation_email(None, invitation)

    (email,) = service.sent
    assert email["to"] == "invited@example.com"
    assert email["template_type"] == "admin_invitation" and email["auto_commit"] is False
    assert f"?token={invitation.invitation_token}" in email["html"]
    assert "Ada Admin" in email["html"] and "See you Monday." in email["html"]
    assert "Admin" in email["subject"] and "invited@example.com" not in email["subject"]


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["failed", "raises"])
async def test_an_email_that_cant_be_sent_stops_the_invitation(service, how, caplog):
    """A failed send is recorded by the email service without raising, and a switched-off
    or broken one raises: both end as one error the admin reads, so the route's
    transaction is rolled back and nothing is kept."""
    service.status = "failed" if how == "failed" else "sent"
    service.raises = Exception("Email sending is disabled") if how == "raises" else None
    invitation = _invitation()

    with caplog.at_level("INFO"), pytest.raises(RextExternalServiceException) as refused:
        await emails.send_admin_invitation_email(None, invitation)

    assert "couldn't be sent" in refused.value.message
    assert refused.value.status_code == 502
    assert invitation.email not in caplog.text and invitation.invitation_token not in caplog.text
