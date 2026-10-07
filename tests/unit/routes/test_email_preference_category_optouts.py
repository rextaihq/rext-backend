"""Turning an email kind off sticks, through the preferences page and the unsubscribe link (G61).

Category preferences live in NotificationPreferences' JSONB (get_preference / set_preference).
`PUT /user/email-preferences/` and the per-type unsubscribe used to look for them as attributes,
find nothing, and drop the change. The router runs in a small app of its own, with the session a
mock and the audit log stubbed: nothing here reaches a database or the network.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.database.async_database import get_async_db
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.routes.users.email_preferences import router
from src.api.security.dependencies import get_current_user

ROUTE = "src.api.routes.users.email_preferences"
USER_ID = uuid4()


@pytest.fixture
def prefs():
    return NotificationPreferences(
        id=uuid4(),
        user_id=USER_ID,
        email_notifications=True,
        in_app_notifications=True,
        marketing_updates=False,
        category_preferences={},
        unsubscribe_token=secrets.token_urlsafe(32),
    )


@pytest.fixture
def client(prefs):
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    found = MagicMock()
    found.scalar_one_or_none.return_value = prefs
    db.execute = AsyncMock(return_value=found)  # the unsubscribe link's token finds these prefs

    service = MagicMock()
    service.get_or_create = AsyncMock(return_value=prefs)

    app = FastAPI()
    app.include_router(router)

    async def override_db():
        yield db

    app.dependency_overrides[get_async_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(USER_ID)}
    with (
        patch(f"{ROUTE}.NotificationPreferencesService", return_value=service),
        patch(f"{ROUTE}.create_audit_log", AsyncMock()),
    ):
        yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_turning_a_kind_off_on_the_preferences_page_sticks(client, prefs):
    async with client as ac:
        response = await ac.put(
            "/user/email-preferences/",
            json={"payment_succeeded": False, "subscription_cancelled": False},
        )

    assert response.status_code == 200
    assert prefs.get_preference("billing_payment_success") is False
    # The route spelled this one "canceled", a key that doesn't exist; the shared map has it right.
    assert prefs.get_preference("billing_subscription_cancelled") is False
    assert prefs.get_preference("billing_payment_failed") is True  # untouched
    assert "billing_subscription_canceled" not in (prefs.category_preferences or {})


@pytest.mark.asyncio
async def test_unsubscribing_from_one_kind_by_link_sticks(client, prefs):
    async with client as ac:
        response = await ac.post(
            "/user/email-preferences/unsubscribe",
            json={"token": prefs.unsubscribe_token, "email_types": ["payment_succeeded"]},
        )

    assert response.status_code == 200
    assert prefs.get_preference("billing_payment_success") is False
    assert prefs.get_preference("billing_payment_failed") is True  # only the one kind
    assert prefs.email_notifications is True  # not every email
