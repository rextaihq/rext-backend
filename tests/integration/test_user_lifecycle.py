"""
Integration tests for user deletion, recovery, and permanent purge lifecycle.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.api.middleware.exceptions import RextValidationException
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.user_models.users import Users
from src.services.user_service import UserService
from src.utils.account_cleanup import permanent_purge_deleted_accounts


class TestUserLifecycle:
    """Test user soft-deletion, recovery, and purge flows"""

    @pytest.fixture
    async def sample_user(self, db_session):
        """Creates a dummy active user for testing."""
        user = Users(
            email=f"test_lifecycle_{uuid.uuid4()}@example.com",
            full_name="Lifecycle Test User",
            password_hash="fake_hash",
            status="active",
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)
        return user

    @pytest.mark.asyncio
    async def test_soft_delete_flow(self, db_session, sample_user):
        """Test that delete_user soft-deletes and maintains the record."""
        service = UserService(db_session)
        user_id = sample_user.id

        # Add a dummy session to test cascade cleanup/invalidation
        # UserSession uses `jti` (JWT ID), not `session_id`
        session = UserSession(
            user_id=user_id,
            jti=str(uuid.uuid4()),
            ip_address="127.0.0.1",
            is_active=True,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(session)
        await db_session.flush()

        # Perform soft delete
        deleted_user = await service.delete_user(user_id)

        # Verify user is soft-deleted
        assert deleted_user.status == "inactive"
        assert deleted_user.deleted_at is not None

        # Verify session is deactivated
        result = await db_session.execute(select(UserSession).where(UserSession.user_id == user_id))
        db_session_record = result.scalars().first()
        assert db_session_record is None

    @pytest.mark.asyncio
    async def test_account_recovery_within_retention(self, db_session, sample_user):
        """Test requesting and completing recovery within retention period."""
        service = UserService(db_session)

        # Soft delete the user
        await service.delete_user(sample_user.id)

        # Request recovery
        user, token = await service.request_account_recovery(sample_user.email)
        assert token is not None

        # Verify recovery
        recovered_user = await service.verify_account_recovery(token)

        assert recovered_user.id == sample_user.id
        assert recovered_user.status == "active"
        assert recovered_user.deleted_at is None

    @pytest.mark.asyncio
    async def test_account_recovery_outside_retention(self, db_session, sample_user):
        """Test that recovery is rejected if retention period expired."""
        service = UserService(db_session)
        from src.api.config import get_settings

        # Soft delete the user
        await service.delete_user(sample_user.id)

        # Manually backdate the deleted_at to exceed retention
        retention_days = get_settings().USER_DELETION_RETENTION_DAYS
        expired_date = datetime.now(timezone.utc) - timedelta(days=retention_days + 1)

        sample_user.deleted_at = expired_date
        db_session.add(sample_user)
        await db_session.flush()

        # Request recovery should fail with RextValidationException
        with pytest.raises(RextValidationException) as excinfo:
            await service.request_account_recovery(sample_user.email)

        assert "recovery period has expired" in str(excinfo.value).lower()

    @pytest.mark.asyncio
    async def test_permanent_purge_anonymizes_data(self, db_session, sample_user):
        """Test the permanent purge job anonymizes user PII properly."""
        service = UserService(db_session)
        from src.api.config import get_settings

        user_id = sample_user.id

        # Soft delete the user
        await service.delete_user(user_id)

        # Backdate deleted_at to make eligible for purge
        retention_days = get_settings().USER_DELETION_RETENTION_DAYS
        sample_user.deleted_at = datetime.now(timezone.utc) - timedelta(days=retention_days + 2)
        db_session.add(sample_user)
        await db_session.flush()

        # Mock commit for the purge function to avoid breaking test transaction context
        original_commit = db_session.commit

        async def mock_commit():
            await db_session.flush()

        db_session.commit = mock_commit

        try:
            # Run purge
            purged_count = await permanent_purge_deleted_accounts(db_session)
            assert purged_count > 0
        finally:
            db_session.commit = original_commit

        # Verify anonymization
        result = await db_session.execute(select(Users).where(Users.id == user_id))
        purged_user = result.scalars().first()

        assert purged_user.status == "anonymized"
        assert purged_user.email.startswith("deleted_")
        assert purged_user.full_name == "Deleted User"
        assert purged_user.password_hash is None
