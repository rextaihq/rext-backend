"""
Unit tests for UserService.

Tests cover:
- get_user_by_id: Retrieval and 404 handling
- get_user_by_email: Email lookup
- update_profile: Partial profile updates
- change_password: Password change with validation
- deactivate_account: Account deactivation
- reactivate_account: Account reactivation
- update_last_login: Login tracking
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import pytest

from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
from src.services.user_service import UserService


@pytest.mark.unit
class TestUserServiceGetUserById:
    """Test get_user_by_id method"""

    async def test_get_user_by_id_success(self, db_session, setup_factories):
        """Should return user when ID exists"""
        # Arrange
        user = await setup_factories["user"].create()
        service = UserService(db_session)

        # Act
        result = await service.get_user_by_id(user.id)

        # Assert
        assert result.id == user.id
        assert result.email == user.email
        assert result.display_name == user.display_name

    async def test_get_user_by_id_not_found(self, db_session):
        """Should raise ResourceNotFoundException when user doesn't exist"""
        # Arrange
        service = UserService(db_session)
        non_existent_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException) as exc_info:
            await service.get_user_by_id(non_existent_id)

        assert "User" in exc_info.value.message
        assert str(non_existent_id) in exc_info.value.message


@pytest.mark.unit
class TestUserServiceGetUserByEmail:
    """Test get_user_by_email method"""

    async def test_get_user_by_email_found(self, db_session, setup_factories):
        """Should return user when email exists"""
        # Arrange
        user = await setup_factories["user"].create(email="found@example.com")
        service = UserService(db_session)

        # Act
        result = await service.get_user_by_email("found@example.com")

        # Assert
        assert result is not None
        assert result.id == user.id
        assert result.email == "found@example.com"

    async def test_get_user_by_email_not_found(self, db_session):
        """Should return None when email doesn't exist"""
        # Arrange
        service = UserService(db_session)

        # Act
        result = await service.get_user_by_email("notfound@example.com")

        # Assert
        assert result is None


@pytest.mark.unit
class TestUserServiceUpdateProfile:
    """Test update_profile method"""

    async def test_update_profile_first_name(self, db_session, setup_factories):
        """Should update only first_name when provided"""
        # Arrange
        user = await setup_factories["user"].create(display_name="Original Name")
        service = UserService(db_session)

        # Act
        result = await service.update_profile(user_id=user.id, full_name="John Doe")

        # Assert
        assert result.full_name == "John Doe"
        assert result.display_name == "Original Name"  # Unchanged

    async def test_update_profile_last_name(self, db_session, setup_factories):
        """Should update only last_name when provided"""
        # Arrange
        user = await setup_factories["user"].create()
        service = UserService(db_session)

        # Act
        result = await service.update_profile(user_id=user.id, full_name="Jane Doe")

        # Assert
        assert result.full_name == "Jane Doe"

    async def test_update_profile_display_name(self, db_session, setup_factories):
        """Should update display_name"""
        # Arrange
        user = await setup_factories["user"].create()
        service = UserService(db_session)

        # Act
        result = await service.update_profile(user_id=user.id, display_name="New Display Name")

        # Assert
        assert result.display_name == "New Display Name"

    async def test_update_profile_avatar_url(self, db_session, setup_factories):
        """Should update avatar_url"""
        # Arrange
        user = await setup_factories["user"].create()
        service = UserService(db_session)

        # Act
        result = await service.update_profile(
            user_id=user.id, avatar_url="https://example.com/avatar.jpg"
        )

        # Assert
        assert result.avatar_url == "https://example.com/avatar.jpg"

    async def test_update_profile_language(self, db_session, setup_factories):
        """Should update language preference"""
        # Arrange
        user = await setup_factories["user"].create()
        service = UserService(db_session)

        # Act
        result = await service.update_profile(user_id=user.id, language="es")

        # Assert
        assert result.language == "es"

    async def test_update_profile_timezone(self, db_session, setup_factories):
        """Should update timezone preference"""
        # Arrange
        user = await setup_factories["user"].create()
        service = UserService(db_session)

        # Act
        result = await service.update_profile(user_id=user.id, timezone="America/New_York")

        # Assert
        assert result.timezone == "America/New_York"

    async def test_update_profile_multiple_fields(self, db_session, setup_factories):
        """Should update multiple fields at once"""
        # Arrange
        user = await setup_factories["user"].create()
        service = UserService(db_session)

        # Act
        result = await service.update_profile(
            user_id=user.id,
            full_name="Jane Smith",
            display_name="Jane S.",
            language="fr",
            timezone="Europe/Paris",
        )

        # Assert
        assert result.full_name == "Jane Smith"
        assert result.display_name == "Jane S."
        assert result.language == "fr"
        assert result.timezone == "Europe/Paris"

    async def test_update_profile_updates_timestamp(self, db_session, setup_factories):
        """Should update updated_at timestamp"""
        # Arrange
        user = await setup_factories["user"].create()
        original_updated_at = user.updated_at
        service = UserService(db_session)

        # Act
        result = await service.update_profile(user_id=user.id, full_name="Updated")

        # Assert
        assert result.updated_at > original_updated_at

    async def test_update_profile_user_not_found(self, db_session):
        """Should raise ResourceNotFoundException when user doesn't exist"""
        # Arrange
        service = UserService(db_session)
        non_existent_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.update_profile(user_id=non_existent_id, full_name="Test")

    async def test_update_profile_no_fields_provided(self, db_session, setup_factories):
        """Should still update timestamp even if no fields changed"""
        # Arrange
        user = await setup_factories["user"].create()
        original_updated_at = user.updated_at
        service = UserService(db_session)

        # Act
        result = await service.update_profile(user_id=user.id)

        # Assert
        assert result.updated_at > original_updated_at


