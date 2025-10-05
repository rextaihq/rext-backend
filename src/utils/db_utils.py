"""Database utility functions for common operations."""

from typing import Type, TypeVar, Any, Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    DuplicateResourceException
)

T = TypeVar('T')


async def get_or_404(
    db: AsyncSession,
    model: Type[T],
    resource_id: UUID,
    resource_type: Optional[str] = None,
    additional_filters: Optional[List] = None
) -> T:
    """
    Get resource by ID or raise 404.

    Args:
        db: Database session
        model: SQLAlchemy model class
        resource_id: ID of resource to fetch
        resource_type: Optional resource type name for error message
        additional_filters: Optional additional filter clauses

    Returns:
        T: The resource object

    Raises:
        ResourceNotFoundException: If resource not found
    """
    query = select(model).where(model.id == resource_id)

    if additional_filters:
        for filter_clause in additional_filters:
            query = query.where(filter_clause)

    result = await db.execute(query)
    resource = result.scalar_one_or_none()

    if not resource:
        raise ResourceNotFoundException(
            resource_type=resource_type or model.__tablename__,
            resource_id=str(resource_id)
        )

    return resource


async def ensure_unique(
    db: AsyncSession,
    model: Type[T],
    field: str,
    value: Any,
    resource_type: Optional[str] = None,
    error_message: Optional[str] = None,
    exclude_id: Optional[UUID] = None
) -> None:
    """
    Ensure field value is unique, raise DuplicateResourceException if not.

    Args:
        db: Database session
        model: SQLAlchemy model class
        field: Field name to check uniqueness
        value: Value that should be unique
        resource_type: Optional resource type name for error
        error_message: Optional custom error message
        exclude_id: Optional ID to exclude from uniqueness check (for updates)

    Raises:
        DuplicateResourceException: If value already exists
    """
    query = select(model).where(getattr(model, field) == value)

    if exclude_id:
        query = query.where(model.id != exclude_id)

    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    if existing:
        raise DuplicateResourceException(
            resource_type=resource_type or model.__tablename__,
            conflicting_field=field,
            conflicting_value=str(value),
            message=error_message or f"{field.replace('_', ' ').title()} already exists"
        )
