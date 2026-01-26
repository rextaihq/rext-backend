"""
Unit tests for AuthService.

Tests cover:
- register_user: User registration with role assignment
- login_user: Authentication with session tracking and account locking
- verify_email: Email verification token handling
- refresh_token: Token refresh with rotation
- logout_user: Token blacklisting and session deactivation
- initiate_password_reset: Password reset token generation
- complete_password_reset: Password reset completion
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.services.auth_service import AuthService
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.user_sessions import UserSession
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    RextAuthenticationException,
    ResourceNotFoundException
)


class TestAuthServiceRegisterUser:
    """Test register_user method"""

    @pytest.mark.asyncio
    async def test_register_user_success(self):
        """Should create user with default role and return verification token"""
        # Arrange
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing user
        mock_db.flush = Mock()

        # Mock default role
        default_role = Role(
            id=uuid4(),
            name="user",
            display_name="User",
            description="Default role",
            hierarchy_level=1,
            is_system_role=True
        )

        # Setup query chain for getting default role
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # First call: check existing user
            default_role  # Second call: get default role
        ]

        service = AuthService(mock_db)

        with patch('src.services.auth_service.hash_password', return_value="hashed_password"), \
             patch('src.services.auth_service.create_verification_token', return_value="verification_token_123"):

            # Act
            user, token = await service.register_user(
                email="test@example.com",
                username="testuser",
                password="password123",
                first_name="Test",
                last_name="User"
            )

        # Assert
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.password_hash == "hashed_password"
        assert token == "verification_token_123"

        # Verify user was added
        assert mock_db.add.call_count == 2  # User + UserRole
        assert mock_db.flush.call_count == 2

    @pytest.mark.asyncio
    async def test_register_user_duplicate_email(self):
        """Should raise DuplicateResourceException when email exists"""
        # Arrange
        existing_user = Users(
            id=uuid4(),
            email="existing@example.com",
            username="different_username",
            password_hash="hash"
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_user

        service = AuthService(mock_db)

        # Act & Assert
        with pytest.raises(DuplicateResourceException) as exc_info:
            await service.register_user(
                email="existing@example.com",
                username="newusername",
                password="password123",
                first_name="Test",
                last_name="User"
            )

        assert "email already exists" in exc_info.value.message.lower()
        assert exc_info.value.context["conflicting_field"] == "email"
        assert exc_info.value.context["conflicting_value"] == "existing@example.com"

    @pytest.mark.asyncio
    async def test_register_user_duplicate_username(self):
        """Should raise DuplicateResourceException when username exists"""
        # Arrange
        existing_user = Users(
            id=uuid4(),
            email="different@example.com",
            username="existinguser",
            password_hash="hash"
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_user

        service = AuthService(mock_db)

        # Act & Assert
        with pytest.raises(DuplicateResourceException) as exc_info:
            await service.register_user(
                email="new@example.com",
                username="existinguser",
                password="password123",
                first_name="Test",
                last_name="User"
            )

        assert "username already exists" in exc_info.value.message.lower()
        assert exc_info.value.context["conflicting_field"] == "username"
        assert exc_info.value.context["conflicting_value"] == "existinguser"


class TestAuthServiceLoginUser:
    """Test login_user method"""

    @pytest.mark.asyncio
    async def test_login_user_success(self):
        """Should authenticate user and create session with tokens"""
        # Arrange
        user_id = uuid4()
        db_user = Users(
            id=user_id,
            email="test@example.com",
            username="testuser",
            password_hash="hashed_password",
            failed_login_attempts=0,
            login_count=5,
            user_roles=[]
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user
        mock_db.query.return_value.join.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value.all.return_value = []
        mock_db.flush = Mock()

        service = AuthService(mock_db)

        device_info = {
            "device_name": "Chrome on MacOS",
            "device_type": "desktop",
            "user_agent": "Mozilla/5.0",
            "ip_address": "127.0.0.1"
        }

        with patch('src.services.auth_service.verify_password', return_value=True), \
             patch('src.services.auth_service.create_access_token', return_value="access_token_123"), \
             patch('src.services.auth_service.create_refresh_token', return_value="refresh_token_456"), \
             patch('src.services.auth_service.verify_token', return_value={"jti": "jti_123", "exp": 1234567890}):

            # Act
            user, tokens = await service.login_user(
                email="test@example.com",
                password="password123",
                device_info=device_info
            )

        # Assert
        assert user.id == user_id
        assert user.failed_login_attempts == 0
        assert user.login_count == 6
        assert user.last_login_at is not None

        assert tokens["access_token"] == "access_token_123"
        assert tokens["refresh_token"] == "refresh_token_456"
        assert tokens["token_type"] == "bearer"

        # Verify session created
        assert mock_db.add.call_count >= 1  # Session added
        mock_db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_login_user_invalid_email(self):
        """Should raise RextAuthenticationException when user not found"""
        # Arrange
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = AuthService(mock_db)

        # Act & Assert
        with pytest.raises(RextAuthenticationException) as exc_info:
            await service.login_user(
                email="nonexistent@example.com",
                password="password123",
                device_info={}
            )

        assert "Invalid email or password" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_login_user_invalid_password(self):
        """Should raise RextAuthenticationException and increment failed attempts"""
        # Arrange
        user_id = uuid4()
        db_user = Users(
            id=user_id,
            email="test@example.com",
            password_hash="hashed_password",
            failed_login_attempts=1
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user
        mock_db.flush = Mock()

        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_password', return_value=False):
            # Act & Assert
            with pytest.raises(RextAuthenticationException) as exc_info:
                await service.login_user(
                    email="test@example.com",
                    password="wrong_password",
                    device_info={}
                )

        assert "Invalid email or password" in exc_info.value.message
        assert db_user.failed_login_attempts == 2
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_user_account_locked_after_3_failures(self):
        """Should lock account for 1 hour after 3 failed attempts"""
        # Arrange
        user_id = uuid4()
        db_user = Users(
            id=user_id,
            email="test@example.com",
            password_hash="hashed_password",
            failed_login_attempts=2  # One more will trigger lock
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user
        mock_db.flush = Mock()

        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_password', return_value=False):
            # Act & Assert
            with pytest.raises(RextAuthenticationException):
                await service.login_user(
                    email="test@example.com",
                    password="wrong_password",
                    device_info={}
                )

        assert db_user.failed_login_attempts == 3
        assert db_user.locked_until is not None
        assert db_user.locked_until > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_login_user_account_already_locked(self):
        """Should raise RextAuthenticationException when account is locked"""
        # Arrange
        user_id = uuid4()
        db_user = Users(
            id=user_id,
            email="test@example.com",
            password_hash="hashed_password",
            failed_login_attempts=5,
            locked_until=datetime.utcnow() + timedelta(hours=1)
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user

        service = AuthService(mock_db)

        # Act & Assert
        with pytest.raises(RextAuthenticationException) as exc_info:
            await service.login_user(
                email="test@example.com",
                password="password123",
                device_info={}
            )

        assert "temporarily locked" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_login_user_resets_failed_attempts_on_success(self):
        """Should reset failed_login_attempts to 0 on successful login"""
        # Arrange
        user_id = uuid4()
        db_user = Users(
            id=user_id,
            email="test@example.com",
            username="testuser",
            password_hash="hashed_password",
            failed_login_attempts=2,  # Had previous failures
            login_count=0,
            user_roles=[]
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user
        mock_db.query.return_value.join.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value.all.return_value = []
        mock_db.flush = Mock()

        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_password', return_value=True), \
             patch('src.services.auth_service.create_access_token', return_value="token"), \
             patch('src.services.auth_service.create_refresh_token', return_value="refresh"), \
             patch('src.services.auth_service.verify_token', return_value={"jti": "jti", "exp": 123}):

            # Act
            user, tokens = await service.login_user(
                email="test@example.com",
                password="password123",
                device_info={}
            )

        # Assert
        assert user.failed_login_attempts == 0


class TestAuthServiceVerifyEmail:
    """Test verify_email method"""

    @pytest.mark.asyncio
    async def test_verify_email_success(self):
        """Should verify email and update user"""
        # Arrange
        user_id = str(uuid4())
        db_user = Users(
            id=user_id,
            email="test@example.com",
            email_verified=False,
            email_verified_at=None
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user
        mock_db.flush = Mock()

        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_token', return_value={"user_id": user_id}):
            # Act
            result = await service.verify_email("verification_token_123")

        # Assert
        assert result.email_verified is True
        assert result.email_verified_at is not None
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self):
        """Should raise RextAuthenticationException when token has no user_id"""
        # Arrange
        mock_db = Mock()
        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_token', return_value={}):
            # Act & Assert
            with pytest.raises(RextAuthenticationException) as exc_info:
                await service.verify_email("invalid_token")

        assert "Invalid token payload" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_verify_email_user_not_found(self):
        """Should raise ResourceNotFoundException when user doesn't exist"""
        # Arrange
        user_id = str(uuid4())
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_token', return_value={"user_id": user_id}):
            # Act & Assert
            with pytest.raises(ResourceNotFoundException):
                await service.verify_email("token_123")


