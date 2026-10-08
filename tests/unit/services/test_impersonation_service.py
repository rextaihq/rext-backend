"""Unit tests for ImpersonationService."""

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextAuthenticationException,
    RextValidationException,
)
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.users import Users
from src.services.impersonation_service import ImpersonationService


class FakeScalarSequence:
    """Helper to mimic SQLAlchemy scalar sequence results."""

    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


class FakeResult:
    """Helper to mimic SQLAlchemy Result objects."""

    def __init__(self, *, scalar=None, scalars=None, rows=None):
        self._scalar = scalar
        self._scalars = scalars or []
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def first(self):
        return self._scalar

    def scalars(self):
        return FakeScalarSequence(self._scalars)

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_start_impersonation_successful_flow():
    """start_impersonation should return payload with impersonation metadata."""
    mock_db = AsyncMock()
    service = ImpersonationService(mock_db)

    admin_id = uuid4()
    target_id = uuid4()

    admin_user = Users(
        id=admin_id,
        email="admin@example.com",
        password_hash="hash",
    )
    admin_user.status = "active"
    target_user = Users(
        id=target_id,
        email="target@example.com",
        password_hash="hash",
    )
    target_user.status = "active"
    target_user.email_verified = True
    target_user.display_name = "Target Name"

    service._get_user_or_404 = AsyncMock(side_effect=[admin_user, target_user])
    service._has_impersonation_permission = AsyncMock(return_value=True)
    service._get_max_hierarchy_level = AsyncMock(side_effect=[5, 2])
    service._build_context_from_user = AsyncMock(
        return_value={
            "user_id": str(target_id),
            "email": "target@example.com",
            "full_name": "Target Full Name",
            "display_name": "Target Name",
            "roles": ["admin"],
            "permissions": ["user.impersonate"],
        },
    )

    payload = await service.start_impersonation(admin_id, target_id)

    assert payload["target_user_id"] == str(target_id)
    assert payload["impersonated_by"] == str(admin_id)
    assert payload["roles"] == ["admin"]
    assert payload["target_display_name"] == "Target Name"
    service._has_impersonation_permission.assert_awaited_once_with(admin_id)


@pytest.mark.asyncio
async def test_start_impersonation_prevents_self_impersonation():
    """start_impersonation should raise when admin attempts to impersonate themselves."""
    mock_db = AsyncMock()
    service = ImpersonationService(mock_db)

    admin_id = uuid4()
    admin_user = Users(
        id=admin_id,
        email="admin@example.com",
        password_hash="hash",
    )

    service._get_user_or_404 = AsyncMock(side_effect=[admin_user, admin_user])

    with pytest.raises(RextValidationException):
        await service.start_impersonation(admin_id, admin_id)


@pytest.mark.asyncio
async def test_start_impersonation_rejects_unverified_target():
    """start_impersonation should raise when the target's email is not verified."""
    mock_db = AsyncMock()
    service = ImpersonationService(mock_db)

    admin_id = uuid4()
    target_id = uuid4()

    admin_user = Users(
        id=admin_id,
        email="admin@example.com",
        password_hash="hash",
    )
    admin_user.status = "active"
    target_user = Users(
        id=target_id,
        email="target@example.com",
        password_hash="hash",
    )
    target_user.status = "active"
    target_user.email_verified = False

    service._get_user_or_404 = AsyncMock(side_effect=[admin_user, target_user])
    service._has_impersonation_permission = AsyncMock(return_value=True)

    with pytest.raises(RextValidationException, match="verified"):
        await service.start_impersonation(admin_id, target_id)


@pytest.mark.asyncio
async def test_start_impersonation_requires_permission():
    """Should raise authentication exception when permission missing."""
    mock_db = AsyncMock()
    service = ImpersonationService(mock_db)

    admin_id = uuid4()
    target_id = uuid4()

    admin_user = Users(
        id=admin_id,
        email="admin@example.com",
        password_hash="hash",
    )
    admin_user.status = "active"
    target_user = Users(
        id=target_id,
        email="target@example.com",
        password_hash="hash",
    )
    target_user.status = "active"
    target_user.display_name = "Target Name"

    service._get_user_or_404 = AsyncMock(side_effect=[admin_user, target_user])
    service._has_impersonation_permission = AsyncMock(return_value=False)

    with pytest.raises(RextAuthenticationException):
        await service.start_impersonation(admin_id, target_id)


