"""Server-side events for product analytics (rext-control task 712).

Who an event may name, what it may carry, and that sending never reaches the work it
reports. PostHog is a fake client here; nothing leaves the machine.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from src.api.models.subscription_models.subscriptions import BillingPeriod, SubscriptionStatus
from src.services import server_events
from src.services.server_events import (
    EventContext,
    allows_identity,
    event_context,
    plan_properties,
    send_server_event,
)


class _PostHog:
    """Stands in for the httpx client: keeps what was posted, answers as told."""

    def __init__(self, status_code: int = 200, error: Exception | None = None):
        self.status_code = status_code
        self.error = error
        self.posts: list[tuple[str, dict]] = []

    async def post(self, url, json):
        if self.error is not None:
            raise self.error
        self.posts.append((url, json))
        return SimpleNamespace(status_code=self.status_code)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    monkeypatch.setenv("ENVIRONMENT", "Production")
    monkeypatch.delenv("POSTHOG_HOST", raising=False)


@pytest.mark.parametrize(
    ("answer", "region", "allowed"),
    [
        ("granted", "eea", True),
        ("granted", None, True),
        ("denied", "other", False),
        ("denied", "eea", False),
        (None, "other", True),
        (None, "eea", False),
        # A region that isn't known is treated as the EEA.
        (None, None, False),
    ],
)
def test_an_event_names_its_person_only_when_their_answer_allows_it(answer, region, allowed):
    assert allows_identity(answer, region) is allowed


def test_the_plan_is_told_as_the_subscription_has_it():
    subscription = SimpleNamespace(
        status=SubscriptionStatus.TRIAL,
        billing_period=BillingPeriod.YEARLY,
        plan=SimpleNamespace(name="growth"),
    )

    assert plan_properties(subscription) == {
        "plan": "growth",
        "plan_status": "trial",
        "billing_period": "yearly",
    }
    assert plan_properties(None) == {}


def test_a_plan_that_isnt_loaded_is_left_out_rather_than_queried():
    class Unloaded:
        status = SubscriptionStatus.ACTIVE
        billing_period = BillingPeriod.MONTHLY

        @property
        def plan(self):  # a lazy load in an async session would raise here
            raise AssertionError("the plan was read")

    assert plan_properties(Unloaded()) == {"plan_status": "active", "billing_period": "monthly"}


@pytest.mark.asyncio
async def test_an_allowed_event_carries_the_accounts_id(configured):
    posthog = _PostHog()
    user_id, workspace_id = uuid4(), uuid4()

    sent = await send_server_event(
        "credits_spent",
        {"action": "generate", "credits": 15, "balance_after": 385},
        key="charge-1",
        user_id=user_id,
        workspace_id=workspace_id,
        identified=True,
        plan={"plan": "growth", "plan_status": "active", "billing_period": "monthly"},
        occurred_at=datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc),
        client=posthog,
    )

    assert sent is True
    url, body = posthog.posts[0]
    assert url == "https://eu.i.posthog.com/i/v0/e/"
    assert body["event"] == "credits_spent"
    assert body["distinct_id"] == str(user_id)
    assert body["timestamp"] == "2026-10-08T07:00:00+00:00"
    assert body["properties"] == {
        "plan": "growth",
        "plan_status": "active",
        "billing_period": "monthly",
        "action": "generate",
        "credits": 15,
        "balance_after": 385,
        "workspace_id": str(workspace_id),
        "surface": "app",
        "source": "server",
        "environment": "production",
    }


@pytest.mark.asyncio
async def test_an_event_without_the_persons_yes_is_anonymous(configured):
    posthog = _PostHog()
    user_id = uuid4()

    await send_server_event(
        "user_signed_up",
        {"method": "credentials"},
        key=str(user_id),
        user_id=user_id,
        client=posthog,
    )

    body = posthog.posts[0][1]
    assert str(user_id) not in str(body)
    assert body["distinct_id"] == body["uuid"]
    assert body["properties"]["$process_person_profile"] is False


@pytest.mark.asyncio
async def test_a_retry_is_the_same_event_and_another_thing_is_another(configured):
    posthog = _PostHog()

    for key in ("run-1", "run-1", "run-2"):
        await send_server_event(
            "workspace_created", {"first_workspace": True}, key=key, client=posthog
        )
    await send_server_event("credits_out", {"action": "generate"}, key="run-1", client=posthog)

    first, again, other, other_name = (body["uuid"] for _, body in posthog.posts)
    assert first == again
    assert len({first, other, other_name}) == 3


@pytest.mark.asyncio
async def test_text_a_person_could_have_typed_never_leaves(configured, monkeypatch):
    posthog = _PostHog()
    warned = []
    monkeypatch.setattr(
        server_events.logger, "warning", lambda message, **kwargs: warned.append((message, kwargs))
    )

    await send_server_event(
        "credits_spent",
        {
            "action": "generate",
            "credits": 15,
            "refunded": False,
            "keyword": "best running shoes",
            "email": "mary@example.com",
            "title": "x" * 65,
            "details": {"nested": "value"},
            "nothing": None,
        },
        key="charge-2",
        client=posthog,
    )

    properties = posthog.posts[0][1]["properties"]
    assert {"action", "credits", "refunded"} <= set(properties)
    assert not {"keyword", "email", "title", "details", "nothing"} & set(properties)
    # The log names what was left out, never its value.
    assert warned == [
        (
            "Server event properties left out",
            {"extra": {"properties": ["details", "email", "keyword", "title"]}},
        )
    ]


@pytest.mark.asyncio
async def test_nothing_is_sent_without_the_projects_key(monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_KEY", raising=False)
    posthog = _PostHog()

    assert await send_server_event("user_signed_up", key="u-1", client=posthog) is False
    assert posthog.posts == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "posthog",
    [_PostHog(status_code=503), _PostHog(error=httpx.ConnectTimeout("no route"))],
    ids=["refused", "unreachable"],
)
async def test_a_send_that_fails_is_false_and_never_raises(configured, posthog):
    assert await send_server_event("user_signed_up", key="u-1", client=posthog) is False


@pytest.mark.asyncio
async def test_a_context_that_cant_be_read_is_anonymous_and_planless():
    class Broken:
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("connection closed")

    assert await event_context(Broken(), uuid4()) == EventContext()
