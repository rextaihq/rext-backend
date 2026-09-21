import pytest
from pydantic import ValidationError

from src.api.config import Settings


def test_cors_rejects_wildcard_origin():
    """Verify that Settings rejects '*' in ALLOWED_ORIGINS."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            SECRET_KEY="x" * 32,
            REFRESH_SECRET_KEY="y" * 32,
            POSTGRES_URI_CUSTOM="postgresql://localhost/test",
            ALLOWED_ORIGINS="*",
        )
    assert "ALLOWED_ORIGINS cannot include '*'" in str(exc_info.value)


def test_cors_headers_parse_explicit_list():
    """Verify that settings correctly parses various CORS_ALLOWED_HEADERS strings."""
    # Test custom headers
    settings = Settings(
        SECRET_KEY="x" * 32,
        REFRESH_SECRET_KEY="y" * 32,
        POSTGRES_URI_CUSTOM="postgresql://localhost/test",
        CORS_ALLOWED_HEADERS="Authorization,Content-Type,X-Custom-Header",
    )
    assert settings.cors_allowed_headers_list == [
        "Authorization",
        "Content-Type",
        "X-Custom-Header",
    ]

    # Test whitespaces and empty values
    settings.CORS_ALLOWED_HEADERS = " Authorization ,  Content-Type ,, X-API-Key "
    assert settings.cors_allowed_headers_list == ["Authorization", "Content-Type", "X-API-Key"]
