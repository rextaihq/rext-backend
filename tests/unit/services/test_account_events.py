"""What an account does, told to product analytics (rext-control task 712): the five events,
what each carries, that running out is told once per crossing, and that a charge never
waits for any of it. The report, the database and Redis are fakes here.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.api.cache.redis_client import CacheClient
from src.services import account_events, server_events
from src.utils import credit_manager
from src.utils.credit_manager import (
    LOW_CREDITS_THRESHOLD,
    InsufficientCreditsError,
    consume_stage_credits,
    deduct_credits,
)

AT = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)


class _Redis:
    """Redis as the cache client uses it. SET with nx as Redis does it: the first caller sets
    the key, the others get nothing. `broken` is an outage: every command raises."""

    def __init__(self, marks):
        self.marks = marks
        self.broken = False

    async def set(self, key, value, nx=False, ex=None):
        await asyncio.sleep(0)  # let another caller in, as a real round trip would
        if self.broken:
            raise ConnectionError("redis is down")
        if nx and key in self.marks:
            return None
        self.marks[key] = value
        return True

    async def delete(self, key):
        if self.broken:
            raise ConnectionError("redis is down")
        return 1 if self.marks.pop(key, None) is not None else 0


@pytest.fixture
def world(monkeypatch):
    """Analytics on; what would be reported is kept. `creations` is how many workspaces the
    audit log says the account made. `cache` is the real cache client with a stand-in Redis
    behind it, so the client's own interface is what the events meet."""
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    state = SimpleNamespace(
        sent=[], marks={}, creations=1, owner=uuid4(), sessions=0, owners_read=0
    )

    async def report(name, properties, **kwargs):
        state.sent.append((name, properties, kwargs))
        return True

    @asynccontextmanager
    async def session():
        state.sessions += 1
        counted = SimpleNamespace(scalar_one=lambda: state.creations)
        yield SimpleNamespace(execute=AsyncMock(return_value=counted))

    async def owner_of(_user_id, _workspace_id):
        state.owners_read += 1
        return state.owner

    state.cache = CacheClient()
    state.cache._enabled = True
    state.cache.redis = _Redis(state.marks)
    monkeypatch.setattr(state.cache, "_report_unavailable", AsyncMock())
    monkeypatch.setattr(account_events, "report_event", report)
    monkeypatch.setattr(account_events, "get_async_db_context", session)
    monkeypatch.setattr(account_events, "_owner_of", owner_of)
    monkeypatch.setattr(account_events, "cache", state.cache)
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
    assert (sent_with["occurred_at"], sent_with["user_id"]) == (AT, user_id)


@pytest.mark.asyncio
async def test_an_events_key_is_the_same_for_the_same_thing_and_never_its_id(world):
    """The sender names the key when it logs a send that failed: an account's id there
    would put a personal identifier in the log."""
    user_id, workspace_id = uuid4(), uuid4()

    await account_events.user_signed_up(user_id, "credentials", AT)
    await account_events.user_signed_up(user_id, "credentials", AT)
    await account_events.workspace_created(user_id, workspace_id, AT)

    first, again, workspace = (sent_with["key"] for _, _, sent_with in world.sent)
    assert first == again != workspace
    for key in (first, workspace):
        assert str(user_id) not in key and str(workspace_id) not in key


@pytest.mark.asyncio
@pytest.mark.parametrize(("creations", "first"), [(1, True), (0, True), (2, False), (5, False)])
async def test_a_new_workspace_is_the_first_when_the_account_made_no_other(world, creations, first):
    """Counted from the audit log's creations, not from what the account owns now: one it
    handed over still counts, one handed to it doesn't."""
    world.creations = creations
    user_id, workspace_id = uuid4(), uuid4()

    await account_events.workspace_created(user_id, workspace_id, AT)

    name, properties, sent_with = world.sent[0]
    assert (name, properties) == ("workspace_created", {"first_workspace": first})
    assert (sent_with["user_id"], sent_with["workspace_id"]) == (user_id, workspace_id)
    assert sent_with["occurred_at"] == AT


async def _charge(
    balance_after, credits=1, owner=None, workspace_id=None, action="content_drafting"
):
    await account_events.credits_charged(
        owner or uuid4(),
        workspace_id,
        action=action,
        credits=credits,
        balance_after=balance_after,
        low_threshold=LOW_CREDITS_THRESHOLD,
        occurred_at=AT,
    )


@pytest.mark.asyncio
async def test_a_charge_is_told_about_the_account_it_was_taken_from(world):
    """The charge says whose credits it took; who owns the workspace later doesn't matter."""
    charged, workspace_id = uuid4(), uuid4()

    await _charge(96, credits=4, owner=charged, workspace_id=workspace_id, action="deep_research")

    assert _names(world) == ["credits_spent"]
    _, properties, sent_with = world.sent[0]
    assert properties == {"action": "deep_research", "credits": 4, "balance_after": 96}
    assert sent_with["user_id"] == charged
    assert (sent_with["workspace_id"], sent_with["occurred_at"]) == (workspace_id, AT)
    assert world.owners_read == 0


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


