"""
Unit tests for invitation utilities.

Tests invitation helper functions including expiry checking and cleanup.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.models.user_models.invitations import UserInvitations
from src.utils.invitation_utils import (
    cleanup_expired_invitations,
    get_invitation_with_details,
    is_invitation_expired,
)


class TestIsInvitationExpired:
    """Tests for is_invitation_expired function."""

    def test_is_invitation_expired_no_expiry_date(self):
        """Test that invitation without expiry date is not expired."""
        invitation = MagicMock(spec=UserInvitations)
        invitation.expires_at = None

        result = is_invitation_expired(invitation)

        assert result is False

    def test_is_invitation_expired_future_date_aware(self):
        """Test that invitation with future expiry is not expired (timezone aware)."""
        invitation = MagicMock(spec=UserInvitations)
        invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        result = is_invitation_expired(invitation)

        assert result is False

    def test_is_invitation_expired_past_date_aware(self):
        """Test that invitation with past expiry is expired (timezone aware)."""
        invitation = MagicMock(spec=UserInvitations)
        invitation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        result = is_invitation_expired(invitation)

        assert result is True

    def test_is_invitation_expired_future_date_naive(self):
        """Test that invitation with future expiry is not expired (naive datetime)."""
        invitation = MagicMock(spec=UserInvitations)
        # Create naive datetime (no timezone)
        invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        result = is_invitation_expired(invitation)

        assert result is False

    def test_is_invitation_expired_past_date_naive(self):
        """Test that invitation with past expiry is expired (naive datetime)."""
        invitation = MagicMock(spec=UserInvitations)
        # Create naive datetime (no timezone)
        invitation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        result = is_invitation_expired(invitation)

        assert result is True

    def test_is_invitation_expired_exactly_now(self):
        """Test edge case where expiry is approximately now."""
        invitation = MagicMock(spec=UserInvitations)
        # Set expiry to 1 second ago
        invitation.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        result = is_invitation_expired(invitation)

        assert result is True


class TestCleanupExpiredInvitations:
    """Tests for cleanup_expired_invitations function."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_invitations_none_expired(self):
        """Test cleanup when no invitations are expired."""
        mock_db = AsyncMock()

        # Mock the execute result to return no expired invitations
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await cleanup_expired_invitations(mock_db)

        assert result == 0
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_expired_invitations_multiple_expired(self):
        """Test cleanup when multiple invitations are expired."""
        mock_db = AsyncMock()

        # Create mock expired invitations
        inv1 = MagicMock()
        inv1.status = "pending"
        inv2 = MagicMock()
        inv2.status = "pending"
        inv3 = MagicMock()
        inv3.status = "pending"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv1, inv2, inv3]
        mock_db.execute.return_value = mock_result

        result = await cleanup_expired_invitations(mock_db)

        assert result == 3
        assert inv1.status == "expired"
        assert inv2.status == "expired"
        assert inv3.status == "expired"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_expired_invitations_single_expired(self):
        """Test cleanup with single expired invitation."""
        mock_db = AsyncMock()

        inv = MagicMock()
        inv.status = "pending"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute.return_value = mock_result

        result = await cleanup_expired_invitations(mock_db)

        assert result == 1
        assert inv.status == "expired"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.utils.invitation_utils.logger")
    async def test_cleanup_expired_invitations_logs_when_cleaned(self, mock_logger):
        """Test that cleanup logs when invitations are marked expired."""
        mock_db = AsyncMock()

        inv = MagicMock()
        inv.status = "pending"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inv]
        mock_db.execute.return_value = mock_result

        await cleanup_expired_invitations(mock_db)

        mock_logger.info.assert_called_once()
        assert "Marked 1 expired invitations" in str(mock_logger.info.call_args)

    @pytest.mark.asyncio
    @patch("src.utils.invitation_utils.logger")
    async def test_cleanup_expired_invitations_no_log_when_none(self, mock_logger):
        """Test that cleanup logs info message when no invitations expired."""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        await cleanup_expired_invitations(mock_db)

        # Implementation logs "No expired invitations found" even when count == 0
        mock_logger.info.assert_called_once()
        assert "No expired invitations found" in str(mock_logger.info.call_args)

    @pytest.mark.asyncio
    @patch("src.utils.invitation_utils.logger")
    async def test_cleanup_expired_invitations_handles_exception(self, mock_logger):
        """Test that cleanup handles exceptions gracefully."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Database error")

        result = await cleanup_expired_invitations(mock_db)

        assert result == 0
        mock_db.rollback.assert_called_once()
        mock_logger.error.assert_called_once()
        assert "Error cleaning up" in str(mock_logger.error.call_args)


class TestGetInvitationWithDetails:
    """Tests for get_invitation_with_details function."""

    @pytest.mark.asyncio
    async def test_get_invitation_with_details_not_found(self):
        """Test getting details for non-existent invitation."""
        mock_db = AsyncMock()

        # 1st execute call: invitation lookup returns None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_invitation_with_details(mock_db, str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_get_invitation_with_details_complete(self):
        """Test getting complete invitation details."""
        mock_db = AsyncMock()

        invitation_id = uuid4()
        workspace_id = uuid4()
        role_id = uuid4()
        user_id = uuid4()

        invitation = MagicMock()
        invitation.id = invitation_id
        invitation.email = "test@example.com"
        invitation.workspace_id = workspace_id
        invitation.role_id = role_id
        invitation.invited_by_user_id = user_id
        invitation.status = "pending"
        invitation.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        invitation.expires_at = datetime(2024, 12, 31, tzinfo=timezone.utc)

        workspace = MagicMock()
        workspace.name = "Test Workspace"

        role = MagicMock()
        role.name = "Member"

        # FIX: use full_name, NOT username — impl uses invited_by.full_name (line 115)
        user = MagicMock()
        user.full_name = "John Doe"

        # Build 4 execute side-effects in order:
        # 1st: invitation, 2nd: workspace, 3rd: role, 4th: inviter
        mock_results = []
        for obj in [invitation, workspace, role, user]:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = obj
            mock_results.append(mock_result)

        mock_db.execute.side_effect = mock_results

        result = await get_invitation_with_details(mock_db, str(invitation_id))

        assert result is not None
        assert result["id"] == str(invitation_id)
        assert result["email"] == "test@example.com"
        assert result["workspace_id"] == str(workspace_id)
        assert result["workspace_name"] == "Test Workspace"
        assert result["role_id"] == str(role_id)
        assert result["role_name"] == "Member"
        assert result["invited_by_user_id"] == str(user_id)
        assert result["invited_by_name"] == "John Doe"
        assert result["status"] == "pending"
        assert result["created_at"] == "2024-01-01T00:00:00+00:00"
        assert result["expires_at"] == "2024-12-31T00:00:00+00:00"
        assert "is_expired" in result

    @pytest.mark.asyncio
    async def test_get_invitation_with_details_missing_workspace(self):
        """Test getting details when workspace is deleted."""
        mock_db = AsyncMock()

        invitation = MagicMock()
        invitation.id = uuid4()
        invitation.email = "test@example.com"
        invitation.workspace_id = uuid4()
        invitation.role_id = uuid4()
        invitation.invited_by_user_id = uuid4()
        invitation.status = "pending"
        invitation.created_at = None
        invitation.expires_at = None

        role = MagicMock()
        role.name = "Member"

        user = MagicMock()
        user.full_name = "John Doe"

        mock_results = []
        for obj in [invitation, None, role, user]:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = obj
            mock_results.append(mock_result)

        mock_db.execute.side_effect = mock_results

        result = await get_invitation_with_details(mock_db, str(invitation.id))

        assert result is not None
        assert result["workspace_name"] is None
        assert result["role_name"] == "Member"
        assert result["created_at"] is None
        assert result["expires_at"] is None

    @pytest.mark.asyncio
    async def test_get_invitation_with_details_missing_role(self):
        """Test getting details when role is deleted."""
        mock_db = AsyncMock()

        invitation = MagicMock()
        invitation.id = uuid4()
        invitation.email = "test@example.com"
        invitation.workspace_id = uuid4()
        invitation.role_id = uuid4()
        invitation.invited_by_user_id = uuid4()
        invitation.status = "pending"
        invitation.created_at = None
        invitation.expires_at = None

        workspace = MagicMock()
        workspace.name = "Test Workspace"

        user = MagicMock()
        user.full_name = "John Doe"

        mock_results = []
        for obj in [invitation, workspace, None, user]:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = obj
            mock_results.append(mock_result)

        mock_db.execute.side_effect = mock_results

        result = await get_invitation_with_details(mock_db, str(invitation.id))

        assert result is not None
        assert result["workspace_name"] == "Test Workspace"
        assert result["role_name"] is None

    @pytest.mark.asyncio
    async def test_get_invitation_with_details_missing_inviter(self):
        """Test getting details when inviter user is deleted."""
        mock_db = AsyncMock()

        invitation = MagicMock()
        invitation.id = uuid4()
        invitation.email = "test@example.com"
        invitation.workspace_id = uuid4()
        invitation.role_id = uuid4()
        invitation.invited_by_user_id = uuid4()
        invitation.status = "pending"
        invitation.created_at = None
        invitation.expires_at = None

        workspace = MagicMock()
        workspace.name = "Test Workspace"

        role = MagicMock()
        role.name = "Member"

        mock_results = []
        for obj in [invitation, workspace, role, None]:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = obj
            mock_results.append(mock_result)

        mock_db.execute.side_effect = mock_results

        result = await get_invitation_with_details(mock_db, str(invitation.id))

        assert result is not None
        assert result["workspace_name"] == "Test Workspace"
        assert result["role_name"] == "Member"
        assert result["invited_by_name"] is None
