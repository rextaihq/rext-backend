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


def test_two_strong_different_secrets_are_accepted() -> None:
    settings = _settings()
    assert settings.SECRET_KEY == STRONG_ACCESS
    assert settings.REFRESH_SECRET_KEY == STRONG_REFRESH


def test_a_short_secret_is_still_refused() -> None:
    assert "at least 32 characters" in _refusal(SECRET_KEY="a-random-but-short-key")


def test_the_example_file_holds_no_signing_secret() -> None:
    # Empty, so a copied example can't start a server at all.
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    for key in ("SECRET_KEY", "REFRESH_SECRET_KEY"):
        assert f"{key}=" in lines, key
