"""
Authentication and authorization for LangGraph's own routes.

``langgraph.json``'s ``auth.path`` installs ``auth``, so every request to the
threads, runs, assistants, crons and store routes must carry the same bearer
token the app's own routes accept. The app's FastAPI routes are not affected:
they authenticate with their own dependencies (``http.enable_custom_route_auth``
stays off). In-process calls (``langgraph_sdk.get_client()`` with no URL) skip
authentication and carry no user, so the handlers below do not run for them.
"""

import hmac
import logging

from fastapi import Security
from fastapi.security.api_key import APIKeyHeader
from langgraph_sdk import Auth

from src.api.config import get_settings
from src.api.database.async_database import get_async_db_context
from src.api.middleware.exceptions import InvalidAPIKeyException, RextAuthenticationException
from src.api.security.dependencies import get_current_user
from src.api.security.run_admission import MAX_ACTIVE_RUNS, admit_run

logger = logging.getLogger(__name__)

# Get settings instance
settings = get_settings()

auth = Auth()
API_KEY = settings.API_KEY
API_KEY_NAME = settings.API_KEY_NAME
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def _forbidden(detail: str = "Forbidden") -> Auth.exceptions.HTTPException:
    return Auth.exceptions.HTTPException(status_code=403, detail=detail)


TOO_MANY_RUNS = (
    f"You already have {MAX_ACTIVE_RUNS} articles generating. "
    "Wait for one to finish, then start another."
)


async def _busy_threads(identity: str) -> set[str]:
    """The ids of the user's threads with a run in flight.

    Read through the in-process client, which skips these handlers. If they can't be
    read, none count: the run isn't held up, and the credit checks still apply to it.
    """
    from langgraph_sdk import get_client

    try:
        threads = await get_client().threads.search(
            metadata={"owner": identity}, status="busy", limit=MAX_ACTIVE_RUNS + 1
        )
    except Exception as exc:
        # The class only: the error's text can carry the owner id the query was bound with.
        logger.warning("active-run cap: could not count busy threads (%s)", type(exc).__name__)
        return set()
    return {str(thread.get("thread_id")) for thread in threads}


@auth.authenticate
async def authenticate(authorization: str | None) -> Auth.types.MinimalUserDict:
    """Accept the token the dashboard holds for its user, checked as the app's routes check it."""
    if not authorization:
        raise Auth.exceptions.HTTPException(status_code=401, detail="Authorization header missing")

    try:
        async with get_async_db_context() as db:
            return await get_current_user(authorization, db)
    except RextAuthenticationException as exc:
        raise Auth.exceptions.HTTPException(status_code=401, detail=exc.message) from None


@auth.on.threads
async def own_threads(ctx: Auth.types.AuthContext, value: dict) -> Auth.types.FilterType:
    """A thread belongs to the user who created it; its runs and state come with it."""
    owner = {"owner": ctx.user.identity}
    metadata = value.setdefault("metadata", {})
    metadata.update(owner)
    return owner


CONTENT_CREATE_REFUSED = (
    "Starting or continuing an article needs the content.create permission in this workspace"
)


async def _active_in_workspace(db, user_id, workspace_id) -> bool:
    """A platform admin, the workspace's owner, or an active member of it (not deleted).

    The same gate workspace access applies elsewhere (workspace_permission_service):
    a member marked inactive keeps their role assignment, so the role alone
    would still let them in.
    """
    from sqlalchemy import select

    from src.api.models.workspace_models.workspace_member import WorkspaceMembers
    from src.api.models.workspace_models.workspace_model import WorkspaceModel
    from src.utils.rbac_utils import is_user_admin

    if await is_user_admin(db, user_id):
        return True
    owned = await db.execute(
        select(WorkspaceModel.id).where(
            WorkspaceModel.id == workspace_id,
            WorkspaceModel.user_id == user_id,
            WorkspaceModel.deleted_at.is_(None),
        )
    )
    if owned.scalar_one_or_none() is not None:
        return True
    member = await db.execute(
        select(WorkspaceMembers.user_id)
        .join(WorkspaceModel, WorkspaceModel.id == WorkspaceMembers.workspace_id)
        .where(
            WorkspaceMembers.workspace_id == workspace_id,
            WorkspaceMembers.user_id == user_id,
            WorkspaceMembers.status == "active",
            WorkspaceModel.deleted_at.is_(None),
        )
    )
    return member.scalar_one_or_none() is not None


async def _may_create_content(user_id: str, workspace_id: object) -> bool:
    """Whether the user may create content in the workspace: active there, and content.create in their role."""
    from uuid import UUID

    from src.utils.rbac_utils import check_permission

    try:
        uid, wid = UUID(str(user_id)), UUID(str(workspace_id))
    except (TypeError, ValueError):
        return False
    async with get_async_db_context() as db:
        if not await _active_in_workspace(db, uid, wid):
            return False
        return await check_permission(db, uid, "content.create", wid)


@auth.on.threads.create
async def new_threads_name_their_workspace(
    ctx: Auth.types.AuthContext, value: dict
) -> Auth.types.FilterType:
    """A generation thread names its workspace, where its creator may create content.

    The workspace stays in the thread's metadata, so every later run on the thread
    is checked against it (runs_need_content_create) and can't name another.
    """
    metadata = value.setdefault("metadata", {})
    if not await _may_create_content(ctx.user.identity, metadata.get("workspace_id")):
        raise _forbidden(CONTENT_CREATE_REFUSED)
    metadata["owner"] = ctx.user.identity
    return {"owner": ctx.user.identity}


