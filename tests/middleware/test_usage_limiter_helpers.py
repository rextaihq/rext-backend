from unittest.mock import AsyncMock

import pytest

from src.api.middleware.usage_limiter import increment_api_calls, reset_monthly_usage


@pytest.mark.asyncio
async def test_increment_api_calls_delegates_to_tracking_service(monkeypatch):
    tracker_mock = AsyncMock()
    tracker_cls = AsyncMock(return_value=tracker_mock)

    monkeypatch.setattr(
        "src.api.middleware.usage_limiter.UsageTrackingService",
        lambda db: tracker_mock,
    )

    db = AsyncMock()
    await increment_api_calls(db, "11111111-1111-1111-1111-111111111111")

    tracker_mock.increment_api_calls.assert_awaited_once()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_monthly_usage_returns_processed_count(monkeypatch):
    class FakeResult:
        def all(self):
            return [
                ("11111111-1111-1111-1111-111111111111",),
                ("22222222-2222-2222-2222-222222222222",),
            ]

    tracker_mock = AsyncMock()
    monkeypatch.setattr(
        "src.api.middleware.usage_limiter.UsageTrackingService",
        lambda db: tracker_mock,
    )

    db = AsyncMock()
    db.execute = AsyncMock(return_value=FakeResult())

    count = await reset_monthly_usage(db)

    assert count == 2
    assert tracker_mock.reset_monthly_usage.await_count == 2
    db.flush.assert_awaited_once()
