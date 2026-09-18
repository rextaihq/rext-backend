import warnings
from datetime import timedelta

import pytest

from src.api.security.token_utils import (
    VerifiedToken,
    create_access_token,
    decode_and_verify_token,
    verify_token,
)


def test_decode_and_verify_token_valid():
    """Test that decode_and_verify_token works for valid tokens."""
    data = {"sub": "testuser", "test_claims": "true"}
    token = create_access_token(data=data)

    payload = decode_and_verify_token(token)
    assert payload["sub"] == "testuser"
    assert payload["test_claims"] == "true"
    assert "exp" in payload
    assert "jti" in payload


def test_verify_token_deprecated():
    """Test that verify_token still works but emits a DeprecationWarning."""
    data = {"sub": "testuser_dep"}
    token = create_access_token(data=data)

    with pytest.warns(DeprecationWarning, match="verify_token\(\) is deprecated"):
        payload = verify_token(token)
        assert payload["sub"] == "testuser_dep"


def test_verified_token_type_alias_exists():
    """Test that VerifiedToken type alias exists."""
    # This is a static check mainly, but ensures it can be imported
    assert VerifiedToken is not None