@pytest.mark.asyncio
async def test_stop_impersonation_returns_confirmation():
    """stop_impersonation should return confirmation payload."""
    service = ImpersonationService(db=AsyncMock())

    payload = await service.stop_impersonation(uuid4(), uuid4())

    assert payload["message"] == "Impersonation stopped"
    assert "impersonation_stopped_at" in payload


@pytest.mark.asyncio
async def test_get_impersonation_status_handles_non_impersonating_state():
    """Should return simple payload when not impersonating."""
    service = ImpersonationService(db=AsyncMock())
    user_id = uuid4()

    payload = await service.get_impersonation_status(user_id)

    assert payload == {"is_impersonating": False, "user_id": str(user_id)}


@pytest.mark.asyncio
async def test_get_impersonation_status_includes_impersonator_details():
    """Should include impersonator information when IDs provided."""
    mock_db = AsyncMock()
    service = ImpersonationService(mock_db)

    user = Users(
        id=uuid4(),
        email="user@example.com",
        password_hash="hash",
    )
    impersonator = Users(
        id=uuid4(),
        email="admin@example.com",
        password_hash="hash",
    )

    service._get_user_or_404 = AsyncMock(side_effect=[user, impersonator])

    payload = await service.get_impersonation_status(user.id, impersonator.id)

    assert payload["is_impersonating"] is True
    assert payload["impersonated_by_email"] == "admin@example.com"


@pytest.mark.asyncio
async def test_get_user_or_404_raises_when_missing():
    """_get_user_or_404 should raise ResourceNotFoundException when user not found."""
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)

    service = ImpersonationService(mock_db)

    with pytest.raises(ResourceNotFoundException):
        await service._get_user_or_404(uuid4())


@pytest.mark.asyncio
async def test_has_impersonation_permission_queries_permissions():
    """_has_impersonation_permission returns True when permission exists."""
    mock_db = AsyncMock()
    permission = Permission(name="user.impersonate")
    mock_db.execute.return_value = FakeResult(scalar=permission)

    service = ImpersonationService(mock_db)

    assert await service._has_impersonation_permission(uuid4()) is True


@pytest.mark.asyncio
async def test_has_impersonation_permission_returns_false_when_missing():
    """_has_impersonation_permission returns False when no record found."""
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)

    service = ImpersonationService(mock_db)

    assert await service._has_impersonation_permission(uuid4()) is False


@pytest.mark.asyncio
async def test_get_max_hierarchy_level_defaults_to_zero():
    """_get_max_hierarchy_level should return 0 when user has no roles."""
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)

    service = ImpersonationService(mock_db)

    assert await service._get_max_hierarchy_level(uuid4()) == 0


@pytest.mark.asyncio
async def test_get_auth_context_returns_roles_and_permissions():
    """_get_auth_context should return role and permission names."""
    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        FakeResult(rows=[("admin",), ("editor",)]),
        FakeResult(rows=[("user.invite",), ("user.impersonate",)]),
    ]

    service = ImpersonationService(mock_db)

    context = await service._get_auth_context(uuid4())

    assert context["roles"] == ["admin", "editor"]
    assert "user.impersonate" in context["permissions"]


@pytest.mark.asyncio
async def test_get_user_context_aggregates_user_and_auth_data():
    """get_user_context should combine user profile with access metadata."""
    mock_db = AsyncMock()
    service = ImpersonationService(mock_db)

    user = Users(
        id=uuid4(),
        email="user@example.com",
        password_hash="hash",
    )
    user.display_name = "User Example"

    service._get_user_or_404 = AsyncMock(return_value=user)
    service._get_auth_context = AsyncMock(
        return_value={
            "roles": ["editor"],
            "permissions": ["content.edit"],
        }
    )

    context = await service.get_user_context(user.id)

    assert context["user_id"] == str(user.id)
    assert context["display_name"] == "User Example"
    assert context["roles"] == ["editor"]
