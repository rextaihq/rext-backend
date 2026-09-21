import pytest


@pytest.mark.asyncio
async def test_complete_onboarding_marks_required_steps_consistently(async_client, user_token):
    response = await async_client.post(
        "/api/v1/onboarding/complete",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_step"] == 2
    assert 0 in body["completed_steps"]
    assert 1 in body["completed_steps"]
