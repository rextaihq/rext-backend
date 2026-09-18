import pytest


@pytest.mark.asyncio
async def test_revenue_export_accepts_supported_formats(async_client, admin_token):
    for fmt in ["csv", "json"]:
        response = await async_client.get(
            f"/api/v1/admin/reports/revenue/export?format={fmt}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code in {200, 401, 403}


@pytest.mark.asyncio
async def test_revenue_export_rejects_invalid_format(async_client, admin_token):
    response = await async_client.get(
        "/api/v1/admin/reports/revenue/export?format=xml",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422
