"""Onboarding routes are own-account endpoints: authentication-gated only.

The former user.update permission gates were redundant (every account held
them via the removed platform-floor 'user' role), so the routes now rely on
get_current_user alone. These tests pin that contract: an authenticated
caller gets through regardless of permissions; an unauthenticated caller
does not.
"""

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, patch
from src.api.server import app
from src.api.security.dependencies import get_current_user
from src.constants.onboarding_steps import OnboardingStep


@pytest.mark.asyncio
async def test_update_onboarding_authenticated_only(client):
    """
    POST /onboarding/update succeeds for any authenticated caller,
    even one whose permission checks would all deny.
    """
    user_id = uuid4()
    mock_user = {"identity": str(user_id)}

    app.dependency_overrides[get_current_user] = lambda: mock_user

    payload = {
        "step": OnboardingStep.CONTENT_PILLAR.value,
        "action": "complete"
    }

    with patch("src.utils.rbac_utils.check_all_permissions", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False
        with patch("src.services.onboarding_service.OnboardingService.complete_step", new_callable=AsyncMock) as mock_service:
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
                "updated_at": datetime.now().isoformat()
            }
            response = await client.post("/api/v1/onboarding/update", json=payload)
            assert response.status_code == 200
            # The route must not consult the permission system at all.
            mock_check.assert_not_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_complete_onboarding_authenticated_only(client):
    """
    POST /onboarding/complete succeeds for any authenticated caller whose
    permission checks would deny.
    """
    user_id = uuid4()
    mock_user = {"identity": str(user_id)}
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("src.utils.rbac_utils.check_all_permissions", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False
        with patch("src.services.onboarding_service.OnboardingService.complete_onboarding", new_callable=AsyncMock) as mock_service:
            mock_service.return_value = {
                "id": str(uuid4()),
                "user_id": str(user_id),
                "completed": True,
                "current_step": 0,
                "completed_steps": [],
                "skipped_steps": [],
                "user_industry": None,
                "user_role": None,
                "user_goal": None,
                "heard_from": None,
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            response = await client.post("/api/v1/onboarding/complete")
            assert response.status_code == 200
            mock_check.assert_not_awaited()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_onboarding_requires_authentication(client):
    """
    Without an authenticated caller, the onboarding routes must reject.
    (422: the authorization header is validated before the dependency runs.)
    """
    app.dependency_overrides.clear()
    response = await client.post("/api/v1/onboarding/complete")
    assert response.status_code in (401, 403, 422)
