"""Server-side events for product analytics (rext-control task 712).

Who an event may name, what it may carry, and that reporting one never reaches the work
it reports. PostHog is a fake transport here; nothing leaves the machine.
"""

import asyncio
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from src.api.models.subscription_models.subscriptions import BillingPeriod, SubscriptionStatus
from src.services import money_events, server_events
from src.services.server_events import (
    EVENT_PROPERTIES,
    EventContext,
    allows_identity,
    event_context,
    plan_properties,
    report_event,
    send_soon,
    sendable,
)

AT = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)
PLAN = {"plan": "growth", "plan_status": "active", "billing_period": "monthly"}


@pytest.fixture
def posthog(monkeypatch):
    """Analytics on; what the one sender is asked to send is kept in `sent`."""
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    state = SimpleNamespace(sent=[], context=EventContext(identified=True, plan=PLAN), reads=[])

    async def send(event, properties, *, key, person_id=None, occurred_at=None, client=None):
        state.sent.append(
            SimpleNamespace(
                event=event,
                properties=properties,
                key=key,
                person_id=person_id,
                occurred_at=occurred_at,
            )
        )
        return True

    async def context(user_id):
        state.reads.append(user_id)
        return state.context

    monkeypatch.setattr(money_events, "send_server_event", send)
    monkeypatch.setattr(server_events, "event_context", context)
    return state


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


def test_the_list_is_the_eight_events_on_the_task():
    assert set(EVENT_PROPERTIES) == {
        "user_signed_up",
        "workspace_created",
        "credits_spent",
        "credits_low",
        "credits_out",
        "content_generation_started",
        "content_generation_completed",
        "content_generation_failed",
    }


def test_a_property_that_isnt_on_the_events_list_never_leaves(monkeypatch):
    warned = []
    monkeypatch.setattr(
        server_events.logger, "warning", lambda message, **kwargs: warned.append((message, kwargs))
    )

    kept = sendable(
        "credits_spent",
        {
            "action": "deep_research",
            "credits": 4,
            "balance_after": 96,
            "plan": "growth",
            # One word, so its shape says nothing: it is left out because it isn't listed.
            "keyword": "shoes",
            "token": "abc-123",
            # Listed for another event, not for this one.
            "method": "google",
            "nothing": None,
        },
    )

    assert kept == {"action": "deep_research", "credits": 4, "balance_after": 96, "plan": "growth"}
    # The log names what was left out, never its value.
    assert warned == [
        (
            "Server event properties left out",
            {"extra": {"event": "credits_spent", "properties": ["keyword", "method", "token"]}},
        )
    ]


@pytest.mark.parametrize(
    "value",
    ["best running shoes", "mary@example.com", "x" * 65, {"nested": "value"}, ["a"], ""],
    ids=["a sentence", "an address", "too long", "a mapping", "a list", "empty"],
)
def test_a_listed_property_holds_a_number_a_boolean_or_a_short_word(value):
    assert sendable("credits_spent", {"action": value, "credits": 4}) == {"credits": 4}


@pytest.mark.asyncio
async def test_an_allowed_event_carries_the_accounts_id_its_plan_and_its_workspace(posthog):
    user_id, workspace_id = uuid4(), uuid4()

    sent = await report_event(
        "credits_spent",
        {"action": "generate_outline", "credits": 1, "balance_after": 385},
        key="charge-1",
        occurred_at=AT,
        user_id=user_id,
        workspace_id=workspace_id,
    )

    assert sent is True
    assert posthog.reads == [user_id]
    event = posthog.sent[0]
    assert (event.event, event.key, event.occurred_at) == ("credits_spent", "charge-1", AT)
    assert event.person_id == str(user_id)
    assert event.properties == {
        **PLAN,
        "action": "generate_outline",
        "credits": 1,
        "balance_after": 385,
        "workspace_id": str(workspace_id),
    }


@pytest.mark.asyncio
async def test_an_event_without_the_persons_yes_names_no_one_and_no_workspace(posthog):
    posthog.context = EventContext(identified=False, plan=PLAN)
    user_id, workspace_id = uuid4(), uuid4()

    await report_event(
        "workspace_created",
        {"first_workspace": True},
        key="k-1",
        occurred_at=AT,
        user_id=user_id,
        workspace_id=workspace_id,
    )

    event = posthog.sent[0]
    assert event.person_id is None
    # A workspace's id is as steady as an account's, so an anonymous event has neither.
    assert event.properties == {**PLAN, "first_workspace": True}
    for steady in (user_id, workspace_id):
        assert str(steady) not in str(event.properties)


@pytest.mark.asyncio
@pytest.mark.parametrize("identified", [True, False])
async def test_the_teams_own_account_is_marked_named_or_not(posthog, identified):
    """The mark the team's browsers send, so the charts leave both out. It names nobody,
    so it rides on an anonymous event too."""
    posthog.context = EventContext(identified=identified, plan=PLAN, internal=True)

    await report_event(
        "credits_spent",
        {"action": "serp_seo", "credits": 1, "balance_after": 9},
        key="charge-team",
        occurred_at=AT,
        user_id=uuid4(),
    )

    assert posthog.sent[0].properties["internal"] is True
    assert (posthog.sent[0].person_id is not None) is identified


@pytest.mark.asyncio
async def test_a_customers_event_has_no_such_property_at_all(posthog):
    """Left out, never false: the browser leaves it out too, and the charts filter on it."""
    await report_event(
        "credits_spent",
        {"action": "serp_seo", "credits": 1, "balance_after": 9, "internal": True},
        key="charge-customer",
        occurred_at=AT,
        user_id=uuid4(),
    )

    # Nor can a caller set it: only the account's standing does.
    assert "internal" not in posthog.sent[0].properties