async def _refuse(world, action="generate_outline", owner=None):
    await account_events.credits_refused(
        uuid4(), None, action=action, occurred_at=AT, owner_id=owner
    )


@pytest.mark.asyncio
async def test_running_out_is_told_once_however_many_runs_are_refused_after(world):
    await _charge(balance_after=0, owner=world.owner)
    for _ in range(3):
        await _refuse(world, owner=world.owner)

    assert _names(world).count("credits_out") == 1
    out = next(p for name, p, _ in world.sent if name == "credits_out")
    assert out == {"action": "content_drafting"}


@pytest.mark.asyncio
async def test_runs_refused_at_the_same_moment_tell_it_once(world):
    """Each would find no mark and set one; only the one that sets it tells."""
    await asyncio.gather(*(_refuse(world, owner=world.owner) for _ in range(5)))

    assert _names(world) == ["credits_out"]


@pytest.mark.asyncio
async def test_a_refusal_with_no_charge_before_it_tells_it_once_for_the_workspaces_owner(world):
    """The balance went to nothing some other way (a deduction, a trial that ended), and
    the run was refused before any charge: the owner is read here."""
    for _ in range(2):
        await _refuse(world, action="serp_seo")

    name, properties, sent_with = world.sent[0]
    assert (name, properties) == ("credits_out", {"action": "serp_seo"})
    assert sent_with["user_id"] == world.owner
    assert _names(world) == ["credits_out"]


@pytest.mark.asyncio
async def test_a_refused_charge_names_the_account_it_was_short_on(world):
    short = uuid4()

    await _refuse(world, owner=short)

    assert world.sent[0][2]["user_id"] == short
    assert world.owners_read == 0


@pytest.mark.asyncio
async def test_after_credits_come_back_running_out_again_is_a_new_crossing(world):
    await _refuse(world, owner=world.owner)
    await _charge(balance_after=40, owner=world.owner)  # credits again, a charge went through
    await _refuse(world, owner=world.owner)

    assert _names(world).count("credits_out") == 2


@pytest.mark.asyncio
async def test_a_charge_that_leaves_nothing_is_a_new_crossing_whatever_mark_is_left(world):
    """Out, then given exactly what the next stage costs (an admin's one credit): no charge
    left a balance to clear the mark, and the charge that spends it must still tell."""
    await _refuse(world, owner=world.owner)
    await _charge(balance_after=0, owner=world.owner, action="serp_seo")
    await _refuse(world, owner=world.owner)

    outs = [p for name, p, _ in world.sent if name == "credits_out"]
    assert outs == [{"action": "generate_outline"}, {"action": "serp_seo"}]


@pytest.mark.asyncio
async def test_a_charge_marks_the_account_out_before_it_sends_anything(world, monkeypatch):
    """A run refused while the charge's events are still on their way finds the mark."""
    seen = []

    async def report(name, properties, **kwargs):
        seen.append((name, dict(world.marks)))
        return True

    monkeypatch.setattr(account_events, "report_event", report)

    await _charge(balance_after=0, owner=world.owner)

    assert seen[0][0] == "credits_spent"
    assert seen[0][1] != {}


@pytest.mark.asyncio
async def test_without_redis_there_is_no_mark_and_every_refusal_is_told(world):
    world.cache._enabled = False

    for _ in range(2):
        await _refuse(world, owner=world.owner)
    await _charge(balance_after=0, owner=world.owner)

    assert _names(world) == ["credits_out", "credits_out", "credits_spent", "credits_out"]


@pytest.mark.asyncio
async def test_a_redis_outage_loses_no_event(world):
    """The mark is a nicety and the event is the point: when its write fails, the refusal
    is told (perhaps twice), and a charge still sends all it has to say."""
    world.cache.redis.broken = True

    await _refuse(world, owner=world.owner)
    await _charge(balance_after=0, credits=1, owner=world.owner)
    await _charge(balance_after=7, credits=1, owner=world.owner)

    assert _names(world) == ["credits_out", "credits_spent", "credits_out", "credits_spent"]


@pytest.mark.asyncio
async def test_the_marks_key_is_not_the_accounts_id(world):
    """The cache client names the key in its log lines."""
    await _refuse(world, owner=world.owner)

    (key,) = world.marks
    assert key.startswith("analytics:credits_out:")
    assert str(world.owner) not in key


