"""An article's versions: what the editor's history lists and restores (FB2.25, rext-control #706).

A version is the article's text as a save left it. The editor saves two seconds after typing
stops, so a row per save would spend the kept versions on a few minutes of work: the saves of
one sitting (one person, five minutes) are one version, which the later saves write into. A
restore and a publish always make a version of their own. The newest `KEPT` are kept.

The first save through the editor finds an article without versions: the text it is about to
change is kept first, as the article was generated (or written, for one made by hand).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_version import ContentVersion, ContentVersionSource
from src.api.models.user_models.users import Users
from src.utils.logger import logger

KEPT = 20
SITTING = timedelta(minutes=5)

# What the editor writes and a restore puts back.
TEXT_FIELDS = ("title", "introduction", "body_markdown", "body_html", "images_data")


def text_of(article: Any) -> Dict[str, Any]:
    """The article's (or a version's) text, as the fields a version holds."""
    return {field: getattr(article, field, None) for field in TEXT_FIELDS}


def count_words(introduction: Optional[str], body_markdown: Optional[str]) -> int:
    return len(f"{introduction or ''}\n\n{body_markdown or ''}".split())


class ContentVersionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _newest(self, content_id: UUID) -> Optional[ContentVersion]:
        return await self.db.scalar(
            select(ContentVersion)
            .where(ContentVersion.content_id == content_id)
            .order_by(ContentVersion.created_at.desc(), ContentVersion.id.desc())
            .limit(1)
        )

    def _add(
        self,
        content: Content,
        text: Dict[str, Any],
        source: ContentVersionSource,
        user_id: Optional[UUID],
        at: Optional[datetime] = None,
    ) -> ContentVersion:
        version = ContentVersion(
            content_id=content.id,
            workspace_id=content.workspace_id,
            created_by_user_id=user_id,
            source=source.value,
            word_count=count_words(text.get("introduction"), text.get("body_markdown")),
            **{**text, "title": text.get("title") or content.title},
        )
        if at is not None:
            version.created_at = at
            version.updated_at = at
        self.db.add(version)
        return version

    async def _keep_the_newest(self, content_id: UUID) -> None:
        kept = (
            select(ContentVersion.id)
            .where(ContentVersion.content_id == content_id)
            .order_by(ContentVersion.created_at.desc(), ContentVersion.id.desc())
            .limit(KEPT)
        )
        await self.db.execute(
            delete(ContentVersion).where(
                ContentVersion.content_id == content_id, ContentVersion.id.not_in(kept)
            )
        )

    async def keep_as_it_is(self, content: Content, user_id: Optional[UUID]) -> None:
        """Make sure the article's text as it stands is a version (before a restore replaces
        it): a new one unless the newest already holds exactly this text."""
        newest = await self._newest(content.id)
        now_text = text_of(content)
        if newest is not None and text_of(newest) == now_text:
            return
        if newest is None:
            first = (
                ContentVersionSource.GENERATION
                if content.langgraph_thread_id
                else ContentVersionSource.EDIT
            )
            self._add(content, now_text, first, content.created_by_user_id, at=content.updated_at)
        else:
            self._add(content, now_text, ContentVersionSource.EDIT, user_id)
        await self.db.flush()

    async def record(
        self,
        content: Content,
        before: Dict[str, Any],
        user_id: Optional[UUID],
        source: ContentVersionSource = ContentVersionSource.EDIT,
        before_at: Optional[datetime] = None,
    ) -> Optional[ContentVersion]:
        """Keep the article's text as it is now, after a save that started from `before`.

        Nothing for a save that left the text as it was, unless it is a publish or a restore,
        which mark a moment of their own. An edit within the sitting of the newest version
        (the same person's edit, begun less than `SITTING` ago) is written into that version.
        """
        now_text = text_of(content)
        newest = await self._newest(content.id)
        begins = newest is None and now_text != before
        if begins:
            # The text this save replaced: the article as generated, or as first written.
            first = (
                ContentVersionSource.GENERATION
                if content.langgraph_thread_id
                else ContentVersionSource.EDIT
            )
            newest = self._add(
                content,
                before,
                first,
                content.created_by_user_id,
                at=before_at or content.created_at,
            )
            await self.db.flush()

        unchanged = newest is not None and text_of(newest) == now_text
        if source == ContentVersionSource.EDIT:
            if now_text == before or unchanged:
                return newest
            now = datetime.now(timezone.utc)
            # Never into the version made a moment ago for the text this save replaced.
            if (
                newest is not None
                and not begins
                and newest.source == ContentVersionSource.EDIT.value
                and newest.created_by_user_id == user_id
                and now - _aware(newest.created_at) < SITTING
            ):
                for field, value in now_text.items():
                    setattr(newest, field, value)
                newest.word_count = count_words(content.introduction, content.body_markdown)
                newest.updated_at = now
                await self.db.flush()
                return newest
        elif unchanged and newest.source == source.value:
            return newest

        version = self._add(content, now_text, source, user_id)
        await self.db.flush()
        await self._keep_the_newest(content.id)
        return version

    async def list(self, content_id: UUID, workspace_id: UUID) -> List[Dict[str, Any]]:
        """The article's versions, newest first, without their bodies."""
        rows = (
            await self.db.execute(
                select(ContentVersion, Users.full_name)
                .outerjoin(Users, Users.id == ContentVersion.created_by_user_id)
                .where(
                    ContentVersion.content_id == content_id,
                    ContentVersion.workspace_id == workspace_id,
                )
                .order_by(ContentVersion.created_at.desc(), ContentVersion.id.desc())
                .limit(KEPT)
            )
        ).all()
        return [summary(version, name) for version, name in rows]

    async def get(
        self, content_id: UUID, version_id: UUID, workspace_id: UUID
    ) -> tuple[ContentVersion, Optional[str]]:
        """One version of this article in this workspace, and its maker's name; 404 for a
        version of another article or another workspace."""
        row = (
            await self.db.execute(
                select(ContentVersion, Users.full_name)
                .outerjoin(Users, Users.id == ContentVersion.created_by_user_id)
                .where(
                    ContentVersion.id == version_id,
                    ContentVersion.content_id == content_id,
                    ContentVersion.workspace_id == workspace_id,
                )
            )
        ).first()
        if row is None:
            raise ResourceNotFoundException(
                resource_type="Content version", resource_id=str(version_id)
            )
        return row[0], row[1]


async def record_published(
    db: AsyncSession, content: Content, user_id: Optional[UUID] = None
) -> None:
    """Keep the text as it went out to a site, for a publish that has no request behind it
    (the scheduler's): nobody is its maker unless one is named.

    For a caller whose own work must not fail with it: the version is written inside a
    savepoint, and a failure is logged and leaves the caller's transaction as it was.
    """
    try:
        async with db.begin_nested():
            await ContentVersionService(db).record(
                content, text_of(content), user_id, ContentVersionSource.PUBLISH
            )
    except Exception:
        logger.exception(
            "The published text could not be kept as a version",
            extra={"content_id": str(content.id)},
        )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def summary(version: ContentVersion, maker: Optional[str]) -> Dict[str, Any]:
    """A version as the history lists it."""
    by = version.created_by_user_id
    return {
        "id": version.id,
        "created_at": version.created_at,
        "updated_at": version.updated_at,
        "created_by": {"id": by, "name": maker or None} if by else None,
        "source": version.source,
        "title": version.title,
        "word_count": version.word_count or 0,
    }


def detail(version: ContentVersion, maker: Optional[str]) -> Dict[str, Any]:
    """A version as the history shows it before a restore."""
    return {
        **summary(version, maker),
        "introduction": version.introduction,
        "body_markdown": version.body_markdown,
    }
