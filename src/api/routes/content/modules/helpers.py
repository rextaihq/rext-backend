from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import re

from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.content_models import Content


def slugify(text: str) -> str:
    """Convert text to URL-safe slug"""
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and underscores with hyphens
    text = re.sub(r'[\s_]+', '-', text)
    # Remove non-alphanumeric characters except hyphens
    text = re.sub(r'[^a-z0-9-]', '', text)
    # Remove multiple consecutive hyphens
    text = re.sub(r'-+', '-', text)
    # Strip hyphens from start and end
    text = text.strip('-')
    return text


async def generate_unique_slug(db: AsyncSession, base_slug: str) -> str:
    """Generate unique slug by appending number if needed"""
    slug = base_slug
    counter = 1

    while True:
        result = await db.execute(select(Content).where(Content.slug == slug, Content.deleted_at == None))
        if not result.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


# _build_content_response() function removed - replaced with Content.to_dict(include_relationships=[...])
