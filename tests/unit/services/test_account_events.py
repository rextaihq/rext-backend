"""What an account does, told to product analytics (rext-control task 712): the five events,
what each carries, that running out is told once per crossing, and that a charge never
waits for any of it. The report, the database and Redis are fakes here.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.services import account_events, server_events
from src.utils import credit_manager
from src.utils.credit_manager import (
    LOW_CREDITS_THRESHOLD,
    InsufficientCreditsError,
    consume_stage_credits,
    deduct_credits,
)

AT = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def world(monkeypatch):
    """Analytics on; what would be reported is kept. `workspaces` is how many the account made."""
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    state = SimpleNamespace(sent=[], marks={}, workspaces=1, owner=uuid4(), sessions=0)

    async def report(name, properties, **kwargs):
        state.sent.append((name, properties, kwargs))
        return True

    @asynccontextmanager
    async def session():
        state.sessions += 1
        counted = SimpleNamespace(scalar_one=lambda: state.workspaces)
        yield SimpleNamespace(execute=AsyncMock(return_value=counted))

    async def owner_of(_user_id, _workspace_id):
        return state.owner

    async def get(key):
        return state.marks.get(key)

    async def put(key, value, ttl=300):
        state.marks[key] = value
        return True

    async def delete(key):
        return state.marks.pop(key, None) is not None

    monkeypatch.setattr(account_events, "report_event", report)
    monkeypatch.setattr(account_events, "get_async_db_context", session)
    monkeypatch.setattr(account_events, "_owner_of", owner_of)
    monkeypatch.setattr(account_events, "cache", SimpleNamespace(get=get, set=put, delete=delete))
    return state


def _names(state):
    return [name for name, _, _ in state.sent]


def test_every_event_here_is_on_the_senders_list():
    for name in ("user_signed_up", "workspace_created", "credits_spent", "credits_low"):
        assert name in server_events.EVENT_PROPERTIES
    assert "credits_out" in server_events.EVENT_PROPERTIES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "told"),
    [
        ("credentials", "credentials"),
        ("Google", "google"),
        ("github", "github"),
        ("invitation", "invitation"),
        # A provider the list doesn't know is not passed on as written.
        ("someone@example.com", None),
        (None, None),
    ],
)
async def test_a_new_account_says_how_it_was_made(world, method, told):
    user_id = uuid4()

    await account_events.user_signed_up(user_id, method, AT)

    name, properties, sent_with = world.sent[0]
    assert (name, properties) == ("user_signed_up", {"method": told})
    assert sent_with == {"key": str(user_id), "occurred_at": AT, "user_id": user_id}


@pytest.mark.asyncio
@pytest.mark.parametrize(("made", "first"), [(1, True), (2, False), (5, False)])
async def test_a_new_workspace_says_whether_it_is_the_first(world, made, first):
    world.workspaces = made
    user_id, workspace_id = uuid4(), uuid4()

    await account_events.workspace_created(user_id, workspace_id, AT)

    name, properties, sent_with = world.sent[0]
    assert (name, properties) == ("workspace_created", {"first_workspace": first})
    assert sent_with == {
        "key": str(workspace_id),
        "occurred_at": AT,
        "user_id": user_id,
        "workspace_id": workspace_id,
    }


async def _charge(
    balance_after, credits=1, user_id=None, workspace_id=None, action="content_drafting"
):
    await account_events.credits_charged(
        user_id or uuid4(),
        workspace_id,
        action=action,
        credits=credits,
        balance_after=balance_after,
        low_threshold=LOW_CREDITS_THRESHOLD,
        occurred_at=AT,
    )


@pytest.mark.asyncio
async def test_a_charge_is_told_about_the_account_whose_credits_were_spent(world):
    member, workspace_id = uuid4(), uuid4()

    await _charge(96, credits=4, user_id=member, workspace_id=workspace_id, action="deep_research")

    assert _names(world) == ["credits_spent"]
    _, properties, sent_with = world.sent[0]
    assert properties == {"action": "deep_research", "credits": 4, "balance_after": 96}
    assert sent_with["user_id"] == world.owner != member
    assert (sent_with["workspace_id"], sent_with["occurred_at"]) == (workspace_id, AT)


@pytest.mark.asyncio
async def test_two_charges_are_two_events(world):
    await _charge(96)
    await _charge(95)

    first, second = (sent_with["key"] for _, _, sent_with in world.sent)
    assert first != second


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("credits", "balance_after", "low"),
    [
        (5, LOW_CREDITS_THRESHOLD - 1, True),  # 19 -> 14: this charge crossed it
        (1, LOW_CREDITS_THRESHOLD - 1, True),  # 15 -> 14
        (1, LOW_CREDITS_THRESHOLD, False),  # 16 -> 15: one article still fits
        (1, LOW_CREDITS_THRESHOLD - 2, False),  # 14 -> 13: it was low already
    ],
)
async def test_low_is_told_by_the_charge_that_crosses_it_and_no_other(
    world, credits, balance_after, low
):
    await _charge(balance_after, credits=credits)

    assert ("credits_low" in _names(world)) is low
    if low:
        properties = next(p for name, p, _ in world.sent if name == "credits_low")
        assert properties == {"balance": balance_after, "threshold": LOW_CREDITS_THRESHOLD}


@pytest.mark.asyncio
async def test_running_out_is_told_once_however_many_runs_are_refused_after(world):
    await _charge(balance_after=0)
    for _ in range(3):
        await account_events.credits_refused(
            uuid4(), None, action="generate_outline", occurred_at=AT
        )

    assert _names(world).count("credits_out") == 1
    out = next(p for name, p, _ in world.sent if name == "credits_out")
    assert out == {"action": "content_drafting"}


@pytest.mark.asyncio
async def test_a_refusal_with_no_charge_before_it_tells_it_once(world):
    """The balance went to nothing some other way (a deduction, a trial that ended)."""
    for _ in range(2):
        await account_events.credits_refused(uuid4(), None, action="serp_seo", occurred_at=AT)

    assert world.sent[0][:2] == ("credits_out", {"action": "serp_seo"})
    assert _names(world) == ["credits_out"]


@pytest.mark.asyncio
async def test_after_credits_come_back_running_out_again_is_a_new_crossing(world):
    await account_events.credits_refused(uuid4(), None, action="serp_seo", occurred_at=AT)
    await _charge(balance_after=40)  # credits again, and a charge went through
    await account_events.credits_refused(uuid4(), None, action="deep_research", occurred_at=AT)

    assert _names(world).count("credits_out") == 2


@pytest.mark.asyncio
async def test_with_analytics_off_nothing_is_read_or_sent(world, monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_KEY")

    await account_events.user_signed_up(uuid4(), "credentials", AT)
    await account_events.workspace_created(uuid4(), uuid4(), AT)
    await _charge(balance_after=0)
    await account_events.credits_refused(uuid4(), None, action="serp_seo", occurred_at=AT)

    assert (world.sent, world.sessions, world.marks) == ([], 0, {})


@pytest.mark.asyncio
async def test_an_event_that_fails_never_reaches_its_caller(world, monkeypatch):
    monkeypatch.setattr(account_events, "report_event", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(account_events, "_owner_of", AsyncMock(side_effect=RuntimeError("gone")))

    await account_events.user_signed_up(uuid4(), "credentials", AT)
    await account_events.workspace_created(uuid4(), uuid4(), AT)
    await _charge(balance_after=3)
    await account_events.credits_refused(uuid4(), None, action="serp_seo", occurred_at=AT)


# --- the charge itself (src/utils/credit_manager.py) hands the event over and goes on


@pytest.fixture
def charge(monkeypatch):
    """A charge with its database and notices stood in; what it hands to analytics is kept."""
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    state = SimpleNamespace(started=[], outcome=96)

    async def on_main_loop(work):
        work.close()
        if isinstance(state.outcome, Exception):
            raise state.outcome
        return state.outcome

    def soon(sending):
        state.started.append(sending)

    monkeypatch.setattr(credit_manager, "_run_on_main_loop", on_main_loop)
    monkeypatch.setattr(credit_manager, "notify_credit_owner", AsyncMock())
    monkeypatch.setattr(credit_manager, "_emit_credit_event", MagicMock())
    monkeypatch.setattr(server_events, "send_soon", soon)
    # The events are stood in by plain values, so nothing is left un-awaited.
    monkeypatch.setattr(
        account_events, "credits_charged", lambda *a, **k: ("credits_charged", a, k)
    )
    monkeypatch.setattr(
        account_events, "credits_refused", lambda *a, **k: ("credits_refused", a, k)
    )
    return state


@pytest.mark.asyncio
async def test_a_committed_charge_hands_its_event_over_without_waiting(charge):
    user_id, workspace_id = uuid4(), uuid4()
    before = datetime.now(timezone.utc)

    await consume_stage_credits(str(user_id), 4, "deep_research", workspace_id=workspace_id)

    assert charge.started == [
        (
            "credits_charged",
            (user_id, workspace_id),
            {
                "action": "deep_research",
                "credits": 4,
                "balance_after": 96,
                "low_threshold": LOW_CREDITS_THRESHOLD,
                "occurred_at": ANY,
            },
        )
    ]
    assert before <= charge.started[0][2]["occurred_at"] <= datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_a_charge_refused_for_lack_of_credits_says_so(charge):
    charge.outcome = InsufficientCreditsError("humanization", 5, 2)
    user_id = uuid4()

    with pytest.raises(InsufficientCreditsError):
        await consume_stage_credits(str(user_id), 5, "humanization")

    assert charge.started == [
        ("credits_refused", (user_id, None), {"action": "humanization", "occurred_at": ANY})
    ]


@pytest.mark.asyncio
async def test_someone_who_isnt_a_member_is_not_an_account_out_of_credits(charge):
    charge.outcome = InsufficientCreditsError("workspace_access", 1, 0)

    with pytest.raises(InsufficientCreditsError):
        await consume_stage_credits(str(uuid4()), 1, "serp_seo", workspace_id=uuid4())

    assert charge.started == []


@pytest.mark.asyncio
async def test_a_run_refused_before_it_starts_says_so(charge, monkeypatch):
    monkeypatch.setattr(credit_manager, "_get_balance", AsyncMock(return_value=0))
    user_id = uuid4()
    ran = []

    @deduct_credits("generate_outline")
    async def node(state):
        ran.append(state)
        return {"content": {}}

    result = await node({"user_id": str(user_id)})

    assert ran == []
    assert result["content"]["error_code"] == "insufficient_credits"
    assert charge.started == [
        ("credits_refused", (user_id, None), {"action": "generate_outline", "occurred_at": ANY})
    ]


@pytest.mark.asyncio
async def test_with_analytics_off_a_charge_hands_nothing_over(charge, monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_KEY")

    await consume_stage_credits(str(uuid4()), 1, "serp_seo")

    assert charge.started == []
