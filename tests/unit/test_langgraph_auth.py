"""LangGraph's own routes refuse anonymous callers and keep each user to their own threads and library."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from langgraph_sdk import Auth

from src.api.middleware.exceptions import RextAuthenticationException, TokenExpiredException
from src.api.security import auth as langgraph_auth

USER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


class _User:
    identity = USER
    is_authenticated = True
    display_name = USER
    permissions: list[str] = []


def _ctx(resource: str, action: str) -> Auth.types.AuthContext:
    return Auth.types.AuthContext(permissions=[], user=_User(), resource=resource, action=action)


@pytest.fixture
def fake_db(monkeypatch):
    """No database: the token check itself is get_current_user's, tested with it."""

    @asynccontextmanager
    async def _context():
        yield object()

    monkeypatch.setattr(langgraph_auth, "get_async_db_context", _context)


def _token_check(monkeypatch, outcome):
    async def _get_current_user(authorization, db):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(langgraph_auth, "get_current_user", _get_current_user)


def test_langgraph_json_installs_this_auth():
    config = json.loads((Path(__file__).parents[2] / "langgraph.json").read_text())

    assert config["auth"] == {
        "path": "./src/api/security/auth.py:auth",
        "disable_studio_auth": True,
    }
    assert langgraph_auth.auth._authenticate_handler is langgraph_auth.authenticate


async def test_anonymous_request_is_refused():
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.authenticate(None)

    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "error",
    [
        RextAuthenticationException(message="Invalid authentication token"),
        TokenExpiredException(),
    ],
)
async def test_bad_or_expired_token_is_refused(monkeypatch, fake_db, error):
    _token_check(monkeypatch, error)

    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.authenticate("Bearer not-a-valid-token")

    assert exc.value.status_code == 401


async def test_valid_token_speaks_for_its_user(monkeypatch, fake_db):
    _token_check(monkeypatch, {"identity": USER, "email": "user@example.com"})

    user = await langgraph_auth.authenticate("Bearer valid")

    assert user["identity"] == USER


async def test_new_thread_is_stamped_with_its_creator_over_a_forged_owner():
    value = {"thread_id": None, "metadata": {"owner": OTHER, "graph_id": "agent"}}

    filters = await langgraph_auth.own_threads(_ctx("threads", "create"), value)

    assert value["metadata"] == {"owner": USER, "graph_id": "agent"}
    assert filters == {"owner": USER}


@pytest.mark.parametrize("action", ["read", "search", "update", "delete", "create_run"])
async def test_every_thread_action_is_limited_to_the_callers_threads(action):
    filters = await langgraph_auth.own_threads(_ctx("threads", action), {"thread_id": "t"})

    assert filters == {"owner": USER}


@pytest.mark.parametrize("action", ["read", "search"])
async def test_assistants_can_be_read(action):
    assert await langgraph_auth.read_only_assistants(_ctx("assistants", action), {}) is True


@pytest.mark.parametrize("action", ["create", "update", "delete"])
async def test_assistants_cannot_be_changed(action):
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.read_only_assistants(_ctx("assistants", action), {})

    assert exc.value.status_code == 403


@pytest.mark.parametrize("action", ["create", "read", "search", "update", "delete"])
async def test_crons_are_refused(action):
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.no_crons(_ctx("crons", action), {})

    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "action, namespace",
    [
        ("search", ("library", USER, "workspace")),
        ("search", ("library", USER)),
        ("get", ("library", USER, "workspace")),
    ],
)
async def test_the_callers_own_library_can_be_read(action, namespace):
    value = {"namespace": namespace}

    assert await langgraph_auth.own_keyword_library(_ctx("store", action), value) is None


@pytest.mark.parametrize(
    "action, namespace",
    [
        ("search", ("library", OTHER, "workspace")),
        ("search", ("library",)),
        ("search", ()),
        ("search", None),
        ("search", ("brand_voice", USER)),
        ("put", ("library", USER, "workspace")),
        ("delete", ("library", USER, "workspace")),
        ("list_namespaces", ("library", USER)),
    ],
)
async def test_everything_else_in_the_store_is_refused(action, namespace):
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.own_keyword_library(_ctx("store", action), {"namespace": namespace})

    assert exc.value.status_code == 403


async def test_a_resource_without_a_rule_is_refused():
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.deny_everything_else(_ctx("runs", "create"), {})

    assert exc.value.status_code == 403


# --- content.create on generation threads and runs (E17, rext-control#368) ------

WORKSPACE = "33333333-3333-3333-3333-333333333333"


