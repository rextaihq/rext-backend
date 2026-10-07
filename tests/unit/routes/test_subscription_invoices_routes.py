"""Tests for GET /api/v1/subscriptions/invoices: the billing page's invoice list."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.database.async_database import get_async_db
from src.api.models.subscription_models.orders import Order, OrderStatus
from src.api.models.subscription_models.refunds import Refund, RefundStatus
from src.api.security.dependencies import get_current_user
from src.api.server import app

USER_ID = uuid4()
EMAIL = "buyer@example.com"


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return SimpleNamespace(
            all=lambda: self._rows, first=lambda: self._rows[0] if self._rows else None
        )

    def all(self):
        return [(row,) for row in self._rows]


class _QueuedDB:
    """Answers each `execute` with the next queued rows, in the route's query order."""

    def __init__(self, *answers):
        self._answers = list(answers)

    async def execute(self, _query):
        return _Result(self._answers.pop(0))

    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _get(db: _QueuedDB, path: str = "/api/v1/subscriptions/invoices"):
    async def override_get_db() -> AsyncGenerator[_QueuedDB, None]:
        yield db

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {
        "identity": str(USER_ID),
        "email": EMAIL,
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.get(path)
    finally:
        app.dependency_overrides.clear()


def _user():
    return SimpleNamespace(id=USER_ID, email=EMAIL)


def _order(order_id, total, ordered_at, status=OrderStatus.PAID):
    return Order(
        id=uuid4(),
        user_id=USER_ID,
        lemonsqueezy_order_id=order_id,
        product_name="Growth",
        total=total,
        subtotal=total,
        tax=0,
        currency="USD",
        status=status,
        receipt_url=f"https://app.lemonsqueezy.com/my-orders/{order_id}?signature=x",
        ordered_at=ordered_at,
        created_at=ordered_at,
    )


@pytest.mark.asyncio
async def test_invoices_come_from_local_orders_with_receipts_and_refund_credits(monkeypatch):
    provider = AsyncMock()
    monkeypatch.setattr(
        "src.api.routes.subscriptions.subscription_routes.get_payment_provider_singleton",
        lambda: provider,
    )
    first = _order("1001", 8900, datetime(2026, 8, 1, tzinfo=timezone.utc))
    renewal = _order(
        "1002", 8900, datetime(2026, 9, 1, tzinfo=timezone.utc), OrderStatus.PARTIAL_REFUND
    )
    refund = Refund(
        id=uuid4(),
        user_id=USER_ID,
        lemonsqueezy_order_id="1002",
        lemonsqueezy_refund_id="r-1",
        refund_amount=2000,
        original_amount=8900,
        currency="USD",
        status=RefundStatus.COMPLETED,
        is_partial=True,
        processed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )

    response = await _get(_QueuedDB([_user()], [renewal, first], [refund]))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 3
    # Newest first: the refund credit, the renewal, the first purchase.
    assert [inv["status"] for inv in data["invoices"]] == ["partial_refund", "paid", "paid"]
    credit, renewal_inv, first_inv = data["invoices"]
    assert credit["amount"] == 20.0
    assert credit["invoice_number"].startswith("REF-1002-")
    # A refunded purchase still reads as paid, with its receipt; the refund is its own line.
    assert renewal_inv["invoice_number"] == "1002"
    assert renewal_inv["amount"] == 89.0
    assert renewal_inv["paid_at"] is not None
    assert renewal_inv["invoice_url"] == "https://app.lemonsqueezy.com/my-orders/1002?signature=x"
    assert first_inv["invoice_number"] == "1001"
    assert first_inv["customer_email"] == EMAIL
    provider.get_invoices.assert_not_called()


@pytest.mark.asyncio
async def test_without_local_orders_the_provider_is_asked_with_the_subscription_ids(monkeypatch):
    provider = AsyncMock()
    provider.get_invoices.return_value = [
        {
            "invoice_id": "inv-1",
            "invoice_number": "INV-1",
            "status": "paid",
            "amount": 39.0,
            "currency": "USD",
            "invoice_url": "https://example.test/invoice.pdf",
            "invoice_date": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "paid_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        }
    ]
    monkeypatch.setattr(
        "src.api.routes.subscriptions.subscription_routes.get_payment_provider_singleton",
        lambda: provider,
    )

    response = await _get(_QueuedDB([_user()], [], ["ls-sub-1"]))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 1
    assert data["invoices"][0]["invoice_url"] == "https://example.test/invoice.pdf"
    assert data["invoices"][0]["invoice_date"].startswith("2026-07-01")
    provider.get_invoices.assert_awaited_once_with(
        user_email=EMAIL, limit=10, subscription_ids=["ls-sub-1"]
    )


@pytest.mark.asyncio
async def test_a_provider_failure_reads_as_an_empty_list(monkeypatch):
    provider = AsyncMock()
    provider.get_invoices.side_effect = RuntimeError("provider unreachable")
    monkeypatch.setattr(
        "src.api.routes.subscriptions.subscription_routes.get_payment_provider_singleton",
        lambda: provider,
    )

    response = await _get(_QueuedDB([_user()], [], []))

    assert response.status_code == 200
    assert response.json()["data"] == {"invoices": [], "count": 0}


@pytest.mark.asyncio
async def test_billing_urls_give_the_signed_portal_and_payment_method_links(monkeypatch):
    provider = AsyncMock()
    provider.get_subscription_urls.return_value = {
        "update_payment_method": "https://store.lemonsqueezy.com/subscription/1/payment-details?signature=a",
        "customer_portal": "https://store.lemonsqueezy.com/billing?expires=1&signature=b",
    }
    monkeypatch.setattr(
        "src.api.routes.subscriptions.subscription_routes.get_payment_provider_singleton",
        lambda: provider,
    )

    response = await _get(_QueuedDB(["ls-sub-1"]), "/api/v1/subscriptions/billing-urls")

    assert response.status_code == 200
    assert response.json()["data"] == provider.get_subscription_urls.return_value
    provider.get_subscription_urls.assert_awaited_once_with("ls-sub-1")


@pytest.mark.asyncio
async def test_billing_urls_need_a_paid_subscription(monkeypatch):
    provider = AsyncMock()
    monkeypatch.setattr(
        "src.api.routes.subscriptions.subscription_routes.get_payment_provider_singleton",
        lambda: provider,
    )

    response = await _get(_QueuedDB([]), "/api/v1/subscriptions/billing-urls")

    assert response.status_code == 400
    provider.get_subscription_urls.assert_not_called()