@pytest.mark.asyncio
async def test_with_analytics_off_nothing_is_read_or_sent(world, monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_KEY")

    await account_events.user_signed_up(uuid4(), "credentials", AT)
    await account_events.workspace_created(uuid4(), uuid4(), AT)
    await _charge(balance_after=0)
    await _refuse(world)

    assert (world.sent, world.sessions, world.marks, world.owners_read) == ([], 0, {}, 0)


@pytest.mark.asyncio
async def test_an_event_that_fails_never_reaches_its_caller(world, monkeypatch):
    monkeypatch.setattr(account_events, "report_event", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(account_events, "_owner_of", AsyncMock(side_effect=RuntimeError("gone")))

    await account_events.user_signed_up(uuid4(), "credentials", AT)
    await account_events.workspace_created(uuid4(), uuid4(), AT)
    await _charge(balance_after=3)
    await _refuse(world)


@pytest.mark.asyncio
async def test_a_routes_background_task_starts_the_event_and_doesnt_wait_for_it(monkeypatch):
    """The tasks queued behind it (the verification email) aren't held up by analytics."""
    monkeypatch.setattr(server_events.loop_registry, "get", lambda: None)
    release, done = asyncio.Event(), asyncio.Event()

    async def slow_event(user_id, method, occurred_at):
        await release.wait()
        done.set()

    await account_events.start(slow_event, uuid4(), "credentials", AT)

    # start() is back while the event is still waiting.
    assert not done.is_set()
    release.set()
    await asyncio.wait_for(done.wait(), timeout=2)


@pytest.mark.asyncio
async def test_a_charge_reaches_the_sender_through_the_real_pieces(monkeypatch):
    """Nothing of this module or of server_events is stood in: only the request to PostHog
    and the read of the person's standing. A stand-in with the wrong shape can't hide a
    call that fails against the real cache client or the real report."""
    from src.services import money_events
    from src.services.server_events import EventContext

    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    sent = []

    async def send(event, properties, *, key, person_id=None, occurred_at=None, client=None):
        sent.append((event, properties, person_id, occurred_at))
        return True

    async def standing(_user_id):
        return EventContext(identified=True, plan={"plan": "growth"})

    monkeypatch.setattr(money_events, "send_server_event", send)
    monkeypatch.setattr(server_events, "event_context", standing)
    owner, workspace_id = uuid4(), uuid4()

    await account_events.credits_charged(
        owner,
        workspace_id,
        action="humanization",
        credits=5,
        balance_after=0,
        low_threshold=LOW_CREDITS_THRESHOLD,
        occurred_at=AT,
    )
    await account_events.credits_refused(
        uuid4(), workspace_id, action="serp_seo", occurred_at=AT, owner_id=owner
    )

    assert [event for event, *_ in sent] == [
        "credits_spent",
        # 5 to 0: it was low before this charge, so low isn't told again.
        "credits_out",
        # The global cache isn't connected in a test: no mark, so the refusal tells too.
        "credits_out",
    ]
    event, properties, person_id, occurred_at = sent[0]
    assert properties == {
        "plan": "growth",
        "action": "humanization",
        "credits": 5,
        "balance_after": 0,
        "workspace_id": str(workspace_id),
    }
    assert (person_id, occurred_at) == (str(owner), AT)


# --- the charge itself (src/utils/credit_manager.py) hands the event over and goes on


@pytest.fixture
def charge(monkeypatch):
    """A charge with its database and notices stood in; what it hands to analytics is kept.
    `outcome` is what the charge's own transaction gives: the account charged and its balance."""
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    state = SimpleNamespace(started=[], owner=uuid4())
    state.outcome = (state.owner, 96)

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
async def test_a_committed_charge_hands_its_event_over_with_the_account_it_charged(charge):
    member, workspace_id = uuid4(), uuid4()
    before = datetime.now(timezone.utc)

    await consume_stage_credits(str(member), 4, "deep_research", workspace_id=workspace_id)

    assert charge.started == [
        (
            "credits_charged",
            (charge.owner, workspace_id),
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
async def test_a_charge_refused_for_lack_of_credits_says_so_with_the_account_that_was_short(charge):
    charge.outcome = InsufficientCreditsError("humanization", 5, 2, owner_id=charge.owner)
    user_id = uuid4()

    with pytest.raises(InsufficientCreditsError):
        await consume_stage_credits(str(user_id), 5, "humanization")

    assert charge.started == [
        (
            "credits_refused",
            (user_id, None),
            {"action": "humanization", "occurred_at": ANY, "owner_id": charge.owner},
        )
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
        (
            "credits_refused",
            (user_id, None),
            {"action": "generate_outline", "occurred_at": ANY, "owner_id": None},
        )
    ]


@pytest.mark.asyncio
async def test_with_analytics_off_a_charge_hands_nothing_over(charge, monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_KEY")

    await consume_stage_credits(str(uuid4()), 1, "serp_seo")

    assert charge.started == []