@pytest.fixture
def role(monkeypatch, fake_db):
    """The caller is an active member of WORKSPACE and holds content.create there only."""
    asked = []

    async def _check_permission(db, user_id, permission, workspace_id):
        asked.append((str(user_id), permission, str(workspace_id)))
        return permission == "content.create" and str(workspace_id) == WORKSPACE

    async def _active(db, user_id, workspace_id):
        return str(workspace_id) == WORKSPACE

    monkeypatch.setattr("src.utils.rbac_utils.check_permission", _check_permission)
    monkeypatch.setattr(langgraph_auth, "_active_in_workspace", _active)
    return asked


async def test_an_inactive_member_keeps_no_access_through_their_role(role, monkeypatch):
    # Marking a member inactive leaves their role assignment in place; the role
    # alone must not let them start or resume a generation.
    async def _inactive(db, user_id, workspace_id):
        return False

    monkeypatch.setattr(langgraph_auth, "_active_in_workspace", _inactive)

    assert not await langgraph_auth._may_create_content(USER, WORKSPACE)
    assert role == []  # refused before the role is even consulted
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.runs_need_content_create(
            _ctx("threads", "create_run"),
            {
                "thread_id": "t",
                "kwargs": {"command": {"resume": "approve"}},
                "metadata": {"workspace_id": WORKSPACE},
            },
        )
    assert exc.value.status_code == 403


async def test_a_new_thread_names_a_workspace_where_its_creator_may_create(role):
    value = {"metadata": {"owner": OTHER, "workspace_id": WORKSPACE}}

    filters = await langgraph_auth.new_threads_name_their_workspace(
        _ctx("threads", "create"), value
    )

    assert value["metadata"] == {"owner": USER, "workspace_id": WORKSPACE}
    assert filters == {"owner": USER}
    assert role == [(USER, "content.create", WORKSPACE)]


@pytest.mark.parametrize("metadata", [{}, {"workspace_id": OTHER}, {"workspace_id": "not-a-uuid"}])
async def test_a_thread_without_content_create_in_its_workspace_is_refused(role, metadata):
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.new_threads_name_their_workspace(
            _ctx("threads", "create"), {"metadata": metadata}
        )

    assert exc.value.status_code == 403


async def test_a_new_run_needs_content_create_in_its_workspace(role):
    value = {
        "thread_id": "t",
        "kwargs": {"input": {"serp_payload": {"workspace_id": WORKSPACE, "query": "q"}}},
    }

    filters = await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    assert filters == {"owner": USER, "workspace_id": WORKSPACE}
    # A run that creates its thread (if_not_exists) stamps it like threads.create.
    assert value["metadata"] == {"owner": USER, "workspace_id": WORKSPACE}


async def test_a_resume_names_the_workspace_in_its_metadata(role):
    value = {
        "thread_id": "t",
        "kwargs": {"command": {"resume": "approve"}},
        "metadata": {"workspace_id": WORKSPACE},
    }

    filters = await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    # The filter keeps the run to the caller's threads in that workspace.
    assert filters == {"owner": USER, "workspace_id": WORKSPACE}


@pytest.mark.parametrize(
    "value",
    [
        {"thread_id": "t", "kwargs": {"input": {"serp_payload": {"workspace_id": OTHER}}}},
        {
            "thread_id": "t",
            "kwargs": {"command": {"resume": "approve"}},
            "metadata": {"workspace_id": OTHER},
        },
        {"thread_id": "t", "kwargs": {"command": {"resume": "approve"}}},
    ],
)
async def test_a_viewer_can_neither_start_nor_resume_a_run(role, value):
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    assert exc.value.status_code == 403


@pytest.mark.parametrize("workspace_id", [OTHER, WORKSPACE])
async def test_a_threads_workspace_cannot_be_changed(workspace_id):
    # Runs are checked against the thread's metadata; the run works on its
    # checkpointed workspace. Renaming it would borrow another workspace's role.
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.a_threads_workspace_is_fixed(
            _ctx("threads", "update"),
            {"thread_id": "t", "metadata": {"workspace_id": workspace_id}},
        )

    assert exc.value.status_code == 403


async def test_other_thread_updates_stay_with_the_callers_threads():
    value = {"thread_id": "t", "metadata": {"owner": OTHER, "title": "Draft"}}

    filters = await langgraph_auth.a_threads_workspace_is_fixed(_ctx("threads", "update"), value)

    assert value["metadata"] == {"owner": USER, "title": "Draft"}
    assert filters == {"owner": USER}
    # Cancelling a run is an update with an action, and stays allowed.
    cancel = {"thread_id": "t", "action": "interrupt", "metadata": {"run_ids": ["r"]}}
    assert await langgraph_auth.a_threads_workspace_is_fixed(_ctx("threads", "update"), cancel) == {
        "owner": USER
    }


async def test_a_threads_state_is_changed_by_its_runs_only():
    # update_state reaches the handler with the thread id alone, not the values
    # it writes: they could put another workspace into the checkpoint.
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.a_threads_workspace_is_fixed(
            _ctx("threads", "update"), {"thread_id": "t"}
        )

    assert exc.value.status_code == 403


