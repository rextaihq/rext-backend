"""
Unit tests for impersonation API routes.

Tests the impersonation status endpoint with various JWT token scenarios.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.routes.users.impersonation import get_impersonation_status
from src.services.impersonation_service import ImpersonationService


async def _status(current_user: dict, *, session_valid: bool = True) -> dict:
    """The route's data, as the client reads it from the response envelope."""
    with patch.object(
        ImpersonationService, "is_session_valid", AsyncMock(return_value=session_valid)
    ):
        response = await get_impersonation_status(
            request=None, db=AsyncMock(), current_user=current_user
        )
    return json.loads(response.body)["data"]


@pytest.mark.asyncio
async def test_get_impersonation_status_not_impersonating():
    """Should return is_impersonating False when user is not impersonating."""
    # Arrange - Regular user without impersonation flag
    current_user = {
        "identity": str(uuid4()),
        "full_name": "regular_user",
        "email": "user@example.com",
        "roles": ["editor"],
        "permissions": ["content.read"],
    }

    # Act
    result = await _status(current_user)

    # Assert
    assert result == {"is_impersonating": False}


@pytest.mark.asyncio
async def test_get_impersonation_status_not_impersonating_explicit_false():
    """Should return is_impersonating False when flag is explicitly set to False."""
    # Arrange - User with explicit is_impersonating=False
    current_user = {
        "identity": str(uuid4()),
        "full_name": "regular_user",
        "email": "user@example.com",
        "roles": ["editor"],
        "permissions": ["content.read"],
        "is_impersonating": False,
    }

    # Act
    result = await _status(current_user)

    # Assert
    assert result == {"is_impersonating": False}


@pytest.mark.asyncio
async def test_get_impersonation_status_while_impersonating():
    """Should return full impersonation details when user is impersonating."""
    # Arrange - Admin user impersonating another user
    original_user_id = str(uuid4())
    impersonated_user_id = str(uuid4())
    started_at = datetime.now(timezone.utc)

    current_user = {
        "identity": impersonated_user_id,
        "full_name": "target_user",
        "email": "target@example.com",
        "roles": ["viewer"],
        "permissions": ["content.read"],
        "is_impersonating": True,
        "original_user_id": original_user_id,
        "impersonation_started_at": started_at,
    }

    # Act
    result = await _status(current_user)

    # Assert
    assert result["is_impersonating"] is True
    assert result["original_user_id"] == original_user_id
    assert result["impersonated_user_id"] == impersonated_user_id
    assert result["impersonated_user_email"] == "target@example.com"
    assert result["impersonated_user_name"] == "target_user"
    assert result["started_at"] == started_at.isoformat()


@pytest.mark.asyncio
async def test_get_impersonation_status_with_all_fields():
    """Should return all available fields when impersonating."""
    # Arrange - Full impersonation context
    original_user_id = str(uuid4())
    impersonated_user_id = str(uuid4())
    started_at = datetime(2025, 10, 7, 10, 0, 0, tzinfo=timezone.utc)

    current_user = {
        "identity": impersonated_user_id,
        "full_name": "john_doe",
        "email": "john@example.com",
        "roles": ["editor", "viewer"],
        "permissions": ["content.read", "content.update"],
        "is_impersonating": True,
        "original_user_id": original_user_id,
        "impersonation_started_at": started_at,
    }

    # Act
    result = await _status(current_user)

    # Assert - Verify all fields present and correct
    assert result["is_impersonating"] is True
    assert result["original_user_id"] == original_user_id
    assert result["impersonated_user_id"] == impersonated_user_id
    assert result["impersonated_user_email"] == "john@example.com"
    assert result["impersonated_user_name"] == "john_doe"
    assert result["started_at"] == started_at.isoformat()


@pytest.mark.asyncio
async def test_get_impersonation_status_with_missing_optional_fields():
    """Should handle missing optional fields gracefully."""
    # Arrange - Minimal impersonation context (some fields missing)
    impersonated_user_id = str(uuid4())

    current_user = {
        "identity": impersonated_user_id,
        "full_name": "target_user",
        "email": "target@example.com",
        "is_impersonating": True,
        # Missing: original_user_id, impersonation_started_at
    }

    # Act
    result = await _status(current_user)

    # Assert - Should still work with None values for missing fields
    assert result["is_impersonating"] is True
    assert result["original_user_id"] is None
    assert result["impersonated_user_id"] == impersonated_user_id
    assert result["impersonated_user_email"] == "target@example.com"
    assert result["impersonated_user_name"] == "target_user"
    assert result["started_at"] is None


@pytest.mark.asyncio
async def test_get_impersonation_status_empty_user_dict():
    """Should handle empty user dict and return not impersonating."""
    # Arrange - Empty or minimal user dict
    current_user = {}

    # Act
    result = await _status(current_user)

    # Assert
    assert result == {"is_impersonating": False}


@pytest.mark.asyncio
async def test_get_impersonation_status_response_structure():
    """Should return correct response structure matching ImpersonationStatusResponse schema."""
    # Arrange
    current_user = {
        "identity": str(uuid4()),
        "full_name": "target",
        "email": "target@example.com",
        "is_impersonating": True,
        "original_user_id": str(uuid4()),
        "impersonation_started_at": datetime.now(timezone.utc),
    }

    # Act
    result = await _status(current_user)

    # Assert - Verify all expected keys exist
    expected_keys = {
        "is_impersonating",
        "original_user_id",
        "impersonated_user_id",
        "impersonated_user_email",
        "impersonated_user_name",
        "started_at",
        "session_id",
    }
    assert set(result.keys()) == expected_keys


@pytest.mark.asyncio
async def test_get_impersonation_status_refuses_an_ended_session():
    """A token from an impersonation session that has been ended gets a 401."""
    current_user = {
        "identity": str(uuid4()),
        "email": "target@example.com",
        "is_impersonating": True,
        "original_user_id": str(uuid4()),
        "session_id": str(uuid4()),
    }

    with pytest.raises(HTTPException) as error:
        await _status(current_user, session_valid=False)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_get_impersonation_status_reports_a_live_session():
    session_id = str(uuid4())
    current_user = {
        "identity": str(uuid4()),
        "email": "target@example.com",
        "is_impersonating": True,
        "original_user_id": str(uuid4()),
        "session_id": session_id,
    }

    result = await _status(current_user)

    assert result["is_impersonating"] is True
    assert result["session_id"] == session_id
