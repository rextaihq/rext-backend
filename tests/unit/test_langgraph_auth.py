"""LangGraph's own routes refuse anonymous callers and keep each user to their own threads and library."""

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
    """The caller holds content.create in WORKSPACE only."""
    asked = []

    async def _check_permission(db, user_id, permission, workspace_id):
        asked.append((str(user_id), permission, str(workspace_id)))
        return permission == "content.create" and str(workspace_id) == WORKSPACE

    monkeypatch.setattr("src.utils.rbac_utils.check_permission", _check_permission)
    return asked


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
    value = {"kwargs": {"input": {"serp_payload": {"workspace_id": WORKSPACE, "query": "q"}}}}

    filters = await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    assert filters == {"owner": USER, "workspace_id": WORKSPACE}
    # A run that creates its thread (if_not_exists) stamps it like threads.create.
    assert value["metadata"] == {"owner": USER, "workspace_id": WORKSPACE}


async def test_a_resume_names_the_workspace_in_its_metadata(role):
    value = {"kwargs": {"command": {"resume": "approve"}}, "metadata": {"workspace_id": WORKSPACE}}

    filters = await langgraph_auth.runs_need_content_create(_ctx("threads", "create_run"), value)

    # The filter keeps the run to the caller's threads in that workspace.
    assert filters == {"owner": USER, "workspace_id": WORKSPACE}


@pytest.mark.parametrize(
    "value",
    [
        {"kwargs": {"input": {"serp_payload": {"workspace_id": OTHER}}}},
        {"kwargs": {"command": {"resume": "approve"}}, "metadata": {"workspace_id": OTHER}},
        {"kwargs": {"command": {"resume": "approve"}}},
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