class TestAuthServiceRefreshToken:
    """Test refresh_token method"""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self):
        """Should generate new token pair and blacklist old refresh token"""
        # Arrange
        user_id = str(uuid4())
        db_user = Users(
            id=user_id,
            username="testuser",
            email="test@example.com",
            status="active",
            user_roles=[]
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user
        mock_db.query.return_value.join.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value.all.return_value = []
        mock_db.add = Mock()
        mock_db.flush = Mock()

        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_refresh_token', return_value={"id": user_id, "jti": "old_jti", "exp": 1234567890}), \
             patch('src.services.auth_service.is_token_blacklisted', return_value=False), \
             patch('src.services.auth_service.create_access_token', return_value="new_access_token"), \
             patch('src.services.auth_service.create_refresh_token', return_value="new_refresh_token"):

            # Act
            tokens = await service.refresh_token("old_refresh_token")

        # Assert
        assert tokens["access_token"] == "new_access_token"
        assert tokens["refresh_token"] == "new_refresh_token"
        assert tokens["token_type"] == "bearer"

        # Verify old token blacklisted
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_token_blacklisted(self):
        """Should raise RextAuthenticationException when token is blacklisted"""
        # Arrange
        mock_db = Mock()
        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_refresh_token', return_value={"jti": "blacklisted_jti", "id": str(uuid4())}), \
             patch('src.services.auth_service.is_token_blacklisted', return_value=True):

            # Act & Assert
            with pytest.raises(RextAuthenticationException) as exc_info:
                await service.refresh_token("blacklisted_token")

        assert "revoked" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_refresh_token_user_inactive(self):
        """Should raise RextAuthenticationException when user is not active"""
        # Arrange
        user_id = str(uuid4())
        db_user = Users(
            id=user_id,
            status="inactive"
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user

        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_refresh_token', return_value={"id": user_id, "jti": "jti_123"}), \
             patch('src.services.auth_service.is_token_blacklisted', return_value=False):

            # Act & Assert
            with pytest.raises(RextAuthenticationException) as exc_info:
                await service.refresh_token("refresh_token")

        assert "not active" in exc_info.value.message.lower()


class TestAuthServiceLogoutUser:
    """Test logout_user method"""

    @pytest.mark.asyncio
    async def test_logout_user_success(self):
        """Should blacklist token and deactivate session"""
        # Arrange
        user_id = uuid4()
        jti = "jti_123"
        exp = 1234567890

        session = UserSession(
            id=uuid4(),
            user_id=user_id,
            jti=jti,
            is_active=True
        )

        mock_db = Mock()
        # Mock query chain for session lookup - filter() takes multiple args, not chained
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = session
        mock_db.query.return_value = mock_query

        mock_db.add = Mock()
        mock_db.flush = Mock()

        service = AuthService(mock_db)

        with patch('src.services.auth_service.is_token_blacklisted', return_value=False):
            # Act
            await service.logout_user(user_id, jti, exp)

        # Assert
        mock_db.add.assert_called_once()  # Blacklist entry added
        assert session.is_active is False
        assert session.revoked_at is not None
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_logout_user_no_jti(self):
        """Should raise RextAuthenticationException when JTI is missing"""
        # Arrange
        mock_db = Mock()
        service = AuthService(mock_db)

        # Act & Assert
        with pytest.raises(RextAuthenticationException) as exc_info:
            await service.logout_user(uuid4(), None, 123)

        assert "missing jti" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_logout_user_already_blacklisted(self):
        """Should return early if token already blacklisted"""
        # Arrange
        user_id = uuid4()
        jti = "already_blacklisted_jti"

        mock_db = Mock()
        service = AuthService(mock_db)

        with patch('src.services.auth_service.is_token_blacklisted', return_value=True):
            # Act
            await service.logout_user(user_id, jti, 123)

        # Assert
        mock_db.add.assert_not_called()
        mock_db.flush.assert_not_called()


class TestAuthServicePasswordReset:
    """Test password reset methods"""

    @pytest.mark.asyncio
    async def test_initiate_password_reset_success(self):
        """Should generate reset token for existing user"""
        # Arrange
        user_id = uuid4()
        db_user = Users(
            id=user_id,
            email="test@example.com"
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user

        service = AuthService(mock_db)

        with patch('src.services.auth_service.create_verification_token', return_value="reset_token_123"):
            # Act
            user, token = await service.initiate_password_reset("test@example.com")

        # Assert
        assert user.id == user_id
        assert token == "reset_token_123"

    @pytest.mark.asyncio
    async def test_initiate_password_reset_user_not_found(self):
        """Should raise ResourceNotFoundException when user doesn't exist"""
        # Arrange
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = AuthService(mock_db)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.initiate_password_reset("nonexistent@example.com")

    @pytest.mark.asyncio
    async def test_complete_password_reset_success(self):
        """Should update password using valid token"""
        # Arrange
        user_id = str(uuid4())
        db_user = Users(
            id=user_id,
            email="test@example.com",
            password_hash="old_hash"
        )

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = db_user
        mock_db.flush = Mock()

        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_token', return_value={"user_id": user_id}), \
             patch('src.services.auth_service.hash_password', return_value="new_hash"):

            # Act
            user = await service.complete_password_reset("reset_token", "new_password123")

        # Assert
        assert user.password_hash == "new_hash"
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_password_reset_invalid_token(self):
        """Should raise RextAuthenticationException when token invalid"""
        # Arrange
        mock_db = Mock()
        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_token', return_value={}):
            # Act & Assert
            with pytest.raises(RextAuthenticationException) as exc_info:
                await service.complete_password_reset("invalid_token", "new_password")

        assert "Invalid token payload" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_complete_password_reset_user_not_found(self):
        """Should raise ResourceNotFoundException when user doesn't exist"""
        # Arrange
        user_id = str(uuid4())
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = AuthService(mock_db)

        with patch('src.services.auth_service.verify_token', return_value={"user_id": user_id}):
            # Act & Assert
            with pytest.raises(ResourceNotFoundException):
                await service.complete_password_reset("token", "new_password")
