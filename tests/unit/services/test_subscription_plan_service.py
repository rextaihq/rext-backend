"""Unit tests for SubscriptionPlanService."""

from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextAPIException,
    WrextValidationException,
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.schema.subscription import SubscriptionPlanCreate, SubscriptionPlanUpdate
from src.services.subscription_plan_service import SubscriptionPlanService


class FakeResult:
    def __init__(self, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        class _Seq:
            def __init__(self, items):
                self._items = items

            def all(self):
                return self._items

        return _Seq(self._scalars)

    def all(self):
        return self._scalars


@pytest.mark.asyncio
async def test_require_admin_raises_for_non_admin():
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)
    service = SubscriptionPlanService(mock_db)

    with pytest.raises(WrextAPIException):
        await service.require_admin(uuid4())


@pytest.mark.asyncio
async def test_create_plan_persists_plan():
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    service = SubscriptionPlanService(mock_db)

    payload = SubscriptionPlanCreate(
        name="pro",
        display_name="Pro",
        description="desc",
        price_monthly=1,
        price_yearly=10,
    )

    result = await service.create_plan(payload)

    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()
    mock_db.refresh.assert_awaited_once()
    assert result["plan"]["name"] == "pro"


@pytest.mark.asyncio
async def test_create_plan_duplicate_raises():
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=SubscriptionPlan(id=uuid4()))
    service = SubscriptionPlanService(mock_db)

    payload = SubscriptionPlanCreate(
        name="existing",
        display_name="Existing",
        description=None,
        price_monthly=0,
        price_yearly=0,
    )

    with pytest.raises(DuplicateResourceException):
        await service.create_plan(payload)


@pytest.mark.asyncio
async def test_get_plan_enforces_visibility_for_non_admin():
    plan = SubscriptionPlan(
        id=uuid4(),
        name="hidden",
        display_name="Hidden",
        is_active=False,
        is_public=False,
        created_at=datetime.utcnow(),
    )
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=plan)
    service = SubscriptionPlanService(mock_db)

    with pytest.raises(WrextAPIException):
        await service.get_plan(plan.id, is_admin=False)


@pytest.mark.asyncio
async def test_get_plan_includes_active_counts_for_admin():
    plan = SubscriptionPlan(
        id=uuid4(),
        name="pro",
        display_name="Pro",
        is_active=True,
        is_public=True,
        created_at=datetime.utcnow(),
    )
    count_result = FakeResult(scalar=5)
    mock_db = AsyncMock()
    mock_db.execute.side_effect = [FakeResult(scalar=plan), count_result]
    service = SubscriptionPlanService(mock_db)

    data = await service.get_plan(plan.id, is_admin=True)

    assert data["active_subscriptions"] == 5


@pytest.mark.asyncio
async def test_update_plan_requires_fields():
    plan = SubscriptionPlan(
        id=uuid4(),
        name="pro",
        display_name="Pro",
        created_at=datetime.utcnow(),
    )
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=plan)
    service = SubscriptionPlanService(mock_db)

    with pytest.raises(WrextValidationException):
        await service.update_plan(plan.id, SubscriptionPlanUpdate())


@pytest.mark.asyncio
async def test_delete_plan_blocks_without_force():
    plan = SubscriptionPlan(
        id=uuid4(),
        name="pro",
        display_name="Pro",
        created_at=datetime.utcnow(),
    )
    mock_db = AsyncMock()
    mock_db.execute.side_effect = [FakeResult(scalar=plan), FakeResult(scalar=1)]
    service = SubscriptionPlanService(mock_db)

    with pytest.raises(WrextValidationException):
        await service.delete_plan(plan.id, force=False)


@pytest.mark.asyncio
async def test_delete_plan_succeeds_with_force():
    plan = SubscriptionPlan(
        id=uuid4(),
        name="pro",
        display_name="Pro",
        created_at=datetime.utcnow(),
    )
    mock_db = AsyncMock()
    mock_db.execute.side_effect = [FakeResult(scalar=plan), FakeResult(scalar=0)]
    mock_db.flush = AsyncMock()
    service = SubscriptionPlanService(mock_db)

    result = await service.delete_plan(plan.id, force=True)

    mock_db.delete.assert_awaited_once_with(plan)
    assert result["plan_name"] == "Pro"
