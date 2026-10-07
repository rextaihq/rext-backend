"""The token signing secrets refuse public values (rext-control G58 #525).

.env.example is public, so a server whose secrets were copied from it would sign login
tokens with a secret anyone can read. The values below are made up for the test.
"""

import secrets
from pathlib import Path

import pytest
from pydantic import ValidationError

import src.api.config as config
from src.api.config import Settings

ROOT = Path(__file__).resolve().parents[2]
STRONG_ACCESS = secrets.token_hex(32)
STRONG_REFRESH = secrets.token_hex(32)


def _settings(**keys) -> Settings:
    return Settings(**{"SECRET_KEY": STRONG_ACCESS, "REFRESH_SECRET_KEY": STRONG_REFRESH, **keys})


def _refusal(**keys) -> str:
    with pytest.raises(ValidationError) as error:
        _settings(**keys)
    return str(error.value)


@pytest.mark.parametrize("field", ["SECRET_KEY", "REFRESH_SECRET_KEY"])
@pytest.mark.parametrize(
    "value",
    [
        # .env.example's former values, 42 and 50 characters long
        "replace_with_32_plus_characters_secret_key",
        "replace_with_32_plus_characters_refresh_secret_key",
        "REPLACE_WITH_ANY_TEXT_THAT_IS_LONG_ENOUGH_TO_PASS",
        # the short placeholders, now refused for what they are
        "your-secret-key-here",
        "changeme",
        "Secret",
        "password",
    ],
)
def test_a_placeholder_is_refused_whatever_its_length(field: str, value: str) -> None:
    message = _refusal(**{field: value})
    assert field in message
    assert "insecure placeholder value" in message


def test_a_value_in_the_example_file_is_refused(tmp_path: Path, monkeypatch) -> None:
    example = tmp_path / ".env.example"
    example.write_text(
        "# a comment=with an equals sign\nSOME_TOKEN='a-long-example-value-anyone-can-read-0123'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_ENV_EXAMPLE", example)

    message = _refusal(SECRET_KEY="a-long-example-value-anyone-can-read-0123")

    assert "insecure placeholder value" in message


def test_one_secret_for_both_tokens_is_refused() -> None:
    same = secrets.token_hex(32)
    message = _refusal(SECRET_KEY=same, REFRESH_SECRET_KEY=same)
    assert "must differ" in message
    # The check spans settings, and the error never quotes their input.
    assert same not in message


def test_an_error_never_shows_the_rejected_secret() -> None:
    short = "a-random-but-short-key-0042"
    message = _refusal(SECRET_KEY=short)
    assert "at least 32 characters" in message
    assert short not in message


def test_a_commented_example_value_is_refused(tmp_path: Path, monkeypatch) -> None:
    example = tmp_path / ".env.example"
    example.write_text(
        "# DATABASE_URL=postgresql://rext:rext@localhost:5432/rext_app\n", encoding="utf-8"
    )
    monkeypatch.setattr(config, "_ENV_EXAMPLE", example)

    message = _refusal(SECRET_KEY="postgresql://rext:rext@localhost:5432/rext_app")

    assert "insecure placeholder value" in message


def test_two_strong_different_secrets_are_accepted() -> None:
    settings = _settings()
    assert settings.SECRET_KEY == STRONG_ACCESS
    assert settings.REFRESH_SECRET_KEY == STRONG_REFRESH


def test_ordinary_settings_may_equal_their_example_values() -> None:
    """Only the two signing secrets are compared with the example file: a server whose
    ordinary settings match it (an environment name, a log level, a port, a Redis
    address) starts as before."""
    example = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    ordinary = [
        "ENVIRONMENT",
        "LOG_LEVEL",
        "HOST",
        "PORT",
        "ALGORITHM",
        "REDIS_URL",
        "FRONTEND_URL",
    ]
    values = {name: example[name].strip() for name in ordinary}

    settings = _settings(**values)

    for name, value in values.items():
        assert str(getattr(settings, name)) == value, name


def test_the_example_file_holds_no_signing_secret() -> None:
    # Empty, so a copied example can't start a server at all.
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    for key in ("SECRET_KEY", "REFRESH_SECRET_KEY"):
        assert f"{key}=" in lines, key
