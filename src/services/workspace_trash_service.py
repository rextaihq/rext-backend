"""A workspace's trash: deleted articles and personas, restored, deleted for good, or purged (G45).

Deleting an article or a persona sets its `deleted_at` and `deleted_by`, and every reader leaves
such a row out. The trash lists them, newest first, with who deleted each and when, for the
dashboard's Trash table. They can be restored for TRASH_RETENTION_DAYS (30 by default, the
window a deleted workspace has in the account's trash, and the common one: Google Drive, Gmail
and WordPress keep their trash 30 days). Past that the nightly purge deletes them for good, and
a person can delete one for good sooner.

Deleting for good removes the row (an article's SEO data and publishing results go with it; an
article written as a persona keeps the article and loses the byline), the article's embedding
in the store, and the persona's uploaded photo.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, delete, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.middleware.exceptions import DuplicateResourceException, ResourceNotFoundException
from src.api.models.content_models.content import Content
from src.api.models.knowledge_models.persona_model import Persona
from src.api.models.user_models.users import Users
from src.services.content_activity import ACTION_RESTORED, record_content_activity
from src.services.persona_names import reject_duplicate_persona_name
from src.utils.logger import logger

ARTICLE = "article"
PERSONA = "persona"
KINDS = (ARTICLE, PERSONA)

# An uploaded persona photo's object key starts with this; any other avatar_url is a link.
_UPLOADED_AVATAR_PREFIX = "avatars/personas/"


def retention_days() -> int:
    return get_settings().TRASH_RETENTION_DAYS


def _cutoff(now: datetime) -> datetime:
    """Anything deleted before this is past restoring: the purge's to remove."""
    return now - timedelta(days=retention_days())


