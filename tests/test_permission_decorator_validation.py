import pytest
import asyncio
from unittest.mock import MagicMock
from src.utils.route_decorators import require_permissions
from uuid import uuid4

@pytest.mark.asyncio
async def test_require_permissions_missing_workspace_id():
    """
    Test that require_permissions raises ValueError when workspace_scoped=True
    but workspace_id is missing from route parameters.
    """
    
    @require_permissions("content.read", workspace_scoped=True)
    async def mock_route(db, user, request):
        return {"status": "ok"}

    # Mock dependencies
    mock_db = MagicMock()
    mock_user = {"identity": str(uuid4())}
    mock_request = MagicMock()

    # This should raise ValueError because 'workspace_id' is not in kwargs
    with pytest.raises(ValueError) as exc_info:
        await mock_route(db=mock_db, user=mock_user, request=mock_request)
    
    assert "requires 'workspace_id' parameter" in str(exc_info.value)
    assert "mock_route" in str(exc_info.value)

@pytest.mark.asyncio
async def test_require_permissions_with_workspace_id():
    """
    Test that require_permissions works correctly when workspace_id is present.
    """
    from src.utils import rbac_utils
    from unittest.mock import patch

    # We need to mock the permission check to avoid DB calls
    with patch("src.utils.rbac_utils.check_all_permissions", return_value=asyncio.Future()) as mock_check:
        mock_check.return_value.set_result(True)
        
        @require_permissions("content.read", workspace_scoped=True)
        async def mock_route(workspace_id, db, user, request):
            return {"status": "ok"}

        mock_db = MagicMock()
        mock_user = {"identity": str(uuid4())}
        mock_request = MagicMock()
        workspace_id = "test-workspace"

        result = await mock_route(
            workspace_id=workspace_id,
            db=mock_db,
            user=mock_user,
            request=mock_request
        )
        
        assert result == {"status": "ok"}
