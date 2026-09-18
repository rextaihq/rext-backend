from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.api.security.dependencies import get_current_user
from src.api.server import app
from src.constants.onboarding_steps import OnboardingStep


@pytest.mark.asyncio
async def test_update_onboarding_permissions(client):
    """
    Test that POST /onboarding/update requires user.update permission.
    """
    user_id = uuid4()
    mock_user = {"identity": str(user_id)}

    # Override authentication dependency
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Valid payload for update
    payload = {"step": OnboardingStep.CONTENT_PILLAR.value, "action": "complete"}

    # 1. Test with permission DENIED (check_all_permissions returns False)
    with patch("src.utils.rbac_utils.check_all_permissions", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False
        response = await client.post("/api/v1/onboarding/update", json=payload)
        assert response.status_code == 403

    # 2. Test with permission GRANTED (check_all_permissions returns True)
    with patch("src.utils.rbac_utils.check_all_permissions", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True
        # Mock service call to avoid database issues for onboarding table
        with patch(
            "src.services.onboarding_service.OnboardingService.complete_step",
            new_callable=AsyncMock,
        ) as mock_service:
            mock_service.return_value = {
                "id": str(uuid4()),
                "user_id": str(user_id),
                "completed": False,
                "current_step": OnboardingStep.CONTENT_PILLAR.value,
                "completed_steps": [],
                "skipped_steps": [],
                "user_industry": None,
                "user_role": None,
                "user_goal": None,
                "heard_from": None,
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            response = await client.post("/api/v1/onboarding/update", json=payload)
            assert response.status_code == 200
            mock_check.assert_awaited_once()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_complete_onboarding_permissions(client):
    """
    Test that POST /onboarding/complete requires user.update permission.
    """
    user_id = uuid4()
    mock_user = {"identity": str(user_id)}
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Test with permission DENIED
    with patch("src.utils.rbac_utils.check_all_permissions", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False
        response = await client.post("/api/v1/onboarding/complete")
        assert response.status_code == 403

    app.dependency_overrides.clear()