@pytest.mark.parametrize(
    ("email", "internal"),
    [
        ("it+plan-1008@revnix.com", True),
        ("Someone@REVNIX.com", True),
        ("someone@gmail.com", False),
        ("someone@notrevnix.com", False),
        ("someone@mail.revnix.com", False),
        ("revnix.com@gmail.com", False),
        ("no-at-sign", False),
        (None, False),
    ],
)
def test_an_address_on_the_companys_own_domain_is_the_teams(email, internal):
    assert server_events.on_internal_domain(email) is internal


def test_the_companys_domains_are_a_setting(monkeypatch):
    monkeypatch.setenv("ANALYTICS_INTERNAL_DOMAINS", " Example.org, @second.example ,")

    assert server_events.internal_domains() == {"example.org", "second.example"}
    assert server_events.on_internal_domain("a@example.org")
    assert not server_events.on_internal_domain("a@revnix.com")


@pytest.mark.asyncio
async def test_a_caller_that_has_read_the_standing_passes_it_and_nothing_is_read(posthog):
    """Code on a sync session (a graph node) reads the answer itself."""
    user_id = uuid4()

    await report_event(
        "content_generation_started",
        {"from_library": True, "country": "US"},
        key="thread-1",
        occurred_at=AT,
        user_id=user_id,
        context=EventContext(identified=False, plan={"plan": "starter"}),
    )

    assert posthog.reads == []
    assert posthog.sent[0].person_id is None
    assert posthog.sent[0].properties == {"plan": "starter", "from_library": True, "country": "US"}


@pytest.mark.asyncio
async def test_an_event_that_isnt_on_the_list_is_not_sent(posthog):
    assert await report_event("page_viewed", {"path": "home"}, key="k", occurred_at=AT) is False
    assert posthog.sent == []


@pytest.mark.asyncio
async def test_nothing_is_read_or_sent_without_the_projects_key(posthog, monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_KEY")

    sent = await report_event("user_signed_up", key="u-1", occurred_at=AT, user_id=uuid4())

    assert (sent, posthog.sent, posthog.reads) == (False, [], [])


@pytest.mark.asyncio
async def test_a_report_that_fails_is_false_and_never_raises(posthog, monkeypatch):
    async def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(money_events, "send_server_event", broken)

    assert await report_event("user_signed_up", key="u-1", occurred_at=AT, user_id=uuid4()) is False


@pytest.mark.asyncio
async def test_a_report_that_hangs_is_given_up_on(posthog, monkeypatch):
    async def hangs(_user_id):
        await asyncio.sleep(30)

    monkeypatch.setattr(server_events, "event_context", hangs)
    monkeypatch.setattr(server_events, "REPORT_TIMEOUT_SECONDS", 0.05)

    assert await report_event("user_signed_up", key="u-1", occurred_at=AT, user_id=uuid4()) is False
    assert posthog.sent == []


@pytest.mark.asyncio
async def test_a_standing_that_cant_be_read_is_anonymous_and_planless(monkeypatch):
    @asynccontextmanager
    async def broken():
        raise RuntimeError("connection closed")
        yield

    monkeypatch.setattr(server_events, "get_async_db_context", broken)

    assert await event_context(uuid4()) == EventContext()


# --- the one sender's request (src/services/money_events.py)


def _transport(requests, status=200):
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"status": 1})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 404, 503])
async def test_only_a_2xx_answer_counts_as_taken(monkeypatch, status):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    requests = []

    async with httpx.AsyncClient(transport=_transport(requests, status)) as client:
        taken = await money_events.send_server_event(
            "credits_spent", {"credits": 1}, key="row-1", occurred_at=AT, client=client
        )

    assert taken is False
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_a_borrowed_client_with_no_time_limit_is_still_given_the_senders(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    requests = []

    async with httpx.AsyncClient(transport=_transport(requests), timeout=None) as client:
        taken = await money_events.send_server_event(
            "credits_spent", {"credits": 1}, key="row-1", occurred_at=AT, client=client
        )

    assert taken is True
    limits = requests[0].extensions["timeout"]
    assert set(limits.values()) == {money_events.SEND_TIMEOUT_SECONDS}


# --- starting a send without waiting for it


@pytest.mark.asyncio
async def test_a_send_started_and_not_awaited_still_runs(monkeypatch):
    monkeypatch.setattr(server_events.loop_registry, "get", lambda: None)
    done = asyncio.Event()

    async def sending():
        done.set()

    send_soon(sending())

    await asyncio.wait_for(done.wait(), timeout=2)


@pytest.mark.asyncio
async def test_a_send_from_another_loop_runs_on_the_servers(monkeypatch):
    """A graph node runs on a loop of its own; the send goes to the server's."""
    servers_loop = asyncio.get_running_loop()
    monkeypatch.setattr(server_events.loop_registry, "get", lambda: servers_loop)
    ran_on = []
    done = asyncio.Event()

    async def sending():
        ran_on.append(asyncio.get_running_loop())
        done.set()

    def a_node():
        async def node():
            send_soon(sending())

        asyncio.run(node())

    worker = threading.Thread(target=a_node)
    worker.start()
    await asyncio.wait_for(done.wait(), timeout=2)
    worker.join(timeout=2)

    assert ran_on == [servers_loop]


def test_with_no_loop_at_all_nothing_is_sent_and_nothing_raises(monkeypatch):
    monkeypatch.setattr(server_events.loop_registry, "get", lambda: None)
    started = []

    async def sending():
        started.append(True)

    send_soon(sending())

    assert started == []
