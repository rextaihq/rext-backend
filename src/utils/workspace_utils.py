"""
Workspace utility functions for handling workspace resolution
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.workspace_models.workspace_model import WorkspaceModel


def is_valid_uuid(value) -> bool:
    """
    Check if a value is a valid UUID or UUID object

    Args:
        value: String or UUID object to check

    Returns:
        True if valid UUID, False otherwise
    """
    # Already a UUID object
    if isinstance(value, UUID):
        return True

    # Try to parse as UUID string
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


async def resolve_workspace(db: AsyncSession, identifier: str) -> Optional[WorkspaceModel]:
    """
    Resolve a workspace by either UUID or slug.
    Excludes soft-deleted workspaces (where deleted_at is not NULL).

    Args:
        db: Async database session
        identifier: Either a workspace UUID or slug

    Returns:
        WorkspaceModel if found and not deleted, None otherwise
    """
    if is_valid_uuid(identifier):
        # It's a UUID, query by ID
        result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.id == UUID(identifier), WorkspaceModel.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()
    else:
        # It's a slug, query by slug
        result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.slug == identifier, WorkspaceModel.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()


async def get_workspace_id_from_identifier(db: AsyncSession, identifier: str) -> Optional[UUID]:
    """
    Get workspace UUID from either a UUID string or slug

    Args:
        db: Async database session
        identifier: Either a workspace UUID or slug

    Returns:
        UUID of the workspace if found, None otherwise
    """
    workspace = await resolve_workspace(db, identifier)
    return workspace.id if workspace else None


async def verify_workspace_membership(
    db: AsyncSession, workspace_id: UUID, user_id: UUID, check_active: bool = True
) -> tuple:
    """
    Verify user is a member of workspace and return both objects.

    Args:
        db: Database session
        workspace_id: Workspace ID
        user_id: User ID
        check_active: Whether to check if membership is active

    Returns:
        tuple: (WorkspaceModel, WorkspaceMembers)

    Raises:
        ResourceNotFoundException: If workspace not found or user not a member
    """
    from src.api.models.workspace_models.workspace_member import WorkspaceMembers

    workspace_query = (
        select(WorkspaceModel, WorkspaceMembers)
        .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
        .where(
            WorkspaceModel.id == workspace_id,
            WorkspaceModel.deleted_at.is_(None),
            WorkspaceMembers.user_id == user_id,
        )
    )

    if check_active:
        workspace_query = workspace_query.where(WorkspaceMembers.status == "active")

    result = await db.execute(workspace_query)
    row = result.first()

    if not row:
        raise ResourceNotFoundException(
            resource_type="workspace",
            resource_id=str(workspace_id),
            message="Workspace not found or you are not a member",
        )

    return row[0], row[1]


async def resolve_and_verify_workspace(
    db: AsyncSession, workspace_identifier: str, user_id: UUID, check_active: bool = True
) -> tuple[WorkspaceModel, any]:
    """
    One-stop function to resolve workspace by UUID/slug and verify membership.

    This consolidates the common pattern of:
    1. Resolving workspace ID from identifier (UUID or slug)
    2. Verifying user membership

    Args:
        db: Async database session
        workspace_identifier: Either workspace UUID or slug
        user_id: User ID to verify membership
        check_active: Whether to check if membership is active (default: True)

    Returns:
        tuple: (WorkspaceModel, WorkspaceMembers)

    Raises:
        ResourceNotFoundException: If workspace not found
        RextAuthorizationException: If user not a member

    Example:
        >>> workspace, membership = await resolve_and_verify_workspace(
        ...     db, "acme-corporation", UUID("user-id")
        ... )
    """
    # Resolve workspace ID from identifier (supports both UUID and slug)
    workspace_uuid = await get_workspace_id_from_identifier(db, workspace_identifier)

    if not workspace_uuid:
        raise ResourceNotFoundException(
            message=f"Workspace '{workspace_identifier}' not found",
            resource_type="workspace",
            context={"workspace_identifier": workspace_identifier},
        )

    # Verify membership and return workspace + membership objects
    return await verify_workspace_membership(db, workspace_uuid, user_id, check_active)


# Alias for backward compatibility with older route implementations
async_get_workspace_id_from_identifier = get_workspace_id_from_identifier


async def resolve_workspace_for_route(
    *,
    db: AsyncSession,
    workspace_identifier: str,
    user: dict,
) -> tuple[WorkspaceModel, any]:
    """
    Resolve workspace and verify the current user for route handlers.

    Combines user verification with workspace resolution — the common pattern
    used by knowledge base route handlers. Extracts user_id from the user dict,
    verifies the user exists and is active, then resolves the workspace and
    verifies membership.

    Args:
        db: Async database session
        workspace_identifier: Workspace UUID string or slug
        user: User dict from get_current_user dependency (must contain "identity" key)

    Returns:
        Tuple of (WorkspaceModel, WorkspaceMembers)

    Raises:
        ResourceNotFoundException: If user not found, workspace not found, or user not a member
    """
    from src.utils.auth_utils import verify_current_user

    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    return await resolve_and_verify_workspace(db, workspace_identifier, UUID(str(user_id)))
