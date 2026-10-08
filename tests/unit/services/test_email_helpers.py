"""
Unit Tests for Email Helper Functions

The helpers render an email from its template (a workspace's own template first, for workspace
emails), respect the recipient's preferences, and send it through EmailService now or in the
background. The templates and the preferences service are imported where they are used, so
they are patched at their own modules.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.email_helpers import _send_email_task, send_auth_email, send_workspace_email

PREFS = "src.services.email_preferences_service.EmailPreferencesService"
AUTH = "emails.templates.auth"
WORKSPACE = "emails.templates.workspace"


@pytest.fixture
def mock_db():
    """A session whose lookup of a workspace's own template finds none."""
    db = MagicMock()
    found = MagicMock()
    found.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=found)
    return db


@pytest.fixture
def sample_user_id():
    return uuid4()


@pytest.fixture
def sample_workspace_id():
    return uuid4()


@pytest.fixture
def email_service():
    """EmailService as the helpers construct it; its send_email is what they call."""
    with patch("src.services.email_helpers.EmailService") as service_class:
        instance = MagicMock()
        instance.send_email = AsyncMock()
        service_class.return_value = instance
        yield instance


@pytest.fixture
def prefs():
    """The recipient's preferences: every email allowed, with an unsubscribe token."""
    with patch(PREFS) as service_class:
        instance = MagicMock()
        instance.check_can_send = AsyncMock(return_value=True)
        instance.get_or_create_preferences = AsyncMock(
            return_value=SimpleNamespace(unsubscribe_token="unsub-token")
        )
        service_class.return_value = instance
        yield instance


