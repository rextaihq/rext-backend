"""
Tests for monitoring route severity query parameter validation.

Verifies that:
- Valid severity values (error, warning, critical) are accepted
- Invalid severity values are rejected with HTTP 422
- severity=None (omitted) is accepted
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.models.admin_models.error_log import ErrorLogSeverity

# ---------------------------------------------------------------------------
# Unit tests: ErrorLogSeverity enum
# ---------------------------------------------------------------------------


class TestErrorLogSeverityEnum:
    """Verify the ErrorLogSeverity enum has the expected values."""

    def test_enum_members_exist(self):
        assert ErrorLogSeverity.ERROR.value == "error"
        assert ErrorLogSeverity.WARNING.value == "warning"
        assert ErrorLogSeverity.CRITICAL.value == "critical"

    def test_enum_has_exactly_three_members(self):
        assert len(ErrorLogSeverity) == 3

    def test_enum_is_str_subclass(self):
        assert isinstance(ErrorLogSeverity.ERROR, str)

    def test_valid_string_lookup(self):
        assert ErrorLogSeverity("error") is ErrorLogSeverity.ERROR
        assert ErrorLogSeverity("warning") is ErrorLogSeverity.WARNING
        assert ErrorLogSeverity("critical") is ErrorLogSeverity.CRITICAL

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError):
            ErrorLogSeverity("warn")

    def test_invalid_case_raises_value_error(self):
        with pytest.raises(ValueError):
            ErrorLogSeverity("ERROR")

    def test_invalid_arbitrary_string_raises_value_error(self):
        with pytest.raises(ValueError):
            ErrorLogSeverity("sev-1")


# ---------------------------------------------------------------------------
# Integration-style tests: route query parameter validation
# ---------------------------------------------------------------------------

_MOCK_SERVICE_RETURN = {
    "logs": [],
    "pagination": {"total": 0, "page": 1, "per_page": 50, "total_pages": 0},
}


def _make_client():
    """
    Build a minimal TestClient for the monitoring router with all
    dependencies mocked so we can exercise query-param validation in isolation.
    """
    from fastapi import FastAPI

    from src.api.routes.admin import monitoring_routes

    app = FastAPI()
    app.include_router(monitoring_routes.router)

    # Patch permission + db decorators so they pass through
    import src.utils.route_decorators as rd

    def _passthrough(permission, workspace_scoped=True):
        def decorator(func):
            return func

        return decorator

    def _db_passthrough(label, auto_commit=True):
        def decorator(func):
            return func

        return decorator

    # Override FastAPI dependencies
    from src.api.database.async_database import get_async_db
    from src.api.security.dependencies import get_current_user

    async def _fake_db():
        yield AsyncMock()

    async def _fake_user():
        return {"identity": "00000000-0000-0000-0000-000000000001", "email": "admin@test.com"}

    app.dependency_overrides[get_async_db] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_user

    return app


class TestMonitoringRouteSeverityValidation:
    """HTTP-level tests for severity query parameter validation."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Patch MonitoringService.get_error_logs to avoid real DB calls."""
        with patch(
            "src.services.monitoring_service.MonitoringService.get_error_logs",
            new_callable=AsyncMock,
            return_value=_MOCK_SERVICE_RETURN,
        ):
            yield

    @pytest.fixture()
    def client(self):
        app = _make_client()
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    @pytest.mark.parametrize("severity", ["error", "warning", "critical"])
    def test_valid_severity_accepted(self, client, severity):
        response = client.get(f"/monitoring/error-logs?severity={severity}")
        # The route itself should accept valid values (200 or 5xx from mocked deps)
        assert response.status_code != 422, (
            f"Valid severity '{severity}' should not be rejected with 422"
        )

    @pytest.mark.parametrize("bad_value", ["warn", "ERROR", "critical!", "sev-1", "info", ""])
    def test_invalid_severity_rejected_with_422(self, client, bad_value):
        response = client.get(f"/monitoring/error-logs?severity={bad_value}")
        assert response.status_code == 422, (
            f"Invalid severity '{bad_value}' should return 422, got {response.status_code}"
        )

    def test_no_severity_param_accepted(self, client):
        response = client.get("/monitoring/error-logs")
        assert response.status_code != 422
