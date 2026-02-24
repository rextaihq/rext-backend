import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_export_subscriptions_returns_csv(client: AsyncClient, admin_auth_headers: dict):
    """
    Test that the export subscriptions endpoint returns a CSV file.
    """
    response = await client.get("/api/v1/admin/export/subscriptions", headers=admin_auth_headers)
    
    # Assert response status
    assert response.status_code == 200
    
    # Assert headers
    assert response.headers["content-type"].startswith("text/csv")
    assert "charset=utf-8" in response.headers["content-type"]
    assert "attachment; filename=subscriptions_export_" in response.headers["content-disposition"]
    
    # Assert content
    content = response.text
    assert "Subscription ID,User Email,User Name" in content
