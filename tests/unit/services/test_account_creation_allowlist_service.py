"""Mock-based unit tests for AccountCreationAllowlistService."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextValidationException,
)
from src.services.account_creation_allowlist_service import (
    AccountCreationAllowlistService,
)


class _Result:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows


@pytest.fixture
def db():
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.get = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture(autouse=True)
def fake_cache(monkeypatch):
    store = {}
    fake = MagicMock()
    fake.store = store
    fake.get = AsyncMock(side_effect=lambda k: store.get(k))
    fake.set = AsyncMock(side_effect=lambda k, v, ttl=None: store.__setitem__(k, v))
    fake.delete = AsyncMock(side_effect=lambda k: store.pop(k, None))
    monkeypatch.setattr(
        "src.services.account_creation_allowlist_service.cache", fake
    )
    return fake


@pytest.mark.asyncio
async def test_add_entry_normalizes_and_creates(db, fake_cache):
    db.execute.return_value = _Result(scalar=None)  # no existing row
    service = AccountCreationAllowlistService(db)

    admin_id = uuid4()
    entry = await service.add_entry(
        ip_address=" 203.0.113.5/24 ", label="  office  ", admin_user_id=admin_id
    )

    assert entry.ip_address == "203.0.113.0/24"
    assert entry.label == "office"
    assert entry.is_active is True
    assert entry.created_by == admin_id
    db.add.assert_called_once_with(entry)
    db.flush.assert_awaited()
    fake_cache.delete.assert_awaited_with(AccountCreationAllowlistService.CACHE_KEY)


@pytest.mark.asyncio
async def test_add_entry_rejects_invalid_ip(db):
    service = AccountCreationAllowlistService(db)
    with pytest.raises(RextValidationException):
        await service.add_entry(ip_address="not-an-ip")


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["192.168.1.10", "10.1.2.3", "172.16.0.1", "127.0.0.1"])
async def test_add_entry_rejects_private_addresses(db, value):
    """The allowlist holds public egress IPs, never internal/private ones."""
    db.execute.return_value = _Result(scalar=None)
    service = AccountCreationAllowlistService(db)
    with pytest.raises(RextValidationException):
        await service.add_entry(ip_address=value)


@pytest.mark.asyncio
async def test_add_entry_rejects_duplicate(db):
    db.execute.return_value = _Result(scalar=object())  # existing row found
    service = AccountCreationAllowlistService(db)
    with pytest.raises(DuplicateResourceException):
        await service.add_entry(ip_address="203.0.113.10")


@pytest.mark.asyncio
async def test_get_entry_missing_raises_not_found(db):
    db.get.return_value = None
    service = AccountCreationAllowlistService(db)
    with pytest.raises(ResourceNotFoundException):
        await service.get_entry(uuid4())


@pytest.mark.asyncio
async def test_update_entry_patches_fields_and_invalidates(db):
    existing = MagicMock(id=uuid4(), ip_address="203.0.113.10", label="old", is_active=True)
    db.get.return_value = existing
    service = AccountCreationAllowlistService(db)

    updated = await service.update_entry(existing.id, label="new", is_active=False)

    assert updated.label == "new"
    assert updated.is_active is False
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_delete_entry_removes_and_invalidates(db, fake_cache):
    existing = MagicMock(id=uuid4())
    db.get.return_value = existing
    service = AccountCreationAllowlistService(db)

    await service.delete_entry(existing.id)

    db.delete.assert_awaited_once_with(existing)
    fake_cache.delete.assert_awaited_with(AccountCreationAllowlistService.CACHE_KEY)


@pytest.mark.asyncio
async def test_active_ip_values_caches_db_result(db, fake_cache):
    db.execute.return_value = _Result(rows=[("203.0.113.10",), ("203.0.113.0/24",)])
    service = AccountCreationAllowlistService(db)

    first = await service._active_ip_values()
    assert first == ["203.0.113.10", "203.0.113.0/24"]
    assert fake_cache.store[AccountCreationAllowlistService.CACHE_KEY] == first

    # Second call is served from cache — no second DB hit.
    db.execute.reset_mock()
    second = await service._active_ip_values()
    assert second == first
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_is_ip_allowlisted_end_to_end(db):
    db.execute.return_value = _Result(rows=[("203.0.113.0/24",)])
    service = AccountCreationAllowlistService(db)

    assert await service.is_ip_allowlisted("203.0.113.42") is True
    assert await service.is_ip_allowlisted("198.51.100.1") is False
