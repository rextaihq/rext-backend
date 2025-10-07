"""
Unit tests for invitation utilities.

Tests invitation helper functions including expiry checking and cleanup.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.utils.invitation_utils import (
    is_invitation_expired,
    cleanup_expired_invitations,
    get_invitation_with_details
)
from src.api.models.user_models.invitations import UserInvitations


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
        invitation.expires_at = datetime.utcnow() + timedelta(days=7)
        
        result = is_invitation_expired(invitation)
        
        assert result is False

    def test_is_invitation_expired_past_date_naive(self):
        """Test that invitation with past expiry is expired (naive datetime)."""
        invitation = MagicMock(spec=UserInvitations)
        # Create naive datetime (no timezone)
        invitation.expires_at = datetime.utcnow() - timedelta(days=1)
        
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

    def test_cleanup_expired_invitations_none_expired(self):
        """Test cleanup when no invitations are expired."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = []
        mock_db.query.return_value.filter.return_value = mock_query
        
        result = cleanup_expired_invitations(mock_db)
        
        assert result == 0
        assert mock_db.commit.called
        assert not mock_db.rollback.called

    def test_cleanup_expired_invitations_multiple_expired(self):
        """Test cleanup when multiple invitations are expired."""
        mock_db = MagicMock()
        
        # Create mock expired invitations
        inv1 = MagicMock()
        inv1.status = "pending"
        inv2 = MagicMock()
        inv2.status = "pending"
        inv3 = MagicMock()
        inv3.status = "pending"
        
        mock_query = MagicMock()
        mock_query.all.return_value = [inv1, inv2, inv3]
        mock_db.query.return_value.filter.return_value = mock_query
        
        result = cleanup_expired_invitations(mock_db)
        
        assert result == 3
        assert inv1.status == "expired"
        assert inv2.status == "expired"
        assert inv3.status == "expired"
        assert mock_db.commit.called
        assert not mock_db.rollback.called

    def test_cleanup_expired_invitations_single_expired(self):
        """Test cleanup with single expired invitation."""
        mock_db = MagicMock()
        
        inv = MagicMock()
        inv.status = "pending"
        
        mock_query = MagicMock()
        mock_query.all.return_value = [inv]
        mock_db.query.return_value.filter.return_value = mock_query
        
        result = cleanup_expired_invitations(mock_db)
        
        assert result == 1
        assert inv.status == "expired"
        assert mock_db.commit.called

    @patch('src.utils.invitation_utils.logger')
    def test_cleanup_expired_invitations_logs_when_cleaned(self, mock_logger):
        """Test that cleanup logs when invitations are marked expired."""
        mock_db = MagicMock()
        
        inv = MagicMock()
        inv.status = "pending"
        
        mock_query = MagicMock()
        mock_query.all.return_value = [inv]
        mock_db.query.return_value.filter.return_value = mock_query
        
        cleanup_expired_invitations(mock_db)
        
        mock_logger.info.assert_called_once()
        assert "Marked 1 expired invitations" in str(mock_logger.info.call_args)

    @patch('src.utils.invitation_utils.logger')
    def test_cleanup_expired_invitations_no_log_when_none(self, mock_logger):
        """Test that cleanup doesn't log when no invitations expired."""
        mock_db = MagicMock()
        
        mock_query = MagicMock()
        mock_query.all.return_value = []
        mock_db.query.return_value.filter.return_value = mock_query
        
        cleanup_expired_invitations(mock_db)
        
        # Should not call logger.info since count is 0
        mock_logger.info.assert_not_called()

    @patch('src.utils.invitation_utils.logger')
    def test_cleanup_expired_invitations_handles_exception(self, mock_logger):
        """Test that cleanup handles exceptions gracefully."""
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database error")
        
        result = cleanup_expired_invitations(mock_db)
        
        assert result == 0
        assert mock_db.rollback.called
        mock_logger.error.assert_called_once()
        assert "Error cleaning up" in str(mock_logger.error.call_args)


