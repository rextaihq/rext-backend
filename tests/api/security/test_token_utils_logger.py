"""
Regression tests for the `logger` NameError bug in
`src/api/security/token_utils.py`.

`is_token_blacklisted` used to reference a module-level `logger` that was
never imported. Under normal operation that branch is only reached on a
transient SASL/protocol-violation DB error, so the bug was invisible until
that error occurred — at which point `logger.error(...)` itself raised
`NameError: name 'logger' is not defined`, which replaced the original
`asyncpg.exceptions.ProtocolViolationError` as the exception seen by callers.
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.api.security import token_utils


def test_token_utils_module_has_logger_imported():
    """`logger` must exist on the module — this is what was missing."""
    assert hasattr(token_utils, "logger")


@pytest.mark.asyncio
async def test_is_token_blacklisted_propagates_original_sasl_error_not_nameerror():
    """
    The original DB/SASL exception must propagate unchanged — not be
    replaced by a NameError from the (previously broken) logging call.
    """
    db = AsyncMock()
    original_error = Exception(
        "asyncpg.exceptions.ProtocolViolationError: SASL authentication failed"
    )
    db.execute = AsyncMock(side_effect=original_error)

    with patch.object(token_utils, "logger") as mock_logger:
        with pytest.raises(Exception) as exc_info:
            await token_utils.is_token_blacklisted("some-jti", db)

        # Must be the ORIGINAL exception, not a NameError masking it.
        assert exc_info.value is original_error
        assert not isinstance(exc_info.value, NameError)

        # The diagnostic log call must have actually executed (proving
        # `logger` resolved correctly instead of raising).
        mock_logger.error.assert_called_once()
        _, kwargs = mock_logger.error.call_args
        assert kwargs["extra"]["jti"] == "some-jti"
        assert kwargs["exc_info"] is True


@pytest.mark.asyncio
async def test_is_token_blacklisted_propagates_non_sasl_db_errors_without_logging():
    """Non-SASL DB errors propagate too, but skip the SASL-only diagnostic branch."""
    db = AsyncMock()
    original_error = RuntimeError("connection reset by peer")
    db.execute = AsyncMock(side_effect=original_error)

    with patch.object(token_utils, "logger") as mock_logger:
        with pytest.raises(RuntimeError) as exc_info:
            await token_utils.is_token_blacklisted("some-jti", db)

        assert exc_info.value is original_error
        mock_logger.error.assert_not_called()
