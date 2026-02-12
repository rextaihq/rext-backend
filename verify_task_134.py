import asyncio
import uuid
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient
from src.api.server import app

async def run_verification():
    print("Starting verification for Task 134...")
    
    # Mock user and DB
    test_user_id = str(uuid4())
    
    async def override_get_db():
        yield AsyncMock()

    def override_current_user():
        return {"identity": test_user_id}

    from src.api.database.async_database import get_async_db
    from src.api.security.dependencies import get_current_user
    
    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        
        # 1. Test Cancel Not Found -> 404
        print("\nTesting cancel non-existent subscription (expecting 404)...")
        with patch("src.services.subscription_service.SubscriptionService.cancel", new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = None
            response = await client.post("/api/subscriptions/cancel", json={"reason": "test"})
            print(f"Status: {response.status_code}")
            assert response.status_code == 404
            data = response.json()
            assert data["success"] is False
            print("OK: Got 404 for missing subscription.")

        # 2. Test Cancel Exception -> 500 (Sanitized)
        print("\nTesting cancel with internal error (expecting 500 sanitized)...")
        with patch("src.services.subscription_service.SubscriptionService.cancel", side_effect=Exception("SECRET_INTERNAL_DB_ERROR")):
            response = await client.post("/api/subscriptions/cancel", json={"reason": "test"})
            print(f"Status: {response.status_code}")
            assert response.status_code == 500
            data = response.json()
            assert "SECRET_INTERNAL_DB_ERROR" not in str(data)
            print(f"Error Message: {data['error']['message']}")
            print("OK: Got 500 and secret message was NOT leaked.")

        # 3. Test Portal Session Exception -> 500 (Sanitized)
        print("\nTesting portal session with internal error (expecting 500 sanitized)...")
        # Need to mock more things for this route
        execute_result = AsyncMock()
        execute_result.scalar_one_or_none.return_value = AsyncMock(provider_customer_id="cus_123")
        
        with patch("src.api.routes.subscriptions.checkout_routes.get_payment_provider") as mock_get_provider, \
             patch("sqlalchemy.ext.asyncio.AsyncSession.execute", return_value=execute_result):
            
            mock_provider = AsyncMock()
            mock_provider.create_portal_session.side_effect = Exception("SENSITIVE_API_KEY_123")
            mock_get_provider.return_value = mock_provider
            
            response = await client.get("/api/subscriptions/portal")
            print(f"Status: {response.status_code}")
            assert response.status_code == 500
            data = response.json()
            assert "SENSITIVE_API_KEY_123" not in str(data)
            print(f"Detail: {data['detail']}")
            print("OK: Got 500 and sensitive API key was NOT leaked.")

    print("\nVerification completed successfully!")

if __name__ == "__main__":
    from uuid import uuid4
    asyncio.run(run_verification())
