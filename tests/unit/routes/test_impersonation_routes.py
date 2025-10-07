"""
Unit tests for impersonation API routes.

Tests the impersonation status endpoint with various JWT token scenarios.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from uuid import uuid4

from src.api.routes.users.impersonation import get_impersonation_status


@pytest.mark.asyncio
async def test_get_impersonation_status_not_impersonating():
    """Should return is_impersonating False when user is not impersonating."""
    # Arrange - Regular user without impersonation flag
    current_user = {
        "identity": str(uuid4()),
        "username": "regular_user",
        "email": "user@example.com",
        "roles": ["editor"],
        "permissions": ["content.read"],
    }
    
    # Act
    result = await get_impersonation_status(current_user=current_user)
    
    # Assert
    assert result == {"is_impersonating": False}


@pytest.mark.asyncio
async def test_get_impersonation_status_not_impersonating_explicit_false():
    """Should return is_impersonating False when flag is explicitly set to False."""
    # Arrange - User with explicit is_impersonating=False
    current_user = {
        "identity": str(uuid4()),
        "username": "regular_user",
        "email": "user@example.com",
        "roles": ["editor"],
        "permissions": ["content.read"],
        "is_impersonating": False,
    }
    
    # Act
    result = await get_impersonation_status(current_user=current_user)
    
    # Assert
    assert result == {"is_impersonating": False}


@pytest.mark.asyncio
async def test_get_impersonation_status_while_impersonating():
    """Should return full impersonation details when user is impersonating."""
    # Arrange - Admin user impersonating another user
    original_user_id = str(uuid4())
    impersonated_user_id = str(uuid4())
    started_at = datetime.utcnow()
    
    current_user = {
        "identity": impersonated_user_id,
        "username": "target_user",
        "email": "target@example.com",
        "roles": ["viewer"],
        "permissions": ["content.read"],
        "is_impersonating": True,
        "original_user_id": original_user_id,
        "impersonation_started_at": started_at,
    }
    
    # Act
    result = await get_impersonation_status(current_user=current_user)
    
    # Assert
    assert result["is_impersonating"] is True
    assert result["original_user_id"] == original_user_id
    assert result["impersonated_user_id"] == impersonated_user_id
    assert result["impersonated_user_email"] == "target@example.com"
    assert result["impersonated_user_name"] == "target_user"
    assert result["started_at"] == started_at


@pytest.mark.asyncio
async def test_get_impersonation_status_with_all_fields():
    """Should return all available fields when impersonating."""
    # Arrange - Full impersonation context
    original_user_id = str(uuid4())
    impersonated_user_id = str(uuid4())
    started_at = datetime(2025, 10, 7, 10, 0, 0)
    
    current_user = {
        "identity": impersonated_user_id,
        "username": "john_doe",
        "email": "john@example.com",
        "roles": ["editor", "viewer"],
        "permissions": ["content.read", "content.update"],
        "is_impersonating": True,
        "original_user_id": original_user_id,
        "impersonation_started_at": started_at,
    }
    
    # Act
    result = await get_impersonation_status(current_user=current_user)
    
    # Assert - Verify all fields present and correct
    assert result["is_impersonating"] is True
    assert result["original_user_id"] == original_user_id
    assert result["impersonated_user_id"] == impersonated_user_id
    assert result["impersonated_user_email"] == "john@example.com"
    assert result["impersonated_user_name"] == "john_doe"
    assert result["started_at"] == started_at


@pytest.mark.asyncio
async def test_get_impersonation_status_with_missing_optional_fields():
    """Should handle missing optional fields gracefully."""
    # Arrange - Minimal impersonation context (some fields missing)
    impersonated_user_id = str(uuid4())
    
    current_user = {
        "identity": impersonated_user_id,
        "username": "target_user",
        "email": "target@example.com",
        "is_impersonating": True,
        # Missing: original_user_id, impersonation_started_at
    }
    
    # Act
    result = await get_impersonation_status(current_user=current_user)
    
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
    result = await get_impersonation_status(current_user=current_user)
    
    # Assert
    assert result == {"is_impersonating": False}


@pytest.mark.asyncio
async def test_get_impersonation_status_response_structure():
    """Should return correct response structure matching ImpersonationStatusResponse schema."""
    # Arrange
    current_user = {
        "identity": str(uuid4()),
        "username": "target",
        "email": "target@example.com",
        "is_impersonating": True,
        "original_user_id": str(uuid4()),
        "impersonation_started_at": datetime.utcnow(),
    }
    
    # Act
    result = await get_impersonation_status(current_user=current_user)
    
    # Assert - Verify all expected keys exist
    expected_keys = {
        "is_impersonating",
        "original_user_id",
        "impersonated_user_id",
        "impersonated_user_email",
        "impersonated_user_name",
        "started_at",
    }
    assert set(result.keys()) == expected_keys

