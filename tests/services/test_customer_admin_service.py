import inspect
from unittest.mock import AsyncMock

import pytest

from src.services.customer_admin_service import CustomerAdminService


@pytest.mark.asyncio
async def test_customer_admin_service_has_no_inline_service_imports():
    source = inspect.getsource(CustomerAdminService)
    assert "from src.services.audit_service import AuditService" not in source
    assert "from src.services.usage_tracking_service import UsageTrackingService" not in source


@pytest.mark.asyncio
async def test_customer_admin_service_imports_cleanly():
    db = AsyncMock()
    service = CustomerAdminService(db)
    assert service.db is db
