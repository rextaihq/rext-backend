"""
Slug generation utilities for creating URL-safe identifiers
"""

import re
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def slugify(text: str) -> str:
    """
    Convert text to URL-safe slug

    Args:
        text: The text to convert to slug

    Returns:
        URL-safe slug string
    """
    # Convert to lowercase
    text = text.lower()

    # Replace spaces, underscores, and multiple spaces with hyphens
    text = re.sub(r"[\s_]+", "-", text)

    # Remove all non-alphanumeric characters except hyphens
    text = re.sub(r"[^a-z0-9-]", "", text)

    # Replace multiple hyphens with single hyphen
    text = re.sub(r"-+", "-", text)

    # Strip hyphens from start and end
    text = text.strip("-")

    # If slug is empty after cleaning, generate a default
    if not text:
        text = "workspace"

    return text


async def generate_unique_slug(
    db: AsyncSession,
    base_slug: str,
    model_class,
    slug_field: str = "slug",
    exclude_id: Optional[UUID] = None,
    workspace_id: Optional[UUID] = None,
    workspace_field: str = "workspace_id",
) -> str:
    """
    Generate unique slug by appending number if needed.
    Optimized to fetch all matching slugs in a single query.

    Args:
        db: Async database session
        base_slug: Base slug to make unique
        model_class: SQLAlchemy model class to check against
        slug_field: Name of the slug field in the model
        exclude_id: Optional ID to exclude from uniqueness check (for updates)
        workspace_id: Optional workspace ID for scoped uniqueness
        workspace_field: Name of the workspace_id field in the model

    Returns:
        Unique slug string
    """
    slug_col = getattr(model_class, slug_field)
    pattern = f"{base_slug}%"

    query = select(slug_col).where(
        slug_col.like(pattern),
        model_class.deleted_at.is_(None),
    )

    if workspace_id is not None:
        query = query.where(getattr(model_class, workspace_field) == workspace_id)

    if exclude_id is not None:
        query = query.where(model_class.id != exclude_id)

    result = await db.execute(query)
    existing_slugs = {row[0] for row in result.fetchall()}

    if base_slug not in existing_slugs:
        return base_slug

    counter = 1
    while f"{base_slug}-{counter}" in existing_slugs:
        counter += 1
    return f"{base_slug}-{counter}"


def generate_workspace_slug(name: str) -> str:
    """
    Generate a workspace slug from workspace name

    Args:
        name: Workspace name

    Returns:
        Workspace slug
    """
    # First slugify the name
    slug = slugify(name)

    # Ensure minimum length
    if len(slug) < 3:
        slug = f"workspace-{slug}" if slug else "workspace"

    return slug
