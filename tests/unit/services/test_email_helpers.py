"""
Unit Tests for Email Helper Functions

Tests the email_helpers module which provides unified email sending interface.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4

from src.services.email_helpers import send_auth_email, send_workspace_email


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    return db


@pytest.fixture
def sample_user_id():
    """Sample user UUID."""
    return uuid4()


@pytest.fixture
def sample_workspace_id():
    """Sample workspace UUID."""
    return uuid4()


class TestSendAuthEmail:
    """Tests for send_auth_email function."""

    @pytest.mark.asyncio
    async def test_send_verification_email_success(self, mock_db, sample_user_id):
        """Test successful verification email sending."""
        with patch('src.services.email_helpers.EmailService') as mock_service, \
             patch('src.services.email_helpers.create_verification_email') as mock_template:

            # Setup mocks
            mock_template.return_value = "<html>Verification Email</html>"
            mock_email_service_instance = Mock()
            mock_email_service_instance.send_email = AsyncMock()
            mock_service.return_value = mock_email_service_instance

            # Call function
            result = await send_auth_email(
                db=mock_db,
                email_type="verification",
                recipient_email="test@example.com",
                user_name="John Doe",
                user_id=sample_user_id,
                token="test-token-123",
                frontend_url="https://app.wrext.com"
            )

            # Assertions
            assert result is True
            mock_template.assert_called_once_with(
                user_name="John Doe",
                verification_token="test-token-123",
                frontend_url="https://app.wrext.com"
            )
            mock_email_service_instance.send_email.assert_called_once()
            call_args = mock_email_service_instance.send_email.call_args[1]
            assert call_args['to'] == "test@example.com"
            assert call_args['subject'] == "Verify Your Email Address - WREXT"
            assert call_args['user_id'] == sample_user_id

    @pytest.mark.asyncio
    async def test_send_password_reset_email_success(self, mock_db, sample_user_id):
        """Test successful password reset email sending."""
        with patch('src.services.email_helpers.EmailService') as mock_service, \
             patch('src.services.email_helpers.create_password_reset_email') as mock_template:

            # Setup mocks
            mock_template.return_value = "<html>Password Reset Email</html>"
            mock_email_service_instance = Mock()
            mock_email_service_instance.send_email = AsyncMock()
            mock_service.return_value = mock_email_service_instance

            # Call function
            result = await send_auth_email(
                db=mock_db,
                email_type="password_reset",
                recipient_email="test@example.com",
                user_name="Jane Smith",
                user_id=sample_user_id,
                token="reset-token-456",
                frontend_url="https://app.wrext.com"
            )

            # Assertions
            assert result is True
            mock_template.assert_called_once()
            call_args = mock_template.call_args[1]
            assert call_args['user_name'] == "Jane Smith"
            assert call_args['reset_token'] == "reset-token-456"
            assert call_args['user_email'] == "test@example.com"

    @pytest.mark.asyncio
    async def test_send_welcome_email_success(self, mock_db, sample_user_id):
        """Test successful welcome email sending."""
        with patch('src.services.email_helpers.EmailService') as mock_service, \
             patch('src.services.email_helpers.create_welcome_email') as mock_template:

            # Setup mocks
            mock_template.return_value = "<html>Welcome Email</html>"
            mock_email_service_instance = Mock()
            mock_email_service_instance.send_email = AsyncMock()
            mock_service.return_value = mock_email_service_instance

            # Call function
            result = await send_auth_email(
                db=mock_db,
                email_type="welcome",
                recipient_email="newuser@example.com",
                user_name="New User",
                user_id=sample_user_id,
                frontend_url="https://app.wrext.com"
            )

            # Assertions
            assert result is True
            mock_template.assert_called_once_with(
                user_name="New User",
                frontend_url="https://app.wrext.com"
            )

    @pytest.mark.asyncio
    async def test_send_auth_email_with_background_tasks(self, mock_db, sample_user_id):
        """Test email sending with background tasks."""
        with patch('src.services.email_helpers.create_verification_email') as mock_template:

            mock_template.return_value = "<html>Email</html>"
            mock_background_tasks = Mock()

            # Call function with background_tasks
            result = await send_auth_email(
                db=mock_db,
                email_type="verification",
                recipient_email="test@example.com",
                user_name="Test User",
                user_id=sample_user_id,
                token="token",
                frontend_url="https://app.wrext.com",
                background_tasks=mock_background_tasks
            )

            # Assertions
            assert result is True
            mock_background_tasks.add_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_auth_email_invalid_type(self, mock_db, sample_user_id):
        """Test error handling for invalid email type."""
        result = await send_auth_email(
            db=mock_db,
            email_type="invalid_type",  # Invalid type
            recipient_email="test@example.com",
            user_name="Test User",
            user_id=sample_user_id
        )

        # Should return False on error
        assert result is False

    @pytest.mark.asyncio
    async def test_send_auth_email_service_failure(self, mock_db, sample_user_id):
        """Test error handling when EmailService fails."""
        with patch('src.services.email_helpers.EmailService') as mock_service, \
             patch('src.services.email_helpers.create_verification_email') as mock_template:

            # Setup mocks to simulate failure
            mock_template.return_value = "<html>Email</html>"
            mock_email_service_instance = Mock()
            mock_email_service_instance.send_email = AsyncMock(side_effect=Exception("Email service error"))
            mock_service.return_value = mock_email_service_instance

            # Call function
            result = await send_auth_email(
                db=mock_db,
                email_type="verification",
                recipient_email="test@example.com",
                user_name="Test User",
                user_id=sample_user_id,
                token="token",
                frontend_url="https://app.wrext.com"
            )

            # Should return False on error
            assert result is False


class TestSendWorkspaceEmail:
    """Tests for send_workspace_email function."""

    @pytest.mark.asyncio
    async def test_send_workspace_invitation_success(self, mock_db, sample_workspace_id):
        """Test successful workspace invitation email."""
        with patch('src.services.email_helpers.EmailService') as mock_service, \
             patch('src.services.email_helpers.render_workspace_email') as mock_render:

            # Setup mocks
            mock_render.return_value = {
                "subject": "Join Our Workspace",
                "html": "<html>Invitation Email</html>"
            }
            mock_email_service_instance = Mock()
            mock_email_service_instance.send_email = AsyncMock()
            mock_service.return_value = mock_email_service_instance

            # Call function
            result = await send_workspace_email(
                db=mock_db,
                email_type="invitation",
                workspace_id=sample_workspace_id,
                recipient_email="invitee@example.com",
                workspace_name="Acme Inc",
                inviter_name="John Doe",
                role_name="Editor"
            )

            # Assertions
            assert result is True
            mock_render.assert_called_once()
            mock_email_service_instance.send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_workspace_email_with_preferences_check(self, mock_db, sample_workspace_id, sample_user_id):
        """Test that email preferences are checked before sending."""
        with patch('src.services.email_helpers.EmailPreferencesService') as mock_prefs_service, \
             patch('src.services.email_helpers.render_workspace_email') as mock_render:

            # Setup mocks - preferences block email
            mock_prefs_instance = Mock()
            mock_prefs_instance.check_can_send = AsyncMock(return_value=False)
            mock_prefs_service.return_value = mock_prefs_instance

            # Call function with user_id (triggers preferences check)
            result = await send_workspace_email(
                db=mock_db,
                email_type="invitation",
                workspace_id=sample_workspace_id,
                recipient_email="test@example.com",
                user_id=sample_user_id,
                workspace_name="Test Workspace"
            )

            # Assertions
            assert result is False  # Email should be blocked
            mock_prefs_instance.check_can_send.assert_called_once_with(
                sample_user_id,
                "invitation",
                mock_db
            )
            mock_render.assert_not_called()  # Email should not be rendered

    @pytest.mark.asyncio
    async def test_send_workspace_email_preferences_allow(self, mock_db, sample_workspace_id, sample_user_id):
        """Test email sending when preferences allow."""
        with patch('src.services.email_helpers.EmailPreferencesService') as mock_prefs_service, \
             patch('src.services.email_helpers.EmailService') as mock_service, \
             patch('src.services.email_helpers.render_workspace_email') as mock_render:

            # Setup mocks - preferences allow email
            mock_prefs_instance = Mock()
            mock_prefs_instance.check_can_send = AsyncMock(return_value=True)
            mock_prefs_service.return_value = mock_prefs_instance

            mock_render.return_value = {
                "subject": "Test Email",
                "html": "<html>Test</html>"
            }
            mock_email_service_instance = Mock()
            mock_email_service_instance.send_email = AsyncMock()
            mock_service.return_value = mock_email_service_instance

            # Call function
            result = await send_workspace_email(
                db=mock_db,
                email_type="role_changed",
                workspace_id=sample_workspace_id,
                recipient_email="member@example.com",
                user_id=sample_user_id,
                workspace_name="Test Workspace"
            )

            # Assertions
            assert result is True
            mock_prefs_instance.check_can_send.assert_called_once()
            mock_render.assert_called_once()
            mock_email_service_instance.send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_workspace_email_fallback_to_python_template(self, mock_db, sample_workspace_id):
        """Test fallback to Python template when DB template fails."""
        with patch('src.services.email_helpers.EmailService') as mock_service, \
             patch('src.services.email_helpers.render_workspace_email') as mock_render, \
             patch('src.services.email_helpers.create_workspace_invitation_email') as mock_python_template:

            # Setup mocks - DB template fails, Python template succeeds
            mock_render.side_effect = Exception("DB template error")
            mock_python_template.return_value = "<html>Fallback Email</html>"

            mock_email_service_instance = Mock()
            mock_email_service_instance.send_email = AsyncMock()
            mock_service.return_value = mock_email_service_instance

            # Call function
            result = await send_workspace_email(
                db=mock_db,
                email_type="invitation",
                workspace_id=sample_workspace_id,
                recipient_email="test@example.com",
                workspace_name="Test Workspace"
            )

            # Assertions
            assert result is True
            mock_render.assert_called_once()  # Tried DB template first
            mock_python_template.assert_called_once()  # Fell back to Python template
            mock_email_service_instance.send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_workspace_email_complete_failure(self, mock_db, sample_workspace_id):
        """Test error handling when both DB and Python templates fail."""
        with patch('src.services.email_helpers.render_workspace_email') as mock_render, \
             patch('src.services.email_helpers.create_workspace_invitation_email') as mock_python_template:

            # Setup mocks - both fail
            mock_render.side_effect = Exception("DB template error")
            mock_python_template.side_effect = Exception("Python template error")

            # Call function
            result = await send_workspace_email(
                db=mock_db,
                email_type="invitation",
                workspace_id=sample_workspace_id,
                recipient_email="test@example.com",
                workspace_name="Test Workspace"
            )

            # Should return False on complete failure
            assert result is False


# Test coverage report
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src.services.email_helpers", "--cov-report=term-missing"])
