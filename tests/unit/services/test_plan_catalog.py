"""Tests for the public plan catalogue (GET /api/v1/plans)."""

from datetime import timedelta
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from scripts.seeds.seed_subscription_plans import PLANS
from src.api.database.async_database import get_async_db
from src.config.plan_rules import LAUNCH_OFFER, OFFERS, TRIAL_DURATION_DAYS, active_offer
from src.services.plan_catalog import CREDITS_PER_ARTICLE, build_plan_catalog
from src.services.subscription_plan_service import SubscriptionPlanService
from src.utils.credit_manager import STAGE_CREDITS


def seeded_plans():
    """The plan rows exactly as the seed writes them."""
    return [SimpleNamespace(**plan) for plan in PLANS]


def by_name(catalog):
    return {plan["name"]: plan for plan in catalog["plans"]}


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class InMemoryCache:
    is_enabled = True

    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl=None):
        self.store[key] = value
        self.ttl = ttl


def test_catalog_lists_the_public_plans_cheapest_first():
    catalog = build_plan_catalog(seeded_plans(), currency="USD")

    assert catalog["currency"] == "USD"
    assert [plan["name"] for plan in catalog["plans"]] == ["starter", "growth", "pro", "agency"]


def test_catalog_derives_the_figures_the_pricing_pages_print():
    starter = by_name(build_plan_catalog(seeded_plans(), currency="USD"))["starter"]

    assert starter["price_monthly"] == 39.0
    assert starter["price_yearly"] == 390.0
    assert starter["price_monthly_billed_yearly"] == 32.5
    assert starter["yearly_saving_percent"] == 17
    assert starter["credits_per_month"] == 400
    assert starter["articles_per_month"] == 26
    assert starter["price_per_article_monthly"] == 1.5
    assert starter["price_per_article_yearly"] == 1.25
    assert starter["max_workspaces"] == 1
    assert starter["max_members_per_workspace"] == 5
    assert starter["max_knowledge_items"] == 500


def test_per_article_price_rounds_to_the_cent():
    growth = by_name(build_plan_catalog(seeded_plans(), currency="USD"))["growth"]

    # $89 over the 66 whole articles 1,000 credits pay for is $1.3484..., shown as $1.35.
    assert growth["articles_per_month"] == 66
    assert growth["price_per_article_monthly"] == 1.35


def test_unlimited_caps_read_as_null():
    agency = by_name(build_plan_catalog(seeded_plans(), currency="USD"))["agency"]

    assert agency["max_workspaces"] is None
    assert agency["max_members_per_workspace"] is None
    assert agency["max_knowledge_items"] is None


def test_trial_and_private_plans_are_not_for_sale():
    names = by_name(build_plan_catalog(seeded_plans(), currency="USD"))

    assert "trial" not in names
    assert "enterprise" not in names


def test_trial_rules_come_from_the_trial_plan_and_the_signup_length():
    trial = build_plan_catalog(seeded_plans(), currency="USD")["trial"]

    assert trial == {
        "plan_name": "trial",
        "days": TRIAL_DURATION_DAYS,
        "credits": 50,
        "articles": 3,
        "credits_renew": False,
        "card_required": False,
        "max_workspaces": 1,
        "max_members_per_workspace": 3,
        "max_knowledge_items": 20,
    }


def test_trial_is_null_without_a_trial_plan():
    plans = [plan for plan in seeded_plans() if not plan.is_trial_plan]

    assert build_plan_catalog(plans, currency="USD")["trial"] is None


def test_credit_rules_are_the_credit_managers():
    credits = build_plan_catalog(seeded_plans(), currency="USD")["credits"]

    assert credits["per_article"] == sum(STAGE_CREDITS.values()) == CREDITS_PER_ARTICLE == 15
    assert credits["stages"] == [{"key": k, "credits": v} for k, v in STAGE_CREDITS.items()]
    assert credits["keyword_change"] == 1
    assert credits["outline_regeneration"] == 1
    assert credits["minimum_to_start"] == 15
    assert credits["low_balance_threshold"] == 15
    assert credits["carry_over"] is False


def test_an_offer_is_not_announced_before_it_is_granted():
    inside = LAUNCH_OFFER.starts_at + timedelta(days=1)

    assert LAUNCH_OFFER.granted is False
    assert active_offer(inside) is None


def test_a_granted_offer_is_active_inside_its_window_only(monkeypatch):
    granted = LAUNCH_OFFER.__class__(**{**LAUNCH_OFFER.__dict__, "granted": True})
    monkeypatch.setattr("src.config.plan_rules.OFFERS", (granted,))

    assert active_offer(granted.starts_at - timedelta(seconds=1)) is None
    assert active_offer(granted.starts_at) == granted
    assert active_offer(granted.ends_at - timedelta(seconds=1)) == granted
    assert active_offer(granted.ends_at) is None


def test_offers_have_unique_ids_and_sane_windows():
    assert len({offer.id for offer in OFFERS}) == len(OFFERS)
    for offer in OFFERS:
        assert offer.starts_at.tzinfo is not None
        assert offer.starts_at < offer.ends_at
        assert offer.credit_multiplier > 1


@pytest.mark.asyncio
async def test_service_adds_the_offer_and_caches_the_rest(monkeypatch):
    fake_cache = InMemoryCache()
    monkeypatch.setattr("src.api.cache.decorators.cache", fake_cache)
    granted = LAUNCH_OFFER.__class__(**{**LAUNCH_OFFER.__dict__, "granted": True})
    monkeypatch.setattr("src.config.plan_rules.OFFERS", (granted,))

    db = AsyncMock()
    db.execute.return_value = FakeResult(seeded_plans())
    service = SubscriptionPlanService(db)

    inside = await service.get_catalog(now=granted.starts_at + timedelta(hours=1))
    after = await service.get_catalog(now=granted.ends_at)

    assert db.execute.await_count == 1
    assert fake_cache.ttl == 900
    assert list(fake_cache.store) == ["subscription:plans:catalog:v1"]
    assert "offer" not in fake_cache.store["subscription:plans:catalog:v1"]
    assert inside["offer"] == {
        "id": "launch-2026-10",
        "kind": "first_month_credit_multiplier",
        "credit_multiplier": 2,
        "starts_at": "2026-10-04T00:00:00+00:00",
        "ends_at": "2026-10-11T06:59:00+00:00",
    }
    assert after["offer"] is None
    assert inside["plans"] == after["plans"]


@pytest.mark.asyncio
async def test_get_plans_is_public_and_returns_the_catalogue(monkeypatch):
    from src.api.server import app

    monkeypatch.setattr("src.api.cache.decorators.cache", InMemoryCache())
    monkeypatch.setattr("src.config.plan_rules.OFFERS", ())

    class _DummyDB:
        async def execute(self, _query):
            return FakeResult(seeded_plans())

        async def commit(self):
            return None

        async def rollback(self):
            return None

    async def override_get_db() -> AsyncGenerator[_DummyDB, None]:
        yield _DummyDB()

    app.dependency_overrides[get_async_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/plans")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()["data"]
    assert [plan["name"] for plan in data["plans"]] == ["starter", "growth", "pro", "agency"]
    assert data["trial"]["days"] == TRIAL_DURATION_DAYS
    assert data["credits"]["per_article"] == 15
    assert data["offer"] is None