class TestSendAuthEmail:
    """Tests for send_auth_email function."""

    @pytest.mark.asyncio
    async def test_send_verification_email_success(
        self, mock_db, sample_user_id, email_service, prefs
    ):
        with patch(f"{AUTH}.create_verification_email", return_value="<html>V</html>") as template:
            result = await send_auth_email(
                db=mock_db,
                email_type="verification",
                recipient_email="test@example.com",
                user_name="John Doe",
                user_id=sample_user_id,
                token="test-token-123",
                frontend_url="https://app.rext.com",
            )

        assert result is True
        template.assert_called_once_with(
            user_name="John Doe",
            verification_token="test-token-123",
            frontend_url="https://app.rext.com",
            unsubscribe_token="unsub-token",
        )
        sent = email_service.send_email.call_args.kwargs
        assert sent["to"] == "test@example.com"
        assert sent["subject"] == "Verify Your Email Address - Rext AI"
        assert sent["html"] == "<html>V</html>"
        assert sent["user_id"] == sample_user_id
        assert sent["template_type"] == "verification"

    @pytest.mark.asyncio
    async def test_send_password_reset_email_success(
        self, mock_db, sample_user_id, email_service, prefs
    ):
        with patch(
            f"{AUTH}.create_password_reset_email", return_value="<html>R</html>"
        ) as template:
            result = await send_auth_email(
                db=mock_db,
                email_type="password_reset",
                recipient_email="test@example.com",
                user_name="Jane Smith",
                user_id=sample_user_id,
                token="reset-token-456",
                frontend_url="https://app.rext.com",
            )

        assert result is True
        args = template.call_args.kwargs
        assert args["user_name"] == "Jane Smith"
        assert args["reset_token"] == "reset-token-456"
        assert args["user_email"] == "test@example.com"
        assert (
            email_service.send_email.call_args.kwargs["subject"] == "Reset Your Password - Rext AI"
        )

    @pytest.mark.asyncio
    async def test_send_welcome_email_success(self, mock_db, sample_user_id, email_service, prefs):
        with patch(f"{AUTH}.create_welcome_email", return_value="<html>W</html>") as template:
            result = await send_auth_email(
                db=mock_db,
                email_type="welcome",
                recipient_email="newuser@example.com",
                user_name="New User",
                user_id=sample_user_id,
                frontend_url="https://app.rext.com",
            )

        assert result is True
        template.assert_called_once_with(
            user_name="New User",
            frontend_url="https://app.rext.com",
            unsubscribe_token="unsub-token",
        )
        assert email_service.send_email.call_args.kwargs["subject"] == "Welcome to Rext AI!"

    @pytest.mark.asyncio
    async def test_send_auth_email_with_background_tasks(
        self, mock_db, sample_user_id, email_service, prefs
    ):
        """With background tasks the email is queued, not sent in the request."""
        background_tasks = MagicMock()
        with patch(f"{AUTH}.create_verification_email", return_value="<html>V</html>"):
            result = await send_auth_email(
                db=mock_db,
                email_type="verification",
                recipient_email="test@example.com",
                user_name="Test User",
                user_id=sample_user_id,
                token="token",
                frontend_url="https://app.rext.com",
                background_tasks=background_tasks,
            )

        assert result is True
        email_service.send_email.assert_not_called()
        (task,) = background_tasks.add_task.call_args.args
        queued = background_tasks.add_task.call_args.kwargs
        assert task is _send_email_task
        assert (queued["recipient_email"], queued["html"], queued["email_type"]) == (
            "test@example.com",
            "<html>V</html>",
            "verification",
        )

    @pytest.mark.asyncio
    async def test_send_auth_email_invalid_type(self, mock_db, sample_user_id, prefs):
        result = await send_auth_email(
            db=mock_db,
            email_type="invalid_type",
            recipient_email="test@example.com",
            user_name="Test User",
            user_id=sample_user_id,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_auth_email_service_failure(
        self, mock_db, sample_user_id, email_service, prefs
    ):
        """A failure to send is reported as False, never raised to the caller."""
        email_service.send_email.side_effect = Exception("Email service error")
        with patch(f"{AUTH}.create_verification_email", return_value="<html>V</html>"):
            result = await send_auth_email(
                db=mock_db,
                email_type="verification",
                recipient_email="test@example.com",
                user_name="Test User",
                user_id=sample_user_id,
                token="token",
                frontend_url="https://app.rext.com",
            )

        assert result is False


class TestSendWorkspaceEmail:
    """Tests for send_workspace_email function."""

    @pytest.mark.asyncio
    async def test_send_workspace_invitation_success(
        self, mock_db, sample_workspace_id, email_service
    ):
        """No user to check: the built-in template, given the workspace's id for its links."""
        with patch(
            f"{WORKSPACE}.create_workspace_invitation_email", return_value="<html>I</html>"
        ) as template:
            result = await send_workspace_email(
                db=mock_db,
                email_type="invitation",
                workspace_id=sample_workspace_id,
                recipient_email="invitee@example.com",
                workspace_name="Acme Inc",
                inviter_name="John Doe",
                role_name="Editor",
            )

        assert result is True
        context = template.call_args.kwargs
        assert context["workspace_id"] == str(sample_workspace_id)
        assert context["unsubscribe_token"] is None
        assert (context["workspace_name"], context["inviter_name"]) == ("Acme Inc", "John Doe")
        sent = email_service.send_email.call_args.kwargs
        assert sent["subject"] == "You're invited to join Acme Inc"
        assert (sent["to"], sent["workspace_id"]) == ("invitee@example.com", sample_workspace_id)

    @pytest.mark.asyncio
    async def test_send_workspace_email_with_preferences_check(
        self, mock_db, sample_workspace_id, sample_user_id, email_service, prefs
    ):
        """A recipient who turned the kind off gets nothing; nothing is rendered."""
        prefs.check_can_send.return_value = False
        with patch(f"{WORKSPACE}.create_workspace_invitation_email") as template:
            result = await send_workspace_email(
                db=mock_db,
                email_type="invitation",
                workspace_id=sample_workspace_id,
                recipient_email="test@example.com",
                user_id=sample_user_id,
                workspace_name="Test Workspace",
            )

        assert result is False
        prefs.check_can_send.assert_awaited_once_with(sample_user_id, "invitation")
        template.assert_not_called()
        email_service.send_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_workspace_email_preferences_allow(
        self, mock_db, sample_workspace_id, sample_user_id, email_service, prefs
    ):
        with patch(
            f"{WORKSPACE}.create_role_changed_email", return_value="<html>R</html>"
        ) as template:
            result = await send_workspace_email(
                db=mock_db,
                email_type="role_changed",
                workspace_id=sample_workspace_id,
                recipient_email="member@example.com",
                user_id=sample_user_id,
                workspace_name="Test Workspace",
            )

        assert result is True
        assert template.call_args.kwargs["unsubscribe_token"] == "unsub-token"
        sent = email_service.send_email.call_args.kwargs
        assert sent["subject"] == "Your role in Test Workspace has been updated"
        assert sent["user_id"] == sample_user_id

    @pytest.mark.asyncio
    async def test_send_workspace_email_comes_from_the_built_in_template_alone(
        self, mock_db, sample_workspace_id, email_service
    ):
        """Custom templates went with the old product (rext-control#369): a row that would
        once have been a workspace's own template is not looked for, and changes nothing."""
        own = SimpleNamespace(
            subject="Welcome to {{workspace_name}}", body="<p>Hi from {{workspace_name}}</p>"
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = own
        with patch(
            f"{WORKSPACE}.create_workspace_invitation_email", return_value="<p>built in</p>"
        ) as built_in:
            result = await send_workspace_email(
                db=mock_db,
                email_type="invitation",
                workspace_id=sample_workspace_id,
                recipient_email="test@example.com",
                workspace_name="Acme",
            )

        assert result is True
        built_in.assert_called_once()
        mock_db.execute.assert_not_called()
        sent = email_service.send_email.call_args.kwargs
        assert sent["subject"] == "You're invited to join Acme"
        assert sent["html"] == "<p>built in</p>"

    @pytest.mark.asyncio
    async def test_send_workspace_email_fallback_to_python_template(
        self, mock_db, sample_workspace_id, email_service
    ):
        """The workspace-template lookup failing falls back to the built-in template."""
        mock_db.execute.side_effect = Exception("DB template error")
        with patch(
            f"{WORKSPACE}.create_workspace_invitation_email", return_value="<html>F</html>"
        ) as built_in:
            result = await send_workspace_email(
                db=mock_db,
                email_type="invitation",
                workspace_id=sample_workspace_id,
                recipient_email="test@example.com",
                workspace_name="Test Workspace",
            )

        assert result is True
        built_in.assert_called_once()
        assert email_service.send_email.call_args.kwargs["html"] == "<html>F</html>"

    @pytest.mark.asyncio
    async def test_send_workspace_email_complete_failure(
        self, mock_db, sample_workspace_id, email_service
    ):
        """No template at all: reported as False, and nothing is sent."""
        mock_db.execute.side_effect = Exception("DB template error")
        with patch(
            f"{WORKSPACE}.create_workspace_invitation_email",
            side_effect=Exception("Python template error"),
        ):
            result = await send_workspace_email(
                db=mock_db,
                email_type="invitation",
                workspace_id=sample_workspace_id,
                recipient_email="test@example.com",
                workspace_name="Test Workspace",
            )

        assert result is False
        email_service.send_email.assert_not_called()
