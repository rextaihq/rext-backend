"""
Slug generation utilities for creating URL-safe identifiers
"""
import re
from typing import Optional
from sqlalchemy.orm import Session


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
    text = re.sub(r'[\s_]+', '-', text)

    # Remove all non-alphanumeric characters except hyphens
    text = re.sub(r'[^a-z0-9-]', '', text)

    # Replace multiple hyphens with single hyphen
    text = re.sub(r'-+', '-', text)

    # Strip hyphens from start and end
    text = text.strip('-')

    # If slug is empty after cleaning, generate a default
    if not text:
        text = 'workspace'

    return text


def generate_unique_slug(
    db: Session,
    base_slug: str,
    model_class,
    slug_field: str = 'slug',
    exclude_id: Optional[str] = None
) -> str:
    """
    Generate unique slug by appending number if needed

    Args:
        db: Database session
        base_slug: Base slug to make unique
        model_class: SQLAlchemy model class to check against
        slug_field: Name of the slug field in the model
        exclude_id: Optional ID to exclude from uniqueness check (for updates)

    Returns:
        Unique slug string
    """
    slug = base_slug
    counter = 1

    while True:
        # Build query to check if slug exists
        query = db.query(model_class).filter(
            getattr(model_class, slug_field) == slug,
            model_class.deleted_at == None
        )

        # Exclude current record if updating
        if exclude_id:
            query = query.filter(model_class.id != exclude_id)

        if not query.first():
            break

        # Append counter to make unique
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


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