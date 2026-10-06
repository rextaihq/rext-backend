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

from fastapi import Security
from fastapi.security.api_key import APIKeyHeader
from langgraph_sdk import Auth

from src.api.config import get_settings
from src.api.database.async_database import get_async_db_context
from src.api.middleware.exceptions import InvalidAPIKeyException, RextAuthenticationException
from src.api.security.dependencies import get_current_user

# Get settings instance
settings = get_settings()

auth = Auth()
API_KEY = settings.API_KEY
API_KEY_NAME = settings.API_KEY_NAME
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def _forbidden(detail: str = "Forbidden") -> Auth.exceptions.HTTPException:
    return Auth.exceptions.HTTPException(status_code=403, detail=detail)


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


async def _may_create_content(user_id: str, workspace_id: object) -> bool:
    """Whether the user holds content.create in the workspace (the role's cached permissions)."""
    from uuid import UUID

    from src.utils.rbac_utils import check_permission

    try:
        uid, wid = UUID(str(user_id)), UUID(str(workspace_id))
    except (TypeError, ValueError):
        return False
    async with get_async_db_context() as db:
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
    serp_payload = (kwargs.get("input") or {}).get("serp_payload") or {}
    workspace_id = serp_payload.get("workspace_id") or (value.get("metadata") or {}).get(
        "workspace_id"
    )
    if not await _may_create_content(ctx.user.identity, workspace_id):
        raise _forbidden(CONTENT_CREATE_REFUSED)
    return {"owner": ctx.user.identity, "workspace_id": str(workspace_id)}


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
