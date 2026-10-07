"""The admin email analytics routes accept only the date ranges they offer (7d, 30d, 90d).

The router runs in a small app of its own, as the app mounts it (under /api/v1), with the
caller resolved and the session a mock; the permission check reads a stubbed answer, and the
analytics service is patched. Nothing reaches a database.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.database.async_database import get_async_db
from src.api.middleware.error_handler import setup_exception_handlers
from src.api.routes.admin.email_analytics_routes import router
from src.api.security.dependencies import get_current_user

SERVICE = "src.services.email_analytics_service.EmailAnalyticsService"
OVERVIEW = {
    "total_sent": 10,
    "total_delivered": 9,
    "total_opened": 5,
    "total_clicked": 2,
    "total_bounced": 1,
    "total_complained": 0,
    "delivery_rate": 90.0,
    "open_rate": 55.6,
    "click_rate": 22.2,
    "bounce_rate": 10.0,
    "complaint_rate": 0.0,
}


@pytest.fixture
def allowed(monkeypatch):
    """Whether the caller holds security.read, as the permission check finds it."""
    import src.utils.rbac_utils as rbac

    answer = AsyncMock(return_value=True)
    monkeypatch.setattr(rbac, "is_user_super_admin", AsyncMock(return_value=False))
    monkeypatch.setattr(rbac, "check_all_permissions", answer)
    return answer


@pytest.fixture
def client(allowed):
    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")

    async def override_db():
        yield AsyncMock()

    app.dependency_overrides[get_async_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(uuid4())}
    return TestClient(app)


def test_get_email_analytics_overview_validation(client):
    with patch(f"{SERVICE}.get_overview_stats", AsyncMock(return_value=OVERVIEW)) as stats:
        response = client.get("/api/v1/admin/email-analytics/overview?date_range=7d")
    assert response.status_code == 200
    assert response.json()["data"]["total_sent"] == 10
    assert stats.await_args.args[0] == "7d"

    response = client.get("/api/v1/admin/email-analytics/overview?date_range=xd")
    assert response.status_code == 422
    assert "date_range" in response.text


def test_get_email_analytics_by_template_validation(client):
    with patch(f"{SERVICE}.get_analytics_by_template", AsyncMock(return_value=[])):
        response = client.get("/api/v1/admin/email-analytics/by-template?date_range=90d")
    assert response.status_code == 200
    assert response.json()["data"] == {"templates": [], "total_count": 0}

    response = client.get("/api/v1/admin/email-analytics/by-template?date_range=365d")
    assert response.status_code == 422


def test_get_email_timeline_validation(client):
    with patch(f"{SERVICE}.get_timeline", AsyncMock(return_value=[])):
        response = client.get("/api/v1/admin/email-analytics/timeline?date_range=30d")
    assert response.status_code == 200
    assert response.json()["data"] == {"timeline": [], "total_count": 0}

    response = client.get("/api/v1/admin/email-analytics/timeline?date_range=foo")
    assert response.status_code == 422


def test_email_analytics_need_security_read(client, allowed):
    allowed.return_value = False

    with patch(f"{SERVICE}.get_overview_stats", AsyncMock(return_value=OVERVIEW)) as stats:
        response = client.get("/api/v1/admin/email-analytics/overview?date_range=7d")

    assert response.status_code == 403
    stats.assert_not_awaited()
