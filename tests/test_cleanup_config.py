import pytest
from pydantic import ValidationError

from src.config.cleanup_config import CleanupConfig


def test_cleanup_config_rejects_invalid_hour(monkeypatch):
    monkeypatch.setenv("CLEANUP_HOUR", "99")
    with pytest.raises(ValidationError):
        CleanupConfig()


def test_cleanup_config_ignores_empty_env_values(monkeypatch):
    monkeypatch.setenv("CLEANUP_BATCH_SIZE", "")
    cfg = CleanupConfig()
    assert cfg.CLEANUP_BATCH_SIZE == 1000