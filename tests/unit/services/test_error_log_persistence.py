"""
Regression tests for the System Monitoring error-log write path.

The bug these guard against: ``ErrorLog.severity`` is a non-native
``Enum(ErrorLogSeverity)`` column whose DB CHECK constraint only allows the
lowercase *values* (``error``/``warning``/``critical``). Without
``values_callable`` SQLAlchemy serialises the member *name* (``ERROR``/...),
so every INSERT fails the constraint and every persist is silently dropped —
the dashboard stays permanently empty.
"""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy.dialects import postgresql

from src.api.middleware.error_handler import _should_skip_error_log
from src.api.models.admin_models.error_log import ErrorLog, ErrorLogSeverity
from src.services.monitoring_service import MonitoringService


# ---------------------------------------------------------------------------
# 1. The enum must serialise to the lowercase value the DB constraint allows
# ---------------------------------------------------------------------------

def test_severity_column_uses_lowercase_values_not_member_names():
    enum_type = ErrorLog.__table__.c.severity.type
    assert set(enum_type.enums) == {"error", "warning", "critical"}

    bind = enum_type.bind_processor(postgresql.dialect())
    assert bind(ErrorLogSeverity.ERROR) == "error"
    assert bind(ErrorLogSeverity.WARNING) == "warning"
    assert bind(ErrorLogSeverity.CRITICAL) == "critical"


# ---------------------------------------------------------------------------
# 2. persist_error_log: severity mapping, redaction, skip rules
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


@pytest.fixture
def fake_session(monkeypatch):
    session = _FakeSession()

    @asynccontextmanager
    async def _factory():
        yield session

    import src.api.database.async_database as adb

    monkeypatch.setattr(adb, "AsyncSessionLocal", lambda: _factory(), raising=False)
    return session


@pytest.mark.asyncio
async def test_low_severity_is_skipped(fake_session):
    await MonitoringService.persist_error_log(api_severity="low", message="not found")
    assert fake_session.added == []
    assert fake_session.committed is False


@pytest.mark.asyncio
async def test_high_maps_to_error_and_redacts(fake_session):
    await MonitoringService.persist_error_log(
        api_severity="high",
        message="boom api_key=supersecret",
        source="GET /things",
        request_id="req_1",
        stack_trace="Traceback…\npassword: hunter2",
        metadata={"token": "abc", "status_code": 500},
    )
    assert len(fake_session.added) == 1
    entry = fake_session.added[0]
    assert entry.severity is ErrorLogSeverity.ERROR
    assert "supersecret" not in entry.message
    assert "hunter2" not in entry.stack_trace
    assert entry.error_metadata["token"] == "[REDACTED]"
    assert entry.error_metadata["status_code"] == 500
    assert fake_session.committed is True


@pytest.mark.asyncio
async def test_medium_maps_to_warning(fake_session):
    await MonitoringService.persist_error_log(api_severity="medium", message="hmm")
    assert fake_session.added[0].severity is ErrorLogSeverity.WARNING


@pytest.mark.asyncio
async def test_invalid_user_id_becomes_null(fake_session):
    await MonitoringService.persist_error_log(
        api_severity="critical", message="x", user_id="not-a-uuid"
    )
    assert fake_session.added[0].user_id is None


@pytest.mark.asyncio
async def test_db_failure_is_swallowed(monkeypatch):
    import src.api.database.async_database as adb

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(adb, "AsyncSessionLocal", _boom, raising=False)
    await MonitoringService.persist_error_log(api_severity="critical", message="x")  # must not raise


# ---------------------------------------------------------------------------
# 3. Skip rules — monitoring + health paths never get logged
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path,skip",
    [
        ("/api/v1/admin/monitoring/error-logs", True),
        ("/health", True),
        ("/health/payment", True),
        ("/api/health", True),
        ("/api/v1/subscriptions/plans/public", False),
        ("/api/v1/admin/emails/failed", False),
    ],
)
def test_should_skip_error_log(path, skip):
    assert _should_skip_error_log(path) is skip