WORKSPACE_FIXED = "A thread's workspace is set when it is created and can't be changed"
STATE_FROM_RUNS_ONLY = "A thread's state is changed by its runs only"


@auth.on.threads.update
async def a_threads_workspace_is_fixed(
    ctx: Auth.types.AuthContext, value: dict
) -> Auth.types.FilterType:
    """The caller's own threads, with the workspace they were created in.

    Runs are checked against the workspace in the thread's metadata
    (runs_need_content_create), while the run itself works on the workspace in
    its checkpointed state. Letting the owner rename it would let someone who
    lost content.create in one workspace resume there under another's role.
    """
    # A state update (update_state) reaches this handler with the thread id
    # alone: no metadata and no action, and not the values it writes. Those
    # could put another workspace into the checkpoint's serp_payload, which a
    # resume then works on while being checked against the metadata's. A
    # thread's state is changed by its runs only; the dashboard never sets it.
    if "metadata" not in value and not value.get("action"):
        raise _forbidden(STATE_FROM_RUNS_ONLY)
    metadata = value.get("metadata") or {}
    if "workspace_id" in metadata:
        raise _forbidden(WORKSPACE_FIXED)
    owner = {"owner": ctx.user.identity}
    if value.get("metadata") is not None:
        value["metadata"].update(owner)
    return owner


RUN_NEEDS_A_THREAD = "A run needs a thread: its gates are resumed on it"
RESUME_ONLY = "A run can only resume its gates"


def _bind_to_its_user(identity: str, run_input: object) -> None:
    """The run's user is the token's, whatever its input named.

    The graph charges credits to, records content for and reads the keyword
    library of the user in its input's serp_payload (and the state's user_id).
    During impersonation the token's user is the impersonated account.
    """
    if not isinstance(run_input, dict):
        return
    if "user_id" in run_input:
        run_input["user_id"] = identity
    if isinstance(run_input.get("serp_payload"), dict):
        run_input["serp_payload"]["user_id"] = identity


@auth.on.threads.create_run
async def runs_need_content_create(
    ctx: Auth.types.AuthContext, value: dict
) -> Auth.types.FilterType:
    """Starting a run, or resuming one at a gate, needs content.create in the thread's workspace.

    A new run names its workspace in its input's serp_payload; a resume carries no
    input and names it in the run's metadata. The filter matches only the caller's
    own threads in that workspace, so a run can't borrow another workspace's role.
    """
    kwargs = value.get("kwargs") or {}
    # A stateless run (POST /runs/stream or /runs/wait) has no thread to resume
    # its gates on; it would only spend credits before stopping at the first.
    if value.get("thread_id") is None:
        raise _forbidden(RUN_NEEDS_A_THREAD)
    # Resuming answers a gate. A command that writes the state or jumps to a node
    # would run on values this check never saw (another workspace, another user).
    command = kwargs.get("command") or {}
    if command.get("update") is not None or command.get("goto"):
        raise _forbidden(RESUME_ONLY)
    serp_payload = (kwargs.get("input") or {}).get("serp_payload") or {}
    workspace_id = serp_payload.get("workspace_id") or (value.get("metadata") or {}).get(
        "workspace_id"
    )
    if not await _may_create_content(ctx.user.identity, workspace_id):
        raise _forbidden(CONTENT_CREATE_REFUSED)
    # Starting or resuming a run starts paid work: at most MAX_ACTIVE_RUNS per user,
    # admitted atomically so runs requested together count each other (run_admission).
    identity = ctx.user.identity
    if not await admit_run(identity, value.get("thread_id"), lambda: _busy_threads(identity)):
        raise Auth.exceptions.HTTPException(status_code=429, detail=TOO_MANY_RUNS)
    _bind_to_its_user(ctx.user.identity, kwargs.get("input"))
    scope = {"owner": ctx.user.identity, "workspace_id": str(workspace_id)}
    # A run that creates its own thread (if_not_exists="create") stamps it with
    # these, as threads.create does; for any other run they're the run's own.
    value.setdefault("metadata", {}).update(scope)
    return scope


@auth.on.assistants
async def read_only_assistants(ctx: Auth.types.AuthContext, value: dict) -> bool:
    """The graph's assistant is shared: runs name it, nobody changes it over HTTP."""
    if ctx.action in ("read", "search"):
        return True
    raise _forbidden("Assistants are read-only")


@auth.on.crons
async def no_crons(ctx: Auth.types.AuthContext, value: dict) -> bool:
    """Nothing schedules runs through LangGraph's crons; a cron would spend credits unattended."""
    raise _forbidden("Scheduled runs are not available")


@auth.on.store
async def own_keyword_library(ctx: Auth.types.AuthContext, value: dict) -> None:
    """The dashboard reads one store namespace over HTTP: the caller's keyword library.

    Its items live under ``("library", <user id>, <workspace id>)``; the graph
    writes them in-process, and deleting goes through the app's own route.
    """
    namespace = tuple(value.get("namespace") or ())
    if ctx.action not in ("search", "get") or namespace[:2] != ("library", ctx.user.identity):
        raise _forbidden()


@auth.on
async def deny_everything_else(ctx: Auth.types.AuthContext, value: dict) -> bool:
    """A resource or action without a rule above is refused."""
    raise _forbidden()


def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header:
        raise InvalidAPIKeyException(message="API key is required")

    if not API_KEY or not hmac.compare_digest(api_key_header, API_KEY):
        raise InvalidAPIKeyException(message="Invalid API key provided")

    return api_key_header