class WorkspaceTrashService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_trash(
        self,
        workspace_id: UUID,
        kinds: Sequence[str] = KINDS,
        limit: int = 100,
        offset: int = 0,
        now: Optional[datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """The workspace's trash, newest first, and how many items it holds.

        Only the kinds asked for (the caller's permissions decide which), and only what can
        still be restored.
        """
        now = now or datetime.now(timezone.utc)
        cutoff = _cutoff(now)
        parts = []
        if ARTICLE in kinds:
            parts.append(
                select(
                    literal(ARTICLE).label("kind"),
                    Content.id.label("id"),
                    Content.title.label("name"),
                    Content.deleted_at.label("deleted_at"),
                    Content.deleted_by.label("deleted_by"),
                ).where(
                    Content.workspace_id == workspace_id,
                    Content.deleted_at.is_not(None),
                    Content.deleted_at > cutoff,
                )
            )
        if PERSONA in kinds:
            parts.append(
                select(
                    literal(PERSONA).label("kind"),
                    Persona.id.label("id"),
                    Persona.name.label("name"),
                    Persona.deleted_at.label("deleted_at"),
                    Persona.deleted_by.label("deleted_by"),
                ).where(
                    Persona.workspace_id == workspace_id,
                    Persona.deleted_at.is_not(None),
                    Persona.deleted_at > cutoff,
                )
            )
        if not parts:
            return [], 0

        trash = (union_all(*parts) if len(parts) > 1 else parts[0]).subquery()
        total = await self.db.scalar(select(func.count()).select_from(trash))
        rows = (
            await self.db.execute(
                select(trash)
                .order_by(trash.c.deleted_at.desc(), trash.c.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()

        deleter_ids = {row.deleted_by for row in rows if row.deleted_by}
        deleters = {}
        if deleter_ids:
            for user in (
                await self.db.execute(
                    select(Users.id, Users.full_name, Users.display_name, Users.email).where(
                        Users.id.in_(deleter_ids)
                    )
                )
            ).all():
                deleters[user.id] = user.full_name or user.display_name or user.email

        items = []
        for row in rows:
            deadline = row.deleted_at + timedelta(days=retention_days())
            items.append(
                {
                    "kind": row.kind,
                    "id": str(row.id),
                    "name": row.name,
                    "deleted_at": row.deleted_at.isoformat(),
                    "deleted_by": (
                        {"id": str(row.deleted_by), "name": deleters.get(row.deleted_by)}
                        if row.deleted_by
                        else None
                    ),
                    "recovery_deadline": deadline.isoformat(),
                    "days_remaining": max(0, (deadline - now).days),
                }
            )
        return items, total or 0

    async def _in_trash(self, workspace_id: UUID, kind: str, item_id: UUID, now: datetime):
        model = Content if kind == ARTICLE else Persona
        item = (
            await self.db.execute(
                select(model)
                .where(
                    model.id == item_id,
                    model.workspace_id == workspace_id,
                    model.deleted_at.is_not(None),
                    model.deleted_at > _cutoff(now),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if item is None:
            raise ResourceNotFoundException(
                resource_type="article" if kind == ARTICLE else "persona",
                resource_id=str(item_id),
                message=f"That {kind} isn't in this workspace's trash",
            )
        return item

    async def restore(
        self,
        workspace_id: UUID,
        kind: str,
        item_id: UUID,
        user_id: Optional[UUID],
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Bring an item back as it was. Refused while a live one holds its name."""
        item = await self._in_trash(workspace_id, kind, item_id, now or datetime.now(timezone.utc))
        if kind == PERSONA:
            await reject_duplicate_persona_name(self.db, workspace_id, item.name)
        elif item.langgraph_thread_id is None and await self._hand_written_title_taken(item):
            # A title written by hand is unique among the live articles written by hand.
            raise DuplicateResourceException(
                message=f"An article titled '{item.title}' already exists in this workspace",
                resource_type="content",
                conflicting_field="title",
                conflicting_value=item.title,
            )

        item.deleted_at = None
        item.deleted_by = None
        await self.db.flush()
        if kind == ARTICLE:
            await record_content_activity(
                self.db, item, ACTION_RESTORED, user_id=user_id, workspace_id=workspace_id
            )
        logger.info(
            "Restored from the trash",
            extra={"workspace_id": str(workspace_id), "kind": kind, "item_id": str(item_id)},
        )
        return {
            "kind": kind,
            "id": str(item.id),
            "name": item.title if kind == ARTICLE else item.name,
        }

    async def _hand_written_title_taken(self, article: Content) -> bool:
        return bool(
            await self.db.scalar(
                select(Content.id)
                .where(
                    Content.workspace_id == article.workspace_id,
                    Content.title == article.title,
                    Content.langgraph_thread_id.is_(None),
                    Content.deleted_at.is_(None),
                    Content.id != article.id,
                )
                .limit(1)
            )
        )

    async def delete_forever(
        self, workspace_id: UUID, kind: str, item_id: UUID, now: Optional[datetime] = None
    ) -> List[str]:
        """Delete an item in the trash for good. Returns the stored files it leaves behind,
        for the caller to remove once its transaction has committed."""
        item = await self._in_trash(workspace_id, kind, item_id, now or datetime.now(timezone.utc))
        files = _uploaded_files(item) if kind == PERSONA else []
        await self.db.delete(item)
        await self.db.flush()
        if kind == ARTICLE:
            await _forget_embeddings(workspace_id, [item_id])
        logger.info(
            "Deleted from the trash for good",
            extra={"workspace_id": str(workspace_id), "kind": kind, "item_id": str(item_id)},
        )
        return files

    async def purge_expired(
        self, now: Optional[datetime] = None, batch_size: int = 500
    ) -> Dict[str, int]:
        """Delete for good everything in any workspace's trash past the retention window.

        One batch per kind at a time, each committed before the next, so no lock is held long.
        """
        cutoff = _cutoff(now or datetime.now(timezone.utc))
        purged = {ARTICLE: 0, PERSONA: 0}
        while True:
            rows = (
                await self.db.execute(
                    select(Content.id, Content.workspace_id)
                    .where(Content.deleted_at.is_not(None), Content.deleted_at <= cutoff)
                    .limit(batch_size)
                )
            ).all()
            if not rows:
                break
            await self.db.execute(
                delete(Content).where(
                    and_(Content.id.in_([r.id for r in rows]), Content.deleted_at <= cutoff)
                )
            )
            await self.db.commit()
            purged[ARTICLE] += len(rows)
            by_workspace: Dict[UUID, List[UUID]] = {}
            for row in rows:
                by_workspace.setdefault(row.workspace_id, []).append(row.id)
            for workspace_id, ids in by_workspace.items():
                await _forget_embeddings(workspace_id, ids)
        while True:
            rows = (
                await self.db.execute(
                    select(Persona.id, Persona.avatar_url)
                    .where(Persona.deleted_at.is_not(None), Persona.deleted_at <= cutoff)
                    .limit(batch_size)
                )
            ).all()
            if not rows:
                break
            await self.db.execute(
                delete(Persona).where(
                    and_(Persona.id.in_([r.id for r in rows]), Persona.deleted_at <= cutoff)
                )
            )
            await self.db.commit()
            purged[PERSONA] += len(rows)
            await remove_stored_files(
                [
                    r.avatar_url
                    for r in rows
                    if (r.avatar_url or "").startswith(_UPLOADED_AVATAR_PREFIX)
                ]
            )
        if purged[ARTICLE] or purged[PERSONA]:
            logger.info(
                "Purged the trash", extra={"articles": purged[ARTICLE], "personas": purged[PERSONA]}
            )
        return purged


async def run_trash_purge_task() -> Dict[str, int]:
    """The nightly purge (scheduled_tasks): its own session, committed batch by batch."""
    from src.api.database.async_database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        return await WorkspaceTrashService(db).purge_expired()


def _uploaded_files(persona: Persona) -> List[str]:
    url = persona.avatar_url or ""
    return [url] if url.startswith(_UPLOADED_AVATAR_PREFIX) else []


async def remove_stored_files(object_names: List[str]) -> None:
    """Best effort: a file nothing references any more is cheaper than a failed delete."""
    if not object_names:
        return
    from src.utils.storage import storage_service

    for name in object_names:
        try:
            await asyncio.to_thread(storage_service.delete_file, name)
        except Exception as exc:  # noqa: BLE001 - an orphan is not a failure
            logger.warning("could not delete stored file %s: %s", name, exc)


async def _forget_embeddings(workspace_id: UUID, content_ids: List[UUID]) -> None:
    """Best effort: an article deleted for good is no longer offered as related content."""
    from src.services.content_embedding_service import ContentEmbeddingService

    for content_id in content_ids:
        await ContentEmbeddingService.delete_content_embedding(workspace_id, content_id)