def test_thread_updates_go_through_the_workspace_rule():
    handlers = langgraph_auth.auth._handlers[("threads", "update")]

    assert handlers == [langgraph_auth.a_threads_workspace_is_fixed]


# --- a run is its token's user's, on a thread, resuming only (G24, rext-control#322) ---


async def test_a_run_is_its_tokens_user_whatever_its_input_named(role):
    value = {
        "thread_id": "t",
        "kwargs": {
            "input": {
                "user_id": OTHER,
                "serp_payload": {"user_id": OTHER, "workspace_id": WORKSPACE, "query": "q"},
            }
        },
    }

    await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    assert value["kwargs"]["input"]["user_id"] == USER
    assert value["kwargs"]["input"]["serp_payload"]["user_id"] == USER


async def test_a_run_whose_input_names_no_user_gets_the_tokens(role):
    value = {"thread_id": "t", "kwargs": {"input": {"serp_payload": {"workspace_id": WORKSPACE}}}}

    await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    assert value["kwargs"]["input"]["serp_payload"]["user_id"] == USER
    assert "user_id" not in value["kwargs"]["input"]  # the state's own field left as it was


async def test_during_impersonation_the_run_is_the_impersonated_users(role):
    # The impersonation token's identity is the impersonated account (the admin is
    # only original_user_id); a payload naming the admin, the browser's session user, loses.
    value = {
        "thread_id": "t",
        "kwargs": {"input": {"serp_payload": {"user_id": OTHER, "workspace_id": WORKSPACE}}},
    }

    await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    assert value["kwargs"]["input"]["serp_payload"]["user_id"] == USER


async def test_a_stateless_run_is_refused(role):
    # POST /runs/stream and /runs/wait create runs with no thread to resume the gates on.
    value = {"thread_id": None, "kwargs": {"input": {"serp_payload": {"workspace_id": WORKSPACE}}}}

    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    assert exc.value.status_code == 403
    assert role == []  # refused before any lookup


@pytest.mark.parametrize(
    "command",
    [
        {"update": {"serp_payload": {"workspace_id": OTHER}}},
        {"goto": "content_engine"},
        {"resume": "approve", "update": {"user_id": OTHER}},
    ],
)
async def test_a_run_can_only_resume_its_gates(role, command):
    value = {
        "thread_id": "t",
        "kwargs": {"command": command},
        "metadata": {"workspace_id": WORKSPACE},
    }

    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    assert exc.value.status_code == 403


# --- at most two runs in flight per user (G62, rext-control#524) ----------------------


@pytest.fixture(autouse=True)
def fresh_admissions(monkeypatch):
    """Each test admits runs from nothing, in process (no Redis), unless it sets one up."""
    from src.api.security import run_admission

    monkeypatch.setattr(run_admission, "_local_admitted", {})
    monkeypatch.setattr(run_admission, "_local_locks", {})
    monkeypatch.setattr(run_admission.cache, "_enabled", False)


def _busy(monkeypatch, thread_ids, *, fails=False):
    """The runtime's answer to "which of this user's threads are busy", through the in-process client."""
    asked = []

    class _Threads:
        async def search(self, **kwargs):
            asked.append(kwargs)
            if fails:
                raise RuntimeError("runtime unavailable")
            return [{"thread_id": t, "status": "busy"} for t in thread_ids]

    class _Client:
        threads = _Threads()

    monkeypatch.setattr("langgraph_sdk.get_client", lambda: _Client())
    return asked


def _new_run(thread_id="t-new"):
    return {
        "thread_id": thread_id,
        "kwargs": {"input": {"serp_payload": {"workspace_id": WORKSPACE, "query": "q"}}},
    }


async def test_a_third_run_in_flight_is_refused(role, monkeypatch):
    asked = _busy(monkeypatch, ["t-1", "t-2"])

    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), _new_run())

    assert exc.value.status_code == 429
    assert exc.value.detail == langgraph_auth.TOO_MANY_RUNS
    # Only the caller's own busy threads are counted.
    assert asked == [{"metadata": {"owner": USER}, "status": "busy", "limit": 3}]


async def test_a_second_run_in_flight_is_allowed(role, monkeypatch):
    _busy(monkeypatch, ["t-1"])

    scope = await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), _new_run())

    assert scope["owner"] == USER


async def test_resuming_a_busy_thread_does_not_count_it(role, monkeypatch):
    _busy(monkeypatch, ["t-1", "t-resumed"])
    resume = {"thread_id": "t-resumed", "kwargs": {"command": {"resume": {"action": "approve"}}}}
    resume["metadata"] = {"workspace_id": WORKSPACE}

    await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), resume)


