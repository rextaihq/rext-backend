"""
Workspace utility functions for handling workspace resolution
"""
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session
from src.api.models.workspace_models.workspace_model import WorkspaceModel


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