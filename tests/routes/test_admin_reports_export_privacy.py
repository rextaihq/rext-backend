import pytest


@pytest.mark.asyncio
async def test_revenue_export_defaults_to_non_email_actor(async_client, admin_token):
    response = await async_client.get(
        "/api/v1/admin/reports/revenue/export",
        params={"format": "json"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert "@" not in response.text


@pytest.mark.asyncio
async def test_revenue_export_email_actor_requires_super_admin(async_client, admin_token):
    response = await async_client.get(
        "/api/v1/admin/reports/revenue/export",
        params={"format": "json", "include_actor_email": "true"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 403
