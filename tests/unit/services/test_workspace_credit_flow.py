"""
Unit tests for workspace credit flow and resolution.

Tests cover:
- resolve_credit_owner_id: verifies active workspace membership and resolves to workspace.user_id
- non-members are blocked from using workspace credits
- members consuming credits in active workspace deduct from workspace owner, leaving personal credits untouched
- cross-workspace credit isolation (Workspace 1 vs Workspace 2)
- workspace owner using their own workspace deducts from their own credits
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.usage_tracking_service import UsageTrackingService
from src.utils.credit_manager import (
    InsufficientCreditsError,
    consume_stage_credits,
    resolve_credit_owner_id,
)


@pytest.mark.unit
class TestResolveCreditOwnerId:
    """Tests for resolve_credit_owner_id helper"""

    async def test_resolve_without_workspace_returns_user_id(self, db_session):
        """When workspace_id is None, personal credit account is used"""
        uid = uuid4()
        resolved = await resolve_credit_owner_id(db_session, uid, None)
        assert resolved == uid

    async def test_resolve_owner_in_own_workspace(self, db_session, setup_factories):
        """When workspace creator/owner uses workspace, resolves to workspace.user_id"""
        owner = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)

        resolved = await resolve_credit_owner_id(db_session, owner.id, str(workspace.id))
        assert resolved == owner.id

    async def test_resolve_active_member_resolves_to_owner(self, db_session, setup_factories):
        """When an active member uses workspace, resolves to the workspace owner (workspace.user_id)"""
        owner = await setup_factories["user"].create()
        member = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=member.id, status="active"
        )

        resolved = await resolve_credit_owner_id(db_session, member.id, str(workspace.id))
        assert resolved == owner.id

    async def test_resolve_non_member_blocked(self, db_session, setup_factories):
        """When user is not a member of the workspace, access is blocked"""
        owner = await setup_factories["user"].create()
        non_member = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)

        with pytest.raises(InsufficientCreditsError) as exc_info:
            await resolve_credit_owner_id(db_session, non_member.id, str(workspace.id))

        assert exc_info.value.stage == "workspace_access"

    async def test_resolve_inactive_member_blocked(self, db_session, setup_factories):
        """When user has inactive membership, access is blocked"""
        owner = await setup_factories["user"].create()
        inactive_member = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=inactive_member.id, status="inactive"
        )

        with pytest.raises(InsufficientCreditsError) as exc_info:
            await resolve_credit_owner_id(db_session, inactive_member.id, str(workspace.id))

        assert exc_info.value.stage == "workspace_access"

    async def test_resolve_nonexistent_workspace_blocked(self, db_session, setup_factories):
        """When workspace does not exist, access is blocked"""
        user = await setup_factories["user"].create()
        fake_ws_id = str(uuid4())

        with pytest.raises(InsufficientCreditsError) as exc_info:
            await resolve_credit_owner_id(db_session, user.id, fake_ws_id)

        assert exc_info.value.stage == "workspace_access"


@pytest.mark.unit
class TestWorkspaceCreditConsumption:
    """Tests for credit consumption in workspace context"""

    @pytest.fixture
    async def sample_plan(self, db_session):
        plan = SubscriptionPlan(
            id=uuid4(),
            name=f"plan_{uuid4().hex[:8]}",
            display_name="Test Plan",
            price_monthly=2000,
            is_trial_plan=False,
            credits_per_month=1000,
        )
        db_session.add(plan)
        await db_session.flush()
        return plan

    async def test_member_consumes_from_workspace_owner(self, db_session, setup_factories, sample_plan):
        """Member content generation consumes from workspace owner, member's balance untouched"""
        owner = await setup_factories["user"].create()
        member = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=member.id, status="active"
        )

        # Owner has 100 credits
        owner_sub = UserSubscription(
            user_id=owner.id,
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            current_credits=100,
            current_api_calls=0,
        )
        # Member has 50 credits in personal account
        member_sub = UserSubscription(
            user_id=member.id,
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            current_credits=50,
            current_api_calls=0,
        )
        db_session.add_all([owner_sub, member_sub])
        await db_session.commit()

        # Member triggers consumption of 10 credits in active workspace
        await consume_stage_credits(
            user_id=str(member.id),
            cost=10,
            stage="test_generation",
            workspace_id=str(workspace.id),
        )

        async with get_async_db_context() as verify_db:
            owner_sub_db = (
                await verify_db.execute(
                    select(UserSubscription).where(UserSubscription.user_id == owner.id)
                )
            ).scalar_one()
            member_sub_db = (
                await verify_db.execute(
                    select(UserSubscription).where(UserSubscription.user_id == member.id)
                )
            ).scalar_one()

            # Owner's balance reduced by 10 (100 -> 90)
            assert owner_sub_db.current_credits == 90
            # Member's balance is untouched (50)
            assert member_sub_db.current_credits == 50

    async def test_cross_workspace_credit_isolation(self, db_session, setup_factories, sample_plan):
        """Member working across two workspaces deducts from each respective owner"""
        owner_a = await setup_factories["user"].create()
        owner_b = await setup_factories["user"].create()
        member = await setup_factories["user"].create()

        ws_a = await setup_factories["workspace"].create(user_id=owner_a.id)
        ws_b = await setup_factories["workspace"].create(user_id=owner_b.id)

        # Member belongs to both workspaces
        await setup_factories["workspace_member"].create(
            workspace_id=ws_a.id, user_id=member.id, status="active"
        )
        await setup_factories["workspace_member"].create(
            workspace_id=ws_b.id, user_id=member.id, status="active"
        )

        sub_a = UserSubscription(
            user_id=owner_a.id,
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            current_credits=200,
            current_api_calls=0,
        )
        sub_b = UserSubscription(
            user_id=owner_b.id,
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            current_credits=300,
            current_api_calls=0,
        )
        db_session.add_all([sub_a, sub_b])
        await db_session.commit()

        # Member consumes 30 credits in Workspace A
        await consume_stage_credits(
            user_id=str(member.id), cost=30, stage="ws_a_stage", workspace_id=str(ws_a.id)
        )

        # Member consumes 50 credits in Workspace B
        await consume_stage_credits(
            user_id=str(member.id), cost=50, stage="ws_b_stage", workspace_id=str(ws_b.id)
        )

        async with get_async_db_context() as verify_db:
            sub_a_db = (
                await verify_db.execute(
                    select(UserSubscription).where(UserSubscription.user_id == owner_a.id)
                )
            ).scalar_one()
            sub_b_db = (
                await verify_db.execute(
                    select(UserSubscription).where(UserSubscription.user_id == owner_b.id)
                )
            ).scalar_one()

            assert sub_a_db.current_credits == 170  # 200 - 30
            assert sub_b_db.current_credits == 250  # 300 - 50

    async def test_owner_insufficient_credits_raises_error(self, db_session, setup_factories, sample_plan):
        """When workspace owner has insufficient credits, member action fails with InsufficientCreditsError"""
        owner = await setup_factories["user"].create()
        member = await setup_factories["user"].create()
        workspace = await setup_factories["workspace"].create(user_id=owner.id)
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id, user_id=member.id, status="active"
        )

        owner_sub = UserSubscription(
            user_id=owner.id,
            plan_id=sample_plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            current_credits=2,  # Only 2 credits
            current_api_calls=0,
        )
        db_session.add(owner_sub)
        await db_session.commit()

        # Consuming 10 credits should raise InsufficientCreditsError
        with pytest.raises(InsufficientCreditsError):
            await consume_stage_credits(
                user_id=str(member.id), cost=10, stage="expensive_stage", workspace_id=str(workspace.id)
            )