@pytest.mark.unit
class TestUserServiceChangePassword:
    """Test change_password method"""

    async def test_change_password_success(self, db_session, setup_factories):
        """Should successfully change password when current password is correct"""
        # Arrange
        current_password = "Oldpassword123"
        new_password = "Newpassword456!"  # the rule asks for a special character
        password_hash = bcrypt.hashpw(current_password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        user = await setup_factories["user"].create(password_hash=password_hash)
        service = UserService(db_session)

        # Act
        result = await service.change_password(
            user_id=user.id, current_password=current_password, new_password=new_password
        )

        # Assert
        assert bcrypt.checkpw(new_password.encode("utf-8"), result.password_hash.encode("utf-8"))
        assert result.password_changed_at is not None
        assert result.updated_at is not None

    async def test_change_password_wrong_current_password(self, db_session, setup_factories):
        """Should raise RextValidationException when current password is incorrect"""
        # Arrange
        correct_password = "Correctpassword1"
        password_hash = bcrypt.hashpw(correct_password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        user = await setup_factories["user"].create(password_hash=password_hash)
        service = UserService(db_session)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.change_password(
                user_id=user.id, current_password="Wrongpassword1", new_password="Newpassword123"
            )

        assert "Current password is incorrect" in exc_info.value.message
        assert any(d.get("field") == "current_password" for d in exc_info.value.details)

    async def test_change_password_same_as_current(self, db_session, setup_factories):
        """Should raise RextValidationException when new password is same as current"""
        # Arrange
        password = "Samepassword123"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        user = await setup_factories["user"].create(password_hash=password_hash)
        service = UserService(db_session)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.change_password(
                user_id=user.id, current_password=password, new_password=password
            )

        assert "must be different" in exc_info.value.message
        assert any(d.get("field") == "new_password" for d in exc_info.value.details)

    async def test_change_password_updates_password_changed_at(self, db_session, setup_factories):
        """Should update password_changed_at timestamp"""
        # Arrange
        current_password = "Oldpassword1"
        password_hash = bcrypt.hashpw(current_password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        user = await setup_factories["user"].create(
            password_hash=password_hash, password_changed_at=None
        )
        service = UserService(db_session)

        # Act
        result = await service.change_password(
            user_id=user.id, current_password=current_password, new_password="Newpassword123!"
        )

        # Assert
        assert result.password_changed_at is not None

    async def test_change_password_user_not_found(self, db_session):
        """Should raise ResourceNotFoundException when user doesn't exist"""
        # Arrange
        service = UserService(db_session)
        non_existent_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.change_password(
                user_id=non_existent_id, current_password="any", new_password="new"
            )


@pytest.mark.unit
class TestUserServiceDeactivateAccount:
    """Test deactivate_account method"""

    async def test_deactivate_account_success(self, db_session, setup_factories):
        """Should successfully deactivate active account"""
        # Arrange
        user = await setup_factories["user"].create(status="active", deactivated_at=None)
        service = UserService(db_session)

        # Act
        result = await service.deactivate_account(user.id)

        # Assert
        assert result.status == "inactive"
        assert result.deactivated_at is not None

    async def test_deactivate_account_already_inactive(self, db_session, setup_factories):
        """Should still update deactivated_at even if already inactive"""
        # Arrange
        user = await setup_factories["user"].create(
            status="inactive", deactivated_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        original_deactivated_at = user.deactivated_at
        service = UserService(db_session)

        # Act
        result = await service.deactivate_account(user.id)

        # Assert
        assert result.status == "inactive"
        assert result.deactivated_at > original_deactivated_at

    async def test_deactivate_account_updates_timestamp(self, db_session, setup_factories):
        """Should update updated_at timestamp"""
        # Arrange
        user = await setup_factories["user"].create()
        original_updated_at = user.updated_at
        service = UserService(db_session)

        # Act
        result = await service.deactivate_account(user.id)

        # Assert
        assert result.updated_at > original_updated_at

    async def test_deactivate_account_user_not_found(self, db_session):
        """Should raise ResourceNotFoundException when user doesn't exist"""
        # Arrange
        service = UserService(db_session)
        non_existent_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.deactivate_account(non_existent_id)


@pytest.mark.unit
class TestUserServiceReactivateAccount:
    """Test reactivate_account method"""

    async def test_reactivate_account_success(self, db_session, setup_factories):
        """Should successfully reactivate inactive account"""
        # Arrange
        user = await setup_factories["user"].create(
            status="inactive", deactivated_at=datetime.now(timezone.utc)
        )
        service = UserService(db_session)

        # Act
        result = await service.reactivate_account(user.id)

        # Assert
        assert result.status == "active"
        assert result.deactivated_at is None

    async def test_reactivate_account_already_active(self, db_session, setup_factories):
        """Should work even if account is already active"""
        # Arrange
        user = await setup_factories["user"].create(status="active", deactivated_at=None)
        service = UserService(db_session)

        # Act
        result = await service.reactivate_account(user.id)

        # Assert
        assert result.status == "active"
        assert result.deactivated_at is None

    async def test_reactivate_account_updates_timestamp(self, db_session, setup_factories):
        """Should update updated_at timestamp"""
        # Arrange
        user = await setup_factories["user"].create(status="inactive")
        original_updated_at = user.updated_at
        service = UserService(db_session)

        # Act
        result = await service.reactivate_account(user.id)

        # Assert
        assert result.updated_at > original_updated_at

    async def test_reactivate_account_user_not_found(self, db_session):
        """Should raise ResourceNotFoundException when user doesn't exist"""
        # Arrange
        service = UserService(db_session)
        non_existent_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.reactivate_account(non_existent_id)


@pytest.mark.unit
class TestUserServiceUpdateLastLogin:
    """Test update_last_login method"""

    @pytest.fixture(autouse=True)
    def commit_as_flush(self, db_session, monkeypatch):
        """update_last_login commits; inside the test's rolled-back transaction the
        commit becomes a flush, so its writes stay there."""
        monkeypatch.setattr(db_session, "commit", db_session.flush)

    async def test_update_last_login_success(self, db_session, setup_factories):
        """Should update last_login_at and increment login_count"""
        # Arrange
        user = await setup_factories["user"].create(last_login_at=None, login_count=0)
        service = UserService(db_session)

        # Act
        await service.update_last_login(user.id)
        await db_session.flush()
        await db_session.refresh(user)

        # Assert
        assert user.last_login_at is not None
        assert user.login_count == 1

    async def test_update_last_login_increments_count(self, db_session, setup_factories):
        """Should increment login_count on each call"""
        # Arrange
        user = await setup_factories["user"].create(login_count=5)
        service = UserService(db_session)

        # Act
        await service.update_last_login(user.id)
        await db_session.flush()
        await db_session.refresh(user)

        # Assert
        assert user.login_count == 6

    async def test_update_last_login_resets_failed_attempts(self, db_session, setup_factories):
        """Should reset failed_login_attempts to 0"""
        # Arrange
        user = await setup_factories["user"].create(failed_login_attempts=3)
        service = UserService(db_session)

        # Act
        await service.update_last_login(user.id)
        await db_session.flush()
        await db_session.refresh(user)

        # Assert
        assert user.failed_login_attempts == 0

    async def test_update_last_login_handles_none_count(self, db_session, setup_factories):
        """Should handle None login_count by setting to 1"""
        # Arrange
        user = await setup_factories["user"].create(login_count=None)
        service = UserService(db_session)

        # Act
        await service.update_last_login(user.id)
        await db_session.flush()
        await db_session.refresh(user)

        # Assert
        assert user.login_count == 1

    async def test_update_last_login_user_not_found(self, db_session):
        """Should raise ResourceNotFoundException when user doesn't exist"""
        # Arrange
        service = UserService(db_session)
        non_existent_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.update_last_login(non_existent_id)


@pytest.mark.unit
class TestUserServiceChangeUserStatus:
    """Test change_user_status method"""

    async def test_change_user_status_success(self, db_session, setup_factories):
        """Should successfully change status and return old status"""
        # Arrange
        user = await setup_factories["user"].create(status="active")
        service = UserService(db_session)
        new_status = "suspended"

        # Act
        updated_user, old_status = await service.change_user_status(user.id, new_status)

        # Assert
        assert old_status == "active"
        assert updated_user.status == new_status
        assert updated_user.updated_at is not None

    async def test_change_user_status_invalid(self, db_session, setup_factories):
        """Should raise RextValidationException for invalid status"""
        # Arrange
        user = await setup_factories["user"].create()
        service = UserService(db_session)

        # Act & Assert
        with pytest.raises(RextValidationException) as exc_info:
            await service.change_user_status(user.id, "invalid_status")

        assert "Invalid status" in str(exc_info.value)

    async def test_change_user_status_not_found(self, db_session):
        """Should raise ResourceNotFoundException when user not found"""
        # Arrange
        service = UserService(db_session)
        non_existent_id = uuid4()

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.change_user_status(non_existent_id, "suspended")