async def test_a_resume_is_capped_too(role, monkeypatch):
    _busy(monkeypatch, ["t-1", "t-2"])
    resume = {
        "thread_id": "t-paused",
        "kwargs": {"command": {"resume": {"action": "approve"}}},
        "metadata": {"workspace_id": WORKSPACE},
    }

    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), resume)
    assert exc.value.status_code == 429


async def test_a_count_that_cant_be_read_does_not_hold_the_run_up(role, monkeypatch):
    _busy(monkeypatch, [], fails=True)

    scope = await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), _new_run())

    assert scope["owner"] == USER


async def test_the_cap_is_counted_only_after_the_workspace_check(role, monkeypatch):
    asked = _busy(monkeypatch, ["t-1", "t-2"])
    elsewhere = {
        "thread_id": "t",
        "kwargs": {"input": {"serp_payload": {"workspace_id": OTHER, "query": "q"}}},
    }

    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), elsewhere)

    assert exc.value.status_code == 403
    assert asked == []


async def test_three_runs_requested_together_admit_two(role, monkeypatch):
    # None is busy yet when all three are checked: the admissions count each other.
    _busy(monkeypatch, [])

    async def start(thread_id):
        try:
            await langgraph_auth.runs_need_content_create(
                _ctx("threads", "create_run"), _new_run(thread_id)
            )
            return "admitted"
        except Auth.exceptions.HTTPException as exc:
            return exc.status_code

    outcomes = await asyncio.gather(start("t-a"), start("t-b"), start("t-c"))

    assert sorted(outcomes, key=str) == [429, "admitted", "admitted"]


class _FakeRedis:
    """The few Redis calls run admission makes, in memory."""

    def __init__(self):
        self.values, self.sets = {}, {}

    async def set(self, key, value, nx=False, px=None):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.values.pop(key, None)

    async def zremrangebyscore(self, key, low, high):
        self.sets[key] = {m: s for m, s in self.sets.get(key, {}).items() if not low <= s <= high}

    async def zrange(self, key, start, end):
        return list(self.sets.get(key, {}))

    async def zadd(self, key, mapping):
        self.sets.setdefault(key, {}).update(mapping)

    async def zrem(self, key, *members):
        for member in members:
            self.sets.get(key, {}).pop(member, None)

    async def expire(self, key, seconds):
        return True


async def test_with_redis_the_admissions_hold_across_processes(role, monkeypatch):
    from src.api.security import run_admission

    redis = _FakeRedis()
    monkeypatch.setattr(run_admission.cache, "_enabled", True)
    monkeypatch.setattr(run_admission.cache, "redis", redis)
    _busy(monkeypatch, [])

    for thread_id in ("t-a", "t-b"):
        await langgraph_auth.runs_need_content_create(
            _ctx("threads", "create_run"), _new_run(thread_id)
        )
    with pytest.raises(Auth.exceptions.HTTPException) as exc:
        await langgraph_auth.runs_need_content_create(
            _ctx("threads", "create_run"), _new_run("t-c")
        )

    assert exc.value.status_code == 429
    assert set(redis.sets[f"run_admission:recent:{USER}"]) == {"t-a", "t-b"}
    assert f"run_admission:lock:{USER}" not in redis.values  # the lock is released


def _with_redis(monkeypatch):
    from src.api.security import run_admission

    redis = _FakeRedis()
    monkeypatch.setattr(run_admission.cache, "_enabled", True)
    monkeypatch.setattr(run_admission.cache, "redis", redis)
    return redis


async def _start(thread_id):
    try:
        await langgraph_auth.runs_need_content_create(
            _ctx("threads", "create_run"), _new_run(thread_id)
        )
        return "admitted"
    except Auth.exceptions.HTTPException as exc:
        return exc.status_code


async def test_a_lock_held_by_another_start_refuses_rather_than_admitting_in_process(
    role, monkeypatch
):
    from src.api.security import run_admission

    redis = _with_redis(monkeypatch)
    monkeypatch.setattr(run_admission, "_LOCK_WAIT_S", 0.1)
    redis.values[f"run_admission:lock:{USER}"] = "another start"
    _busy(monkeypatch, [])

    assert await _start("t-a") == 429
    assert run_admission._local_admitted == {}  # the in-process path never ran


@pytest.mark.parametrize("redis", [False, True], ids=["in process", "redis"])
async def test_runs_that_ended_stop_counting(role, monkeypatch, redis):
    # Two runs are admitted, then seen in flight, then end: a new run is admitted at once,
    # not only once the admission window has passed.
    if redis:
        _with_redis(monkeypatch)
    _busy(monkeypatch, [])
    assert [await _start("t-a"), await _start("t-b")] == ["admitted", "admitted"]

    _busy(monkeypatch, ["t-a", "t-b"])
    assert await _start("t-c") == 429

    _busy(monkeypatch, [])
    assert await _start("t-c") == "admitted"
