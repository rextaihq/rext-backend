"""A persona's name as it is compared for duplicates, and the check that refuses one already held.

Used where a persona is created or renamed, and where one comes back from the trash (G45).
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import DuplicateResourceException
from src.api.models.knowledge_models.persona_model import Persona


def normalized_persona_name(name):
    """A persona name as it is compared for duplicates.

    Case and repeated or surrounding whitespace are not distinctions anyone
    means to make: "Mary Jane", "mary  jane" and " Mary Jane " are one name.
    Expressed in SQL so the comparison happens in the database and two
    concurrent requests see the same answer.
    """
    return func.lower(func.regexp_replace(func.trim(name), r"\s+", " ", "g"))


async def reject_duplicate_persona_name(
    db: AsyncSession, workspace_id: UUID, name: str, exclude_id: Optional[UUID] = None
) -> None:
    """Refuse a name another live persona in this workspace already holds.

    This is what makes a rapid double-click on Create produce one persona
    rather than several: the second request finds the first one's row and is
    turned away. The frontend blocks the second click too, but a dropped
    connection, a retry or anything that is not the form would otherwise get
    through, and the check has to live where the row is written. A persona in
    the trash holds no name: a new one may take it, and that one then stops the
    trashed one coming back under it.
    """
    # One request at a time per name in a workspace, until its transaction ends: two that both
    # found the name free (a create and a restore, or a double-click) would otherwise both write.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"persona-name:{workspace_id}:{' '.join(name.split()).lower()}"},
    )
    query = select(Persona.id).where(
        Persona.workspace_id == workspace_id,
        Persona.deleted_at.is_(None),
        normalized_persona_name(Persona.name) == normalized_persona_name(name),
    )
    if exclude_id is not None:
        query = query.where(Persona.id != exclude_id)
    if (await db.execute(query.limit(1))).scalar_one_or_none():
        raise DuplicateResourceException(
            message=f"A persona named '{name.strip()}' already exists in this workspace",
            resource_type="persona",
            conflicting_field="name",
            conflicting_value=name.strip(),
        )
