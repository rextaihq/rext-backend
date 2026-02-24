import pytest


@pytest.mark.asyncio
async def test_customer_detail_rejects_invalid_uuid(async_client, admin_token):
    response = await async_client.get(
        "/api/v1/admin/customers/not-a-uuid",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 422