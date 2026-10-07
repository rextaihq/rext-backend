"""
Route Decorators for Standardized Request Handling

This module provides decorators that handle common cross-cutting concerns in API routes:
- Database transaction management (commit/rollback)
- Error handling and logging
- Response formatting
- Request/Response tracking

These decorators eliminate 500-750 lines of duplicate try/catch/commit/rollback code
across 45+ route files.

Usage:
    from src.utils.route_decorators import db_transaction_handler

    @router.post("/items")
    @db_transaction_handler("create item", "Item created successfully")
    async def create_item(
        data: ItemCreate,
        request: Request,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
    ) -> dict:
        # Only business logic - no error handling needed
        item = Item(...)
        db.add(item)
        return {"item": item.to_dict()}
"""

import functools
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.lib.logger import auto_logger
from src.api.middleware.exceptions import RextAPIException
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.response_utils import error, success

logger = auto_logger()


def db_transaction_handler(
    operation_name: str,
    success_message: Optional[str] = None,
    auto_commit: bool = True,
    error_severity: ErrorSeverity = ErrorSeverity.HIGH,
    error_code: ErrorCode = ErrorCode.INTERNAL_SERVER_ERROR,
    include_error_details: bool = False,
):
    """
    Decorator for automatic database transaction and error handling.

    This decorator handles all the boilerplate error handling, transaction management,
    and response formatting that was previously duplicated across every route handler.

    Handles:
    - Database transaction commit on success
    - Automatic rollback on any error
    - Exception catching and structured logging
    - Standardized error response formatting
    - Success response formatting (if raw data returned)
    - Re-raising business exceptions for middleware handling

    Args:
        operation_name: Human-readable operation name for logging and error messages
                       Example: "create content", "delete persona", "update workspace"
        success_message: Optional custom success message for the response
                        If not provided, defaults to "{operation_name} completed successfully"
        auto_commit: Whether to automatically commit the transaction on success (default: True)
                    Set to False if you need manual transaction control
        error_severity: Severity level for unexpected errors (default: HIGH)
        error_code: Error code for unexpected errors (default: INTERNAL_SERVER_ERROR)
        include_error_details: Whether to include error details in logging (default: False)
                      Error details are logged but never returned to clients
    Returns:
        Decorated async function that handles transactions and errors

    Raises:
        RextAPIException: Business exceptions are re-raised after rollback for middleware handling

    Usage Example:
        @router.post("/content")
        @db_transaction_handler("create content", "Content created successfully")
        async def create_content(
            data: ContentCreate,
            request: Request,
            workspace_id: str,
            db: AsyncSession = Depends(get_async_db),
            user: dict = Depends(get_current_user)
        ) -> dict:
            # Verify workspace access and membership
            from src.utils.workspace_utils import resolve_and_verify_workspace
            from uuid import UUID
            workspace, membership = await resolve_and_verify_workspace(
                db, workspace_id, UUID(user["identity"])
            )

            # Create content
            content = Content(workspace_id=workspace.id, title=data.title, ...)
            db.add(content)

            # Return raw data - decorator handles success response formatting
            return {"content": content.to_dict()}

    Best Practices:
    - Route handlers should return raw dict data (not JSONResponse)
    - Decorator automatically formats raw data into standardized success responses
    - RextAPIException subclasses are re-raised (handled by exception middleware)
    - Database session parameter must be named 'db' in function signature
    - Request parameter must be named 'request' for tracking
    - Always include meaningful operation names for debugging

    What Changes:
    BEFORE (with decorator):
        try:
            # ... business logic ...
            await db.commit()
            return success(data={...}, request=request, message="...")
        except RextValidationException:
            raise
        except Exception as e:
            await db.rollback()
            logger.exception(f"Error: {e}")
            return error(message="...", status_code=500, request=request)

    AFTER (with decorator):
        @db_transaction_handler("operation name", "Success message")
        async def handler(...):
            # ... business logic only ...
            return {"data": ...}
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Extract dependencies from kwargs
            # These are injected by FastAPI's dependency injection system
            request: Optional[Request] = kwargs.get("request")
            db: Optional[AsyncSession] = kwargs.get("db")

            try:
                # Execute the route handler with business logic
                result = await func(*args, **kwargs)

                # Auto-commit transaction if db session present and enabled
                if db and auto_commit and hasattr(db, "commit"):
                    await db.commit()
                    logger.debug(f"Transaction committed: {operation_name}")

                # Auto-format success response if raw data returned.
                # A handler that builds its own response (JSON, a CSV or a file
                # download) passes through unchanged: wrapping it would try to
                # JSON-encode the Response object and fail with a 500.
                if not isinstance(result, Response):
                    return success(
                        data=result,
                        request=request,
                        message=success_message
                        or f"{operation_name.capitalize()} completed successfully",
                    )

                # Return the handler's own response as-is
                return result

            except HTTPException:
                if db and hasattr(db, "rollback"):
                    await db.rollback()
                raise

            except RextAPIException as e:
                # Business/validation exceptions - rollback and re-raise
                # These are handled by the global exception middleware
                if db and hasattr(db, "rollback"):
                    await db.rollback()
                    logger.debug(
                        f"Transaction rolled back: {operation_name}",
                        extra={"operation": func.__name__},
                    )

                # Log business exception at WARNING level (not ERROR)
                logger.warning(
                    f"Business exception in {operation_name}: {e.message}",
                    extra={
                        "operation": func.__name__,
                        "error_code": e.error_code.value,
                        "status_code": e.status_code,
                        "severity": e.severity.value,
                    },
                )

                # Re-raise to be handled by exception middleware
                # This ensures consistent error response formatting
                raise

            except Exception as e:
                # Unexpected errors - rollback and return error response
                if db and hasattr(db, "rollback"):
                    await db.rollback()
                    logger.debug(
                        f"Transaction rolled back: {operation_name}",
                        extra={"operation": func.__name__},
                    )

                # Log unexpected exception at ERROR level with full stack trace
                # include_error_details controls whether we log additional context
                if include_error_details:
                    logger.exception(
                        f"Unexpected error in {operation_name}",
                        extra={
                            "operation": func.__name__,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    )
                else:
                    logger.exception(
                        f"Unexpected error in {operation_name}", extra={"operation": func.__name__}
                    )

                # Return standardized error response without context parameter
                # Error details are logged above but not included in the response
                return error(
                    message=f"Failed to {operation_name}",
                    code=error_code,
                    status_code=500,
                    severity=error_severity,
                    request=request,
                )

        return wrapper

    return decorator


def require_permissions(
    *permissions: str,
    workspace_scoped: bool = False,
    require_all: bool = True,
    allow_roles: tuple[str, ...] = (),
):
    """
    Decorator to require specific permissions before route execution.

    This decorator enforces Role-Based Access Control (RBAC) by checking if the
    current user has the required permissions before allowing the route to execute.
    It integrates with the RBAC utilities to perform async permission checks.

    Args:
        *permissions: Variable number of permission names required
                     (e.g., "content.delete", "content.publish")
        workspace_scoped: Whether permissions are workspace-scoped (default: False)
                         If True, checks permissions within the specified workspace.
                         If False, checks global permissions only -- so a route
                         that takes a workspace_id but omits this flag silently
                         checks the caller's GLOBAL roles and will reject any
                         member whose permission comes from a workspace role.
        require_all: Require ALL permissions (AND logic) or ANY permission (OR logic)
                    Default: True (user must have ALL specified permissions)
        allow_roles: Global role NAMES that bypass the permission check (OR logic:
                    the caller passes with the permission OR one of these roles).
                    Used where a permission is too broadly held to gate on — e.g.
                    user.read is the self-service permission every account has,
                    so read-only admin visibility for Support is keyed on its
                    global role name instead. Only global roles appear in the
                    signed JWT's roles claim, so a same-named workspace role
                    never matches.

    Expected Parameters in Route:
        - workspace_id: str parameter (if workspace_scoped=True)
                       Can be UUID or slug - will be resolved to UUID
        - user: dict parameter (from get_current_user dependency)
                Must contain "identity" key with user UUID
        - db: AsyncSession parameter (from get_async_db dependency)

    Raises:
        RextAuthorizationException: If user lacks required permission(s)
        ValueError: If required parameters (user, db, workspace_id) are missing

    Usage Examples:
        # Single permission (DELETE route)
        @router.delete("/{content_id}")
        @db_transaction_handler("delete content")
        @require_permissions("content.delete", workspace_scoped=True)
        async def delete_content(
            content_id: str,
            workspace_id: str,
            user: dict = Depends(get_current_user),
            db: AsyncSession = Depends(get_async_db),
            request: Request
        ) -> dict:
            # Permission already verified - only business logic here
            content = await get_or_404(db, Content, content_id)
            await db.delete(content)
            return {"deleted_id": content_id}

        # Multiple permissions (AND logic - require ALL)
        @router.put("/publish/{content_id}")
        @db_transaction_handler("publish content")
        @require_permissions("content.publish", "content.update", workspace_scoped=True)
        async def publish_content(
            content_id: str,
            workspace_id: str,
            user: dict,
            db: AsyncSession,
            request: Request
        ) -> dict:
            # User must have BOTH content.publish AND content.update
            pass

        # Multiple permissions (OR logic - require ANY)
        @router.get("/admin")
        @require_permissions("admin.access", "superadmin.access", require_all=False)
        async def admin_panel(
            user: dict,
            db: AsyncSession
        ) -> dict:
            # User needs EITHER admin.access OR superadmin.access
            pass

        # Global permission (not workspace-scoped)
        @router.post("/users")
        @db_transaction_handler("create user")
        @require_permissions("user.create", workspace_scoped=False)
        async def create_user(
            data: UserCreate,
            user: dict,
            db: AsyncSession,
            request: Request
        ) -> dict:
            # Global permission check (applies system-wide)
            pass

    Best Practices:
        - Apply AFTER @router decorator but BEFORE/AFTER @db_transaction_handler
        - Use workspace_scoped=True for workspace-specific resources (content, personas, brand voice)
        - Use workspace_scoped=False for global resources (users, system settings)
        - Order decorators logically: @router → @db_transaction_handler → @require_permissions
        - For destructive operations (delete, publish), always check permissions
        - For read operations, use "{resource}.read" permission
        - Log permission checks are automatic (via rbac_utils)

    Security Notes:
        - Permission checks are performed BEFORE route execution
        - Uses AsyncSession for database queries (compatible with FastAPI async routes)
        - Workspace isolation is enforced (users can't access other workspaces)
        - Error messages don't leak sensitive information (generic "insufficient permissions")
        - Failed permission checks are logged for audit trails
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            from uuid import UUID

            from src.api.middleware.exceptions import RextAuthorizationException
            from src.utils.rbac_utils import (
                check_all_permissions,
                check_any_permission,
                is_user_super_admin,
            )
            from src.utils.workspace_utils import async_get_workspace_id_from_identifier

            # Extract required dependencies from kwargs
            # Prioritize 'current_user' (standard auth dependency name)
            # over generic 'user' which might be a payload model
            user = kwargs.get("current_user") or kwargs.get("user")
            db = kwargs.get("db")

            if not user or not db:
                raise ValueError(
                    "require_permissions decorator requires 'current_user' (or 'user') and 'db' parameters in route signature"
                )

            # Safety check: Ensure user is a dict and has 'identity'
            # This prevents picking up Pydantic models named 'user' from the payload
            if not isinstance(user, dict) or "identity" not in user:
                # If we have both, maybe 'current_user' is the real one
                if "current_user" in kwargs and isinstance(kwargs["current_user"], dict):
                    user = kwargs["current_user"]
                else:
                    logger.error(
                        f"require_permissions decorator found invalid user object in {func.__name__}. "
                        f"Expected dict with 'identity', got {type(user).__name__}",
                        extra={"operation": func.__name__},
                    )
                    raise ValueError(
                        f"require_permissions decorator in {func.__name__} could not find a valid authenticated user object. "
                        f"Check if Depends(get_current_user) is added to the route."
                    )

            user_id = UUID(user.get("identity"))
            workspace_uuid = None

            # Resolve workspace if scoped
            if workspace_scoped:
                workspace_id_param = kwargs.get("workspace_id")
                if not workspace_id_param:
                    logger.error(
                        f"require_permissions with workspace_scoped=True requires 'workspace_id' parameter "
                        f"in route signature for {func.__name__}",
                        extra={"operation": func.__name__, "permissions": list(permissions)},
                    )
                    raise ValueError(
                        f"require_permissions with workspace_scoped=True requires 'workspace_id' parameter "
                        f"in route signature. Route: {func.__name__}"
                    )

                # Resolve workspace ID (handles both UUID and slug)
                try:
                    workspace_uuid = UUID(str(workspace_id_param))
                except ValueError:
                    workspace_uuid = await async_get_workspace_id_from_identifier(
                        db, workspace_id_param
                    )
            # SECURITY INVARIANT:
            # Never bypass permission checks based on DB/session attributes (for example `_executed`).
            # Tests must use dependency overrides or monkeypatching, not production bypass branches.
            # Global super_admin bypass:
            # super_admin is defined as "all permissions" (seed grants "*") and is
            # always a global role (workspace_id IS NULL, hierarchy_level >= 100).
            # Honour that directly so a stale/incomplete role_permissions mapping
            # can't lock a super_admin out of platform routes.

            # Global super_admin bypass:
            # Query PostgreSQL database authority to verify active super_admin role
            try:
                is_super = await is_user_super_admin(db, user_id)
            except Exception:
                logger.warning(
                    "super_admin check failed; falling back to permission check",
                    exc_info=True,
                    extra={"operation": func.__name__},
                )
                is_super = False

            if is_super:
                return await func(*args, **kwargs)

            # Optional role-based admission (OR with the permission check).
            # The signed JWT's roles claim lists only GLOBAL role names, so a
            # workspace-scoped role with the same name never matches here.
            if allow_roles and set(user.get("roles") or []) & set(allow_roles):
                return await func(*args, **kwargs)

            check_func = check_all_permissions if require_all else check_any_permission
            try:
                has_permission = await check_func(db, user_id, list(permissions), workspace_uuid)
            except Exception as exc:
                logger.error(
                    "Permission evaluation failed; denying request",
                    exc_info=True,
                    extra={
                        "operation": func.__name__,
                        "permissions": list(permissions),
                        "workspace_id": str(workspace_uuid) if workspace_uuid else None,
                    },
                )
                raise RextAuthorizationException(
                    message="Permission verification failed",
                    context={
                        "required_permissions": list(permissions),
                        "workspace_id": str(workspace_uuid) if workspace_uuid else None,
                        "logic": "AND" if require_all else "OR",
                        "failure_mode": "permission_check_exception",
                    },
                ) from exc

            if not has_permission:
                # Permission check failed - user lacks required permissions
                logger.warning(
                    f"Access denied: user {user_id} lacks permissions {list(permissions)} for workspace {workspace_uuid}",
                    extra={
                        "operation": func.__name__,
                        "user_id": str(user_id),
                        "workspace_id": str(workspace_uuid) if workspace_uuid else None,
                        "required_permissions": list(permissions),
                    },
                )
                raise RextAuthorizationException(
                    message="You do not have permission to perform this action",
                    context={
                        "required_permissions": list(permissions),
                        "workspace_id": str(workspace_uuid) if workspace_uuid else None,
                        "logic": "AND" if require_all else "OR",
                    },
                )

            # Permission check passed - execute the route
            return await func(*args, **kwargs)

        return wrapper

    return decorator
