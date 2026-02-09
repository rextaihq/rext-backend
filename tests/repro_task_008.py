import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from src.utils.route_decorators import require_permissions
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import MagicMock
import uuid

app = FastAPI()

# Mock DB dependency
async def get_mock_db():
    return MagicMock(spec=AsyncSession)

# Mock Current User dependency
async def get_mock_user():
    return {"identity": str(uuid.uuid4())}

# Misconfigured route: workspace_scoped=True but NO workspace_id in parameters
@app.get("/test-misconfigured")
@require_permissions("test.permission", workspace_scoped=True)
async def test_misconfigured_route(
    db: AsyncSession = Depends(get_mock_db),
    user: dict = Depends(get_mock_user)
):
    return {"status": "ok"}

# Correctly configured route
@app.get("/test-correct/{workspace_id}")
@require_permissions("test.permission", workspace_scoped=True)
async def test_correct_route(
    workspace_id: str,
    db: AsyncSession = Depends(get_mock_db),
    user: dict = Depends(get_mock_user)
):
    return {"status": "ok"}

client = TestClient(app)

def test_require_permissions_validation():
    # Calling the misconfigured route should raise a ValueError during execution of the decorator
    # Note: In FastAPI, exceptions raised in dependencies or decorators called within the route
    # might be caught by the app, but since this is inside the wrapper, it should bubble up or
    # cause a 500 if not handled.
    # However, the requirement says "observe that a ValueError is raised".
    
    pass  # Placeholder for previous logic

    # Let's try calling the route via TestClient
    # FastAPI usually catches exceptions and returns 500.
    # But if we want to see the ValueError, we might want to test the decorator wrapper directly.
    
    from src.utils.route_decorators import require_permissions
    
    # Mocking the function that would be decorated
    async def mock_func(db, user):
        return {"status": "ok"}
    
    decorated = require_permissions("test.permission", workspace_scoped=True)(mock_func)
    
    # Missing workspace_id in kwargs
    with pytest.raises(ValueError) as excinfo:
        import asyncio
        asyncio.run(decorated(db=MagicMock(), user={"identity": str(uuid.uuid4())}))
    
    assert "requires 'workspace_id' parameter" in str(excinfo.value)
    print(f"Caught expected ValueError: {excinfo.value}")

if __name__ == "__main__":
    test_require_permissions_validation()
