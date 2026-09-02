"""Unit tests for PermissionService."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.api.middleware.exceptions import RextValidationException
from src.api.models.user_models.permissions import Permission
from src.api.schema.permission_schema import PermissionCreate, PermissionUpdate
from src.services.permission_service import PermissionService


class FakeScalarSequence:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, *, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return FakeScalarSequence(self._scalars)


@pytest.mark.asyncio
async def test_list_permissions_includes_roles_when_requested():
    mock_db = AsyncMock()
    service = PermissionService(mock_db)

    permission = Permission(
        name="content.create",
        display_name="Create Content",
        description="",
        resource="content",
        action="create",
    )

    mock_db.execute.return_value = FakeResult(scalars=[permission])
    service._ensure_user_can = AsyncMock()
    service._serialize_permission_with_roles = AsyncMock(
        return_value={"name": "content.create", "roles": []}
    )

    result = await service.list_permissions(user_id=uuid4(), resource=None, include_roles=True)

    service._ensure_user_can.assert_awaited_once()
    service._serialize_permission_with_roles.assert_awaited_once()
    assert result["data"]["count"] == 1


@pytest.mark.asyncio
async def test_create_permission_validates_and_persists():
    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    service = PermissionService(mock_db)

    service._ensure_user_can = AsyncMock()
    service._ensure_unique_name = AsyncMock()

    payload = PermissionCreate(
        name="content.create",
        display_name="Create Content",
        description="",
        resource="content",
        action="create",
    )

    result = await service.create_permission(user_id=uuid4(), payload=payload)

    service._ensure_user_can.assert_awaited_once()
    service._ensure_unique_name.assert_awaited_once()
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()
    mock_db.refresh.assert_awaited_once()
    assert "permission" in result["data"]


@pytest.mark.asyncio
async def test_update_permission_updates_name_when_resource_changes():
    mock_db = AsyncMock()
    service = PermissionService(mock_db)

    permission = Permission(
        name="content.read",
        display_name="Read Content",
        description="",
        resource="content",
        action="read",
    )

    service._ensure_user_can = AsyncMock()
    service._get_permission_or_404 = AsyncMock(return_value=permission)
    service._ensure_unique_name = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    payload = PermissionUpdate(resource="content", action="view")

    result = await service.update_permission(
        user_id=uuid4(), permission_id=uuid4(), payload=payload
    )

    assert permission.action == "view"
    assert permission.name == "content.view"
    service._ensure_unique_name.assert_awaited_once()
    mock_db.flush.assert_awaited_once()
    mock_db.refresh.assert_awaited_once()
    assert "permission" in result["data"]


@pytest.mark.asyncio
async def test_delete_permission_raises_when_assigned():
    mock_db = AsyncMock()
    service = PermissionService(mock_db)

    permission = Permission(
        name="content.delete",
        display_name="Delete Content",
        description="",
        resource="content",
        action="delete",
    )

    service._ensure_user_can = AsyncMock()
    service._get_permission_or_404 = AsyncMock(return_value=permission)
    mock_db.execute.return_value = FakeResult(scalar=2)

    with pytest.raises(RextValidationException):
        await service.delete_permission(user_id=uuid4(), permission_id=uuid4())


@pytest.mark.asyncio
async def test_delete_permission_removes_permission_when_unassigned():
    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    service = PermissionService(mock_db)

    permission = Permission(
        name="content.delete",
        display_name="Delete Content",
        description="",
        resource="content",
        action="delete",
    )

    service._ensure_user_can = AsyncMock()
    service._get_permission_or_404 = AsyncMock(return_value=permission)
    mock_db.execute.return_value = FakeResult(scalar=0)

    result = await service.delete_permission(user_id=uuid4(), permission_id=uuid4())

    mock_db.delete.assert_called_once_with(permission)
    mock_db.flush.assert_awaited_once()
    assert "permission_id" in result["data"]
