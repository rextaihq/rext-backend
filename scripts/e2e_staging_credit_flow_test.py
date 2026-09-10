"""
End-to-End Staging Test: Workspace Credit Gate & Backend Deduction Flow.

Verifies:
1. Workspace Owner has 100 credits.
2. Workspace Member has 0 personal credits.
3. Member calls GET /api/v1/subscriptions/credits (personal) -> gets 0 credits.
4. Member calls GET /api/v1/subscriptions/credits?workspace_id={ws.id} (frontend credit gate) -> gets 100 credits and is_workspace_credits=True.
5. Unauthorized outsider is blocked from querying workspace credits (HTTP 403).
6. Member consumes credits in workspace (e.g. 15 credits for content generation) -> owner balance becomes 85, member personal balance remains 0.
7. Frontend credit balance refresh query returns 85 credits.
8. Consuming more credits than owner has raises InsufficientCreditsError.
9. Clean up test records.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import UUID, uuid4

os.environ["REXT_STORAGE_SKIP_BUCKET_CHECK"] = "1"

import httpx
from sqlalchemy import delete, select

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.api.server import app
from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.token_utils import create_access_token
from src.utils.credit_manager import (
    InsufficientCreditsError,
    _get_balance,
    consume_stage_credits,
)

BASE_URL = "http://127.0.0.1:2024"


async def run_e2e_test():
    print("=" * 70)
    print("STARTING E2E STAGING TEST: WORKSPACE OWNER CREDIT DELEGATION")
    print("=" * 70)

    test_run_id = uuid4().hex[:8]
    owner_id = uuid4()
    member_id = uuid4()
    outsider_id = uuid4()
    workspace_id = uuid4()
    plan_id = uuid4()

    owner_email = f"e2e_owner_{test_run_id}@example.com"
    member_email = f"e2e_member_{test_run_id}@example.com"
    outsider_email = f"e2e_outsider_{test_run_id}@example.com"

    print(f"\n[SETUP] Creating test users and subscriptions (Run ID: {test_run_id})...")

    async with get_async_db_context() as db:
        # 1. Create Subscription Plan
        plan = SubscriptionPlan(
            id=plan_id,
            name=f"plan_{test_run_id}",
            display_name="E2E Test Plan",
            price_monthly=2000,
            is_trial_plan=False,
            credits_per_month=1000,
        )
        db.add(plan)

        # 2. Create Users
        owner_user = Users(
            id=owner_id,
            email=owner_email,
            full_name="E2E Workspace Owner",
            status="active",
            email_verified=True,
        )
        member_user = Users(
            id=member_id,
            email=member_email,
            full_name="E2E Workspace Member",
            status="active",
            email_verified=True,
        )
        outsider_user = Users(
            id=outsider_id,
            email=outsider_email,
            full_name="E2E Outsider",
            status="active",
            email_verified=True,
        )
        db.add_all([owner_user, member_user, outsider_user])

        # 3. Create Subscriptions
        # OWNER: 100 credits
        owner_sub = UserSubscription(
            user_id=owner_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            current_credits=100,
            current_api_calls=0,
        )
        # MEMBER: STRICTLY 0 credits
        member_sub = UserSubscription(
            user_id=member_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            current_credits=0,
            current_api_calls=0,
        )
        db.add_all([owner_sub, member_sub])

        # 4. Create Workspace (Owned by Owner)
        workspace = WorkspaceModel(
            id=workspace_id,
            user_id=owner_id,
            name=f"E2E Workspace {test_run_id}",
            slug=f"e2e-ws-{test_run_id}",
            url=f"https://e2e-{test_run_id}.example.com",
        )
        db.add(workspace)

        # 5. Add Member to Workspace
        ws_member = WorkspaceMembers(
            id=uuid4(),
            user_id=member_id,
            workspace_id=workspace_id,
            status="active",
            is_default=False,
        )
        db.add(ws_member)

        # 6. Assign Member 'editor' role in workspace
        role_res = await db.execute(select(Role).where(Role.name == "editor"))
        editor_role = role_res.scalar_one_or_none()
        if editor_role:
            ur = UserRole(
                id=uuid4(),
                user_id=member_id,
                role_id=editor_role.id,
                workspace_id=workspace_id,
                is_primary=True,
            )
            db.add(ur)

        await db.commit()
        print("✓ Test entities successfully committed to staging database.")
        print(f"  - Owner:  {owner_email} (Personal credits: 100)")
        print(f"  - Member: {member_email} (Personal credits: 0)")
        print(f"  - Workspace: {workspace.name} (Owner ID: {owner_id})")

    # Generate Auth Tokens
    member_token = create_access_token({"id": str(member_id), "email": member_email, "session_kind": "test"})
    owner_token = create_access_token({"id": str(owner_id), "email": owner_email, "session_kind": "test"})
    outsider_token = create_access_token({"id": str(outsider_id), "email": outsider_email, "session_kind": "test"})

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
            # -------------------------------------------------------------
            # TEST STEP 1: Member checks personal credit account (No workspace_id)
            # -------------------------------------------------------------
            print("\n[STEP 1] Testing Member personal credits via HTTP API...")
            res_personal = await client.get(
                "/api/v1/subscriptions/credits",
                headers={"Authorization": f"Bearer {member_token}"},
            )
            assert res_personal.status_code == 200, f"Failed: {res_personal.text}"
            data_personal = res_personal.json().get("data", {})
            print(f"  Response: {data_personal}")
            assert data_personal.get("current_credits") == 0, "Expected 0 credits for member personal account"
            assert data_personal.get("is_workspace_credits") is False, "Expected is_workspace_credits=False"
            print("✓ PROOF 1: Member's personal credit balance is strictly 0.")

            # -------------------------------------------------------------
            # TEST STEP 2: Member checks active workspace credits (Frontend Credit Gate)
            # -------------------------------------------------------------
            print("\n[STEP 2] Testing Member workspace credit gate (with workspace_id)...")
            res_ws = await client.get(
                f"/api/v1/subscriptions/credits?workspace_id={workspace_id}",
                headers={"Authorization": f"Bearer {member_token}"},
            )
            assert res_ws.status_code == 200, f"Failed: {res_ws.text}"
            data_ws = res_ws.json().get("data", {})
            print(f"  Response: {data_ws}")
            assert data_ws.get("current_credits") == 100, f"Expected 100 credits, got {data_ws.get('current_credits')}"
            assert data_ws.get("is_workspace_credits") is True, "Expected is_workspace_credits=True"
            assert data_ws.get("target_user_id") == str(owner_id), "Expected target_user_id to be owner"
            print("✓ PROOF 2: Frontend Credit Gate receives 100 credits from workspace owner! Member is not blocked.")

            # -------------------------------------------------------------
            # TEST STEP 3: Security - Outsider querying workspace credits
            # -------------------------------------------------------------
            print("\n[STEP 3] Testing Security Gate (Outsider querying workspace credits)...")
            res_outsider = await client.get(
                f"/api/v1/subscriptions/credits?workspace_id={workspace_id}",
                headers={"Authorization": f"Bearer {outsider_token}"},
            )
            print(f"  Response Status: {res_outsider.status_code} ({res_outsider.json().get('error', {}).get('message')})")
            assert res_outsider.status_code == 403, f"Expected 403 Forbidden, got {res_outsider.status_code}"
            print("✓ PROOF 3: Unauthorized user is forbidden from accessing workspace owner credits.")

            # -------------------------------------------------------------
            # TEST STEP 4: Member executes generation stage (Backend Deduction)
            print("\n[STEP 4] Member executing content generation costing 15 credits...")
            await consume_stage_credits(
                user_id=str(member_id),
                cost=15,
                stage="content_generation",
                workspace_id=str(workspace_id),
            )
            print("  Credit deduction succeeded without error.")

            # Verify DB states directly
            async with get_async_db_context() as db:
                owner_sub_db = (
                    await db.execute(select(UserSubscription).where(UserSubscription.user_id == owner_id))
                ).scalar_one()
                member_sub_db = (
                    await db.execute(select(UserSubscription).where(UserSubscription.user_id == member_id))
                ).scalar_one()

                print(f"  Owner credits after deduction:  {owner_sub_db.current_credits} (was 100, -15)")
                print(f"  Member credits after deduction: {member_sub_db.current_credits} (was 0)")

                assert owner_sub_db.current_credits == 85, f"Expected owner to have 85 credits, got {owner_sub_db.current_credits}"
                assert member_sub_db.current_credits == 0, f"Expected member to still have 0 credits, got {member_sub_db.current_credits}"
                print("✓ PROOF 4: 15 credits deducted from Workspace Owner! Member personal balance remained at 0.")

            # -------------------------------------------------------------
            # TEST STEP 5: Live Frontend balance reflects updated owner balance
            # -------------------------------------------------------------
            print("\n[STEP 5] Checking live frontend credit balance via HTTP...")
            res_after = await client.get(
                f"/api/v1/subscriptions/credits?workspace_id={workspace_id}",
                headers={"Authorization": f"Bearer {member_token}"},
            )
            assert res_after.status_code == 200
            data_after = res_after.json().get("data", {})
            print(f"  Response: {data_after}")
            assert data_after.get("current_credits") == 85, f"Expected 85 credits, got {data_after.get('current_credits')}"
            print("✓ PROOF 5: Frontend widget sees updated balance (85 credits).")

            # -------------------------------------------------------------
            # TEST STEP 6: Insufficient Balance Protection
            # -------------------------------------------------------------
            print("\n[STEP 6] Testing Insufficient Balance Protection (cost=90, owner has 85)...")
            try:
                await consume_stage_credits(
                    user_id=str(member_id),
                    cost=90,
                    stage="heavy_video_generation",
                    workspace_id=str(workspace_id),
                )
                assert False, "Should have raised InsufficientCreditsError"
            except InsufficientCreditsError as e:
                print(f"  Successfully blocked: {e}")
                print("✓ PROOF 6: Overdraft properly prevented when owner balance is insufficient.")
    finally:
        # -------------------------------------------------------------
        # CLEANUP
        # -------------------------------------------------------------
        print("\n[CLEANUP] Removing test artifacts from database...")
        async with get_async_db_context() as db:
            await db.execute(delete(UserRole).where(UserRole.workspace_id == workspace_id))
            await db.execute(delete(WorkspaceMembers).where(WorkspaceMembers.workspace_id == workspace_id))
            await db.execute(delete(WorkspaceModel).where(WorkspaceModel.id == workspace_id))
            await db.execute(delete(UserSubscription).where(UserSubscription.user_id.in_([owner_id, member_id, outsider_id])))
            await db.execute(delete(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
            await db.execute(delete(Users).where(Users.id.in_([owner_id, member_id, outsider_id])))
            await db.commit()
        print("✓ Cleanup complete.")

    print("\n" + "=" * 70)
    print("ALL E2E STAGING PROOFS PASSED PERFECTLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