class TestGetInvitationWithDetails:
    """Tests for get_invitation_with_details function."""

    def test_get_invitation_with_details_not_found(self):
        """Test getting details for non-existent invitation."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.first.return_value = None
        mock_db.query.return_value.filter.return_value = mock_query
        
        result = get_invitation_with_details(mock_db, str(uuid4()))
        
        assert result is None

    def test_get_invitation_with_details_complete(self):
        """Test getting complete invitation details."""
        mock_db = MagicMock()
        
        # Mock invitation
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
        
        # Mock workspace
        workspace = MagicMock()
        workspace.name = "Test Workspace"
        
        # Mock role
        role = MagicMock()
        role.name = "Member"
        
        # Mock user
        user = MagicMock()
        user.username = "john_doe"
        
        # Setup query mocks
        def query_side_effect(model):
            mock_query = MagicMock()
            if model.__name__ == 'UserInvitations':
                mock_query.filter.return_value.first.return_value = invitation
            elif model.__name__ == 'WorkspaceModel':
                mock_query.filter.return_value.first.return_value = workspace
            elif model.__name__ == 'Role':
                mock_query.filter.return_value.first.return_value = role
            elif model.__name__ == 'Users':
                mock_query.filter.return_value.first.return_value = user
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        result = get_invitation_with_details(mock_db, str(invitation_id))
        
        assert result is not None
        assert result["id"] == str(invitation_id)
        assert result["email"] == "test@example.com"
        assert result["workspace_id"] == str(workspace_id)
        assert result["workspace_name"] == "Test Workspace"
        assert result["role_id"] == str(role_id)
        assert result["role_name"] == "Member"
        assert result["invited_by_user_id"] == str(user_id)
        assert result["invited_by_name"] == "john_doe"
        assert result["status"] == "pending"
        assert result["created_at"] == "2024-01-01T00:00:00+00:00"
        assert result["expires_at"] == "2024-12-31T00:00:00+00:00"
        assert "is_expired" in result

    def test_get_invitation_with_details_missing_workspace(self):
        """Test getting details when workspace is deleted."""
        mock_db = MagicMock()
        
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
        user.username = "john_doe"
        
        def query_side_effect(model):
            mock_query = MagicMock()
            if model.__name__ == 'UserInvitations':
                mock_query.filter.return_value.first.return_value = invitation
            elif model.__name__ == 'WorkspaceModel':
                mock_query.filter.return_value.first.return_value = None
            elif model.__name__ == 'Role':
                mock_query.filter.return_value.first.return_value = role
            elif model.__name__ == 'Users':
                mock_query.filter.return_value.first.return_value = user
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        result = get_invitation_with_details(mock_db, str(invitation.id))
        
        assert result is not None
        assert result["workspace_name"] is None
        assert result["role_name"] == "Member"
        assert result["created_at"] is None
        assert result["expires_at"] is None

    def test_get_invitation_with_details_missing_role(self):
        """Test getting details when role is deleted."""
        mock_db = MagicMock()
        
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
        user.username = "john_doe"
        
        def query_side_effect(model):
            mock_query = MagicMock()
            if model.__name__ == 'UserInvitations':
                mock_query.filter.return_value.first.return_value = invitation
            elif model.__name__ == 'WorkspaceModel':
                mock_query.filter.return_value.first.return_value = workspace
            elif model.__name__ == 'Role':
                mock_query.filter.return_value.first.return_value = None
            elif model.__name__ == 'Users':
                mock_query.filter.return_value.first.return_value = user
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        result = get_invitation_with_details(mock_db, str(invitation.id))
        
        assert result is not None
        assert result["workspace_name"] == "Test Workspace"
        assert result["role_name"] is None

    def test_get_invitation_with_details_missing_inviter(self):
        """Test getting details when inviter user is deleted."""
        mock_db = MagicMock()
        
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
        
        def query_side_effect(model):
            mock_query = MagicMock()
            if model.__name__ == 'UserInvitations':
                mock_query.filter.return_value.first.return_value = invitation
            elif model.__name__ == 'WorkspaceModel':
                mock_query.filter.return_value.first.return_value = workspace
            elif model.__name__ == 'Role':
                mock_query.filter.return_value.first.return_value = role
            elif model.__name__ == 'Users':
                mock_query.filter.return_value.first.return_value = None
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        result = get_invitation_with_details(mock_db, str(invitation.id))
        
        assert result is not None
        assert result["workspace_name"] == "Test Workspace"
        assert result["role_name"] == "Member"
        assert result["invited_by_name"] is None

