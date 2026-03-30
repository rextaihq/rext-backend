import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from uuid import uuid4

@pytest.fixture
def mock_user():
    return {
        "identity": str(uuid4()),
        "roles": ["admin"],
        "permissions": ["audit.read"]
    }

@patch("src.api.security.dependencies.get_current_user")
@patch("src.api.database.async_database.get_async_db")
def test_get_email_analytics_overview_validation(mock_db, mock_current_user, mock_user):
    from src.main import app
    client = TestClient(app)
    mock_current_user.return_value = mock_user
    
    # Test valid date_range
    with patch("src.services.email_analytics_service.EmailAnalyticsService.get_overview_stats") as mock_stats:
        mock_stats.return_value = {"total_sent": 10}
        response = client.get("/api/v1/admin/email-analytics/overview?date_range=7d")
        assert response.status_code == 200
    
    # Test invalid date_range
    response = client.get("/api/v1/admin/email-analytics/overview?date_range=xd")
    assert response.status_code == 422
    assert "date_range" in response.text

@patch("src.api.security.dependencies.get_current_user")
@patch("src.api.database.async_database.get_async_db")
def test_get_email_analytics_by_template_validation(mock_db, mock_current_user, mock_user):
    from src.main import app
    client = TestClient(app)
    mock_current_user.return_value = mock_user
    
    # Test valid date_range
    with patch("src.services.email_analytics_service.EmailAnalyticsService.get_analytics_by_template") as mock_stats:
        mock_stats.return_value = []
        response = client.get("/api/v1/admin/email-analytics/by-template?date_range=90d")
        assert response.status_code == 200
    
    # Test invalid date_range
    response = client.get("/api/v1/admin/email-analytics/by-template?date_range=365d")
    assert response.status_code == 422

@patch("src.api.security.dependencies.get_current_user")
@patch("src.api.database.async_database.get_async_db")
def test_get_email_timeline_validation(mock_db, mock_current_user, mock_user):
    from src.main import app
    client = TestClient(app)
    mock_current_user.return_value = mock_user
    
    # Test valid date_range
    with patch("src.services.email_analytics_service.EmailAnalyticsService.get_timeline") as mock_stats:
        mock_stats.return_value = []
        response = client.get("/api/v1/admin/email-analytics/timeline?date_range=30d")
        assert response.status_code == 200
    
    # Test invalid date_range
    response = client.get("/api/v1/admin/email-analytics/timeline?date_range=foo")
    assert response.status_code == 422
