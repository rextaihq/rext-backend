import pytest

from src.api.middleware.usage_limiter import get_user_subscription_and_plan


class DummyAsyncSession:
    pass


def test_deprecated_sync_subscription_helper_fails_fast():
    with pytest.raises(RuntimeError):
        get_user_subscription_and_plan(DummyAsyncSession(), "user-123")