"""
Tests for Data Export Route
"""

from uuid import uuid4

import pytest

from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.users import Users
from src.api.security.token_utils import create_access_token


def generate_test_token(user_id, email: str) -> str:
    token_data = {
        "id": str(user_id),
        "identity": str(user_id),
        "sub": str(user_id),
        "email": email,
        "roles": ["user"],
        "permissions": [],
    }
    return create_access_token(token_data)


@pytest.mark.asyncio
async def test_user_data_export_full(client, db_session):
    """
    Test user data export endpoint including all payload elements.
    """
    # Create user
    user_id = uuid4()
    user = Users(
        id=user_id,
        email="exporttest@test.com",
        full_name="Export Test",
        status="active",
        email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    plan = SubscriptionPlan(
        id=uuid4(),
        name="Pro",
        display_name="Pro Plan",
        price_monthly=10.0,
        price_yearly=100.0,
        is_active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    subscription = UserSubscription(
        user_id=user_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        billing_period=BillingPeriod.MONTHLY,
    )
    db_session.add(subscription)

    # Create an audit log
    audit_log = AuditLog(
        user_id=user_id, action="user.login", resource_type="auth", status="success"
    )
    db_session.add(audit_log)

    await db_session.flush()

    token = generate_test_token(user_id, user.email)

    payload = {
        "include_profile": True,
        "include_roles": True,
        "include_workspaces": True,
        "include_usage": True,
        "include_activity": True,
        "include_billing": True,
    }

    response = await client.post(
        "/api/v1/user/export-data", json=payload, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["format"] == "json"
    assert "filename" in data
    assert "export_payload" in data

    payload_data = data["export_payload"]
    assert "user" in payload_data
    assert payload_data["user"]["email"] == "exporttest@test.com"
    assert "activity" in payload_data
    assert len(payload_data["activity"]) == 1
    assert payload_data["activity"][0]["action"] == "user.login"
    assert "billing" in payload_data
    assert payload_data["billing"]["plan_name"] == "Pro"

    # export_id is stable between the response and the embedded metadata
    assert payload_data["export_metadata"]["export_id"] == data["export_id"]
    assert data["filename"].endswith(".json")


@pytest.mark.asyncio
async def test_user_data_export_respects_section_flags(client, db_session):
    """Only the requested sections are populated in the export payload."""
    user_id = uuid4()
    user = Users(
        id=user_id,
        email="exportflags@test.com",
        full_name="Flags Test",
        status="active",
        email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = generate_test_token(user_id, user.email)

    response = await client.post(
        "/api/v1/user/export-data",
        json={
            "include_profile": True,
            "include_roles": False,
            "include_workspaces": False,
            "include_usage": False,
            "include_activity": False,
            "include_billing": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload_data = response.json()["data"]["export_payload"]
    assert payload_data["user"]["email"] == "exportflags@test.com"
    assert payload_data["roles"] == []
    assert payload_data["workspaces"] == []
    assert payload_data["activity"] == []
    assert payload_data["billing"] == {}
