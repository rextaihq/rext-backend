"""
Workspace utility functions for handling workspace resolution
"""
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.middleware.exceptions import ResourceNotFoundException


def is_valid_uuid(value: str) -> bool:
    """
    Check if a string is a valid UUID

    Args:
        value: String to check

    Returns:
        True if valid UUID, False otherwise
    """
    try:
        UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def resolve_workspace(db: Session, identifier: str) -> Optional[WorkspaceModel]:
    """
    Resolve a workspace by either UUID or slug

    Args:
        db: Database session
        identifier: Either a workspace UUID or slug

    Returns:
        WorkspaceModel if found, None otherwise
    """
    if is_valid_uuid(identifier):
        # It's a UUID, query by ID
        return db.query(WorkspaceModel).filter(
            WorkspaceModel.id == UUID(identifier)
        ).first()
    else:
        # It's a slug, query by slug
        return db.query(WorkspaceModel).filter(
            WorkspaceModel.slug == identifier
        ).first()


def get_workspace_id_from_identifier(db: Session, identifier: str) -> Optional[UUID]:
    """
    Get workspace UUID from either a UUID string or slug

    Args:
        db: Database session
        identifier: Either a workspace UUID or slug

    Returns:
        UUID of the workspace if found, None otherwise
    """
    workspace = resolve_workspace(db, identifier)
    return workspace.id if workspace else None


async def verify_workspace_membership(
    db: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    check_active: bool = True
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
            WorkspaceMembers.user_id == user_id,
            WorkspaceModel.deleted_at == None
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
            message="Workspace not found or you are not a member"
        )

    return row[0], row[1]