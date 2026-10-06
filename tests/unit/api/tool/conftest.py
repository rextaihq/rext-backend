import pytest

from src.api.cache.redis_client import cache
from src.api.tool import limits


@pytest.fixture(autouse=True)
def free_tool_counts(monkeypatch):
    """Each test starts with no free-tool call counted, in memory rather than a shared Redis."""
    monkeypatch.setattr(cache, "redis", None)
    monkeypatch.setattr(limits, "COUNTS", limits.DayCounts())
