
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from src.services.workspace_service import WorkspaceService
from src.api.models.user_models.roles import Role
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.middleware.exceptions import ForbiddenException

@pytest.mark.asyncio
async def test_verify_user_is_workspace_owner_success():
    """
    Test that verify_user_is_workspace_owner returns True 
    when the user has the 'workspace_owner' role.
    """
    mock_db = AsyncMock()
    service = WorkspaceService(mock_db)
    
    workspace_id = uuid4()
    user_id = uuid4()
    role_id = uuid4()
    
    # Mock workspace member
    mock_member = WorkspaceMembers(
        workspace_id=workspace_id,
        user_id=user_id,
        role_id=role_id
    )
    
    # Mock role
    mock_role = Role(
        id=role_id,
        name="workspace_owner"
    )
    
    # Mock DB executions
    # First query gets the member
    # Second query gets the role
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_member)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_role))
    ]
    
    result = await service.verify_user_is_workspace_owner(workspace_id, user_id)
    assert result is True


@pytest.mark.asyncio
async def test_verify_user_is_workspace_owner_failure_wrong_role():
    """
    Test that verify_user_is_workspace_owner raises ForbiddenException
    when the user has a different role (e.g. 'editor').
    """
    mock_db = AsyncMock()
    service = WorkspaceService(mock_db)
    
    workspace_id = uuid4()
    user_id = uuid4()
    role_id = uuid4()
    
    mock_member = WorkspaceMembers(
        workspace_id=workspace_id,
        user_id=user_id,
        role_id=role_id
    )
    
    mock_role = Role(
        id=role_id,
        name="editor"
    )
    
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_member)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_role))
    ]
    
    with pytest.raises(ForbiddenException) as excinfo:
        await service.verify_user_is_workspace_owner(workspace_id, user_id)
    
    assert "Only workspace owners can perform this action" in str(excinfo.value)
