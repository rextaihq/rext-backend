"""The settings objects print without their secrets (rext-control G57 #505).

Anything that turns a settings object into text (a log line, an error that quotes it, a
crash report that records local variables) must not carry a key with it. The values
below are made up for the test.
"""

from unittest.mock import patch

import pytest
from pydantic_settings import BaseSettings

# Loaded for the guard below, which checks every settings class that exists.
import src.config.cleanup_config  # noqa: F401
import src.config.storage_config  # noqa: F401
from src.api.config import Settings
from src.config.email_config import EmailConfig
from src.config.hidden_secrets import HIDDEN, HidesSecrets, hide_secret
from src.config.payment_config import PaymentSettings
from src.config.storage_config import StorageSettings

SECRETS = {
    "SECRET_KEY": "made-up-signing-secret-for-the-test-0001",
    "REFRESH_SECRET_KEY": "made-up-refresh-secret-for-the-test-0002",
    "OPENAI_API_KEY": "sk-made-up-openai-key-0003",
    "LANGSMITH_API_KEY": "lsv2-made-up-key-0005",
    "MINIO_SECRET_KEY": "made-up-minio-secret-0006",
}
DB_PASSWORD = "made-up-db-password-0007"
REDIS_PASSWORD = "made-up-redis-password-0008"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        **SECRETS,
        POSTGRES_URI_CUSTOM=f"postgresql://rext:{DB_PASSWORD}@db.example:5432/rext",
        REDIS_URL=f"redis://:{REDIS_PASSWORD}@cache.example:6379/0",
    )


def _all_values() -> list[str]:
    return [*SECRETS.values(), DB_PASSWORD, REDIS_PASSWORD]


@pytest.mark.parametrize("text", [repr, str])
def test_settings_print_without_their_secrets(settings: Settings, text) -> None:
    printed = text(settings)
    for value in _all_values():
        assert value not in printed
    # The names and the rest stay, so the object is still worth printing.
    assert f"OPENAI_API_KEY='{HIDDEN}'" in printed
    assert f"postgresql://rext:{HIDDEN}@db.example:5432/rext" in printed
    assert f"redis://:{HIDDEN}@cache.example:6379/0" in printed
    assert "ACCESS_TOKEN_EXPIRE_MINUTES=" in printed


def test_an_error_that_quotes_the_settings_carries_no_secret(settings: Settings) -> None:
    # unittest.mock's message for a missing attribute quotes its target with str():
    # this is how a test once printed every key.
    with pytest.raises(AttributeError) as error:
        with patch.object(settings, "NO_SUCH_SETTING", "x"):
            pass
    for value in _all_values():
        assert value not in str(error.value)


@pytest.mark.parametrize(
    ("config", "field", "value"),
    [
        (PaymentSettings, "lemonsqueezy_api_key", "made-up-ls-key-0009"),
        (PaymentSettings, "lemonsqueezy_webhook_secret", "made-up-ls-webhook-0010"),
        (EmailConfig, "resend_api_key", "re_made-up-key-0011"),
        (EmailConfig, "resend_webhook_secret", "whsec_made-up-0012"),
        (EmailConfig, "smtp_password", "made-up-smtp-0013"),
        (StorageSettings, "r2_secret_access_key", "made-up-r2-secret-0014"),
    ],
)
def test_the_other_configs_print_without_their_secrets(config, field, value) -> None:
    printed = repr(config(**{field: value}))
    assert value not in printed
    assert f"{field}='{HIDDEN}'" in printed


@pytest.mark.parametrize(
    ("name", "value", "shown"),
    [
        ("SENTRY_DSN", "https://abc123@o1.ingest.example/2", HIDDEN),
        ("ACCESS_TOKEN_EXPIRE_MINUTES", 1, 1),
        ("API_KEY", None, None),
        ("API_KEY", "", ""),
        ("FRONTEND_URL", "https://app.example", "https://app.example"),
        ("DATABASE_URI", "postgresql://user@host/db", "postgresql://user@host/db"),
        ("DATABASE_URI", "postgresql://user:pw@host/db", f"postgresql://user:{HIDDEN}@host/db"),
        (
            "POSTGRES_URI_CUSTOM",
            "postgresql://user@host/db?password=pw&sslmode=require",
            f"postgresql://user@host/db?password={HIDDEN}&sslmode=require",
        ),
        (
            "DATABASE_URI",
            "postgresql://user@host/db?sslmode=require&sslpassword=pw",
            f"postgresql://user@host/db?sslmode=require&sslpassword={HIDDEN}",
        ),
        ("REDIS_URL", "redis://host:6379/0?token=t0k", f"redis://host:6379/0?token={HIDDEN}"),
        ("FRONTEND_URL", "https://app.example/?ref=a", "https://app.example/?ref=a"),
    ],
)
def test_what_is_hidden(name, value, shown) -> None:
    assert hide_secret(name, value) == shown


def _settings_classes(cls=BaseSettings):
    for sub in cls.__subclasses__():
        yield sub
        yield from _settings_classes(sub)


def test_every_settings_class_hides_its_secrets() -> None:
    # A settings class added later without the mixin would print its secrets again.
    ours = [c for c in _settings_classes() if c.__module__.startswith("src.")]
    assert {c.__name__ for c in ours} >= {
        "Settings",
        "PaymentSettings",
        "EmailConfig",
        "StorageSettings",
        "CleanupConfig",
    }
    assert [c.__name__ for c in ours if not issubclass(c, HidesSecrets)] == []
