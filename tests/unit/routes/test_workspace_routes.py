from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.api.security.dependencies import get_current_user
from src.api.server import app


@pytest.mark.asyncio
async def test_create_workspace_returns_operation_id(client) -> None:
    """
    Ensure the workspace creation route surfaces both workspace data and
    operation_id so callers can initiate SSE subscriptions.
    """
    user_identity = uuid4()

    def override_current_user():
        return {"identity": str(user_identity)}

    app.dependency_overrides[get_current_user] = override_current_user

    expected_payload = {
        "workspace": {"id": "workspace-123", "name": "Example Workspace"},
        "operation_id": "op-abc-123",
    }

    try:
        with patch("src.api.routes.workspaces.WorkspaceService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.create_workspace_for_user = AsyncMock(return_value=expected_payload)

            response = await client.post(
                "/api/v1/workspaces",
                json={
                    "name": "Example Workspace",
                    "description": "A workspace for testing",
                    "url": "https://example.com",
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    body = response.json()

    assert body["success"] is True
    assert body["data"]["workspace"] == expected_payload["workspace"]
    assert body["data"]["operation_id"] == expected_payload["operation_id"]
    assert "Background processing initiated" in body["data"]["message"]
    mock_service.create_workspace_for_user.assert_awaited_once()
