"""Content events are recorded as events — DASH-007 and DASH-020.

The dashboard's Recent Activities panel was a listing of the content table,
which is a picture of the present. These tests pin down the three things that
made it wrong, so a later change back to reading `content` directly fails here
rather than in QA:

  - a status change adds an entry instead of overwriting one;
  - a deletion leaves an entry behind, with the title still readable;
  - the entry names whoever acted, not whoever created the article.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.api.models.audit_models.audit_logs import AuditLog
from src.api.schema.content_schema import ContentCreate, ContentUpdate
from src.services.content_activity import (
    ACTION_CREATED,
    ACTION_DELETED,
    ACTION_PUBLISHED,
    ACTION_STATUS_CHANGED,
    ACTION_UPDATED,
    CONTENT_RESOURCE,
    DELETED_STATUS,
    status_change_action,
)
from src.services.content_service import ContentService


async def _events(db_session, workspace_id):
    """Every content event in a workspace, oldest first."""
    result = await db_session.execute(
        select(AuditLog)
        .where(
            AuditLog.workspace_id == workspace_id,
            AuditLog.resource_type == CONTENT_RESOURCE,
        )
        .order_by(AuditLog.created_at.asc())
    )
    return result.scalars().all()


@pytest.mark.unit
class TestStatusChangeAction:
    """The pure part, which needs no database."""

    def test_publishing_is_called_out_separately(self):
        assert status_change_action("ready", "published") == ACTION_PUBLISHED

    def test_other_transitions_are_status_changes(self):
        assert status_change_action("draft", "ready") == ACTION_STATUS_CHANGED

    def test_no_transition_is_an_ordinary_edit(self):
        assert status_change_action("draft", "draft") == ACTION_UPDATED


@pytest.mark.unit
class TestContentActivityIsRecorded:
    @pytest.mark.asyncio
    async def test_creating_content_records_one_event(self, db_session, setup_factories):
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        service = ContentService(db_session)

        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=ContentCreate(title="A Piece Of Writing"),
        )

        events = await _events(db_session, workspace.id)
        assert [e.action for e in events] == [ACTION_CREATED]
        assert events[0].resource_id == str(content.id)
        assert events[0].new_values["title"] == "A Piece Of Writing"

    @pytest.mark.asyncio
    async def test_status_change_adds_an_entry_rather_than_overwriting(
        self, db_session, setup_factories
    ):
        """DASH-007: the bug was one row per article, rewritten in place."""
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        service = ContentService(db_session)

        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=ContentCreate(title="Draft Becoming Ready"),
        )
        await service.update_content(
            content_id=content.id,
            workspace_id=workspace.id,
            user_id=user.id,
            data=ContentUpdate(status="ready"),
        )

        events = await _events(db_session, workspace.id)
        assert [e.action for e in events] == [ACTION_CREATED, ACTION_STATUS_CHANGED]
        # The transition is readable from the entry, both ends of it.
        assert events[1].old_values["status"] == "draft"
        assert events[1].new_values["status"] == "ready"

    @pytest.mark.asyncio
    async def test_deleting_content_leaves_an_entry_with_its_title(
        self, db_session, setup_factories
    ):
        """DASH-007: a soft delete left the row untouched and said nothing."""
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id, title="About To Go", status="draft", deleted_at=None
        )
        service = ContentService(db_session)

        await service.delete_content(
            content_id=content.id, workspace_id=workspace.id, user_id=user.id
        )

        events = await _events(db_session, workspace.id)
        assert [e.action for e in events] == [ACTION_DELETED]
        # The title lives on the event, so the entry still reads correctly once
        # the article has dropped out of every listing.
        assert events[0].new_values["title"] == "About To Go"
        assert events[0].new_values["status"] == DELETED_STATUS
        assert events[0].old_values["status"] == "draft"

    @pytest.mark.asyncio
    async def test_the_event_names_the_actor_not_the_creator(self, db_session, setup_factories):
        """DASH-007: the old join credited created_by_user_id every time."""
        workspace = await setup_factories["workspace"].create()
        author = await setup_factories["user"].create()
        editor = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            created_by_user_id=author.id,
            status="draft",
            deleted_at=None,
        )
        service = ContentService(db_session)

        await service.update_content(
            content_id=content.id,
            workspace_id=workspace.id,
            user_id=editor.id,
            data=ContentUpdate(status="ready"),
        )

        events = await _events(db_session, workspace.id)
        assert events[-1].user_id == editor.id
        assert events[-1].user_id != author.id

    @pytest.mark.asyncio
    async def test_events_are_ordered_by_when_they_happened(self, db_session, setup_factories):
        """DASH-020: ordering by content.created_at never moved an edit up."""
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        service = ContentService(db_session)

        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=ContentCreate(title="Edited Later"),
        )
        await service.update_content(
            content_id=content.id,
            workspace_id=workspace.id,
            user_id=user.id,
            data=ContentUpdate(status="ready"),
        )

        events = await _events(db_session, workspace.id)
        assert events[0].created_at <= events[-1].created_at
        # Newest-first is what the endpoint serves, and the edit is newest.
        assert events[-1].action == ACTION_STATUS_CHANGED
        assert events[-1].new_values["status"] == "ready"

    @pytest.mark.asyncio
    async def test_an_edit_that_changes_no_status_is_an_ordinary_update(
        self, db_session, setup_factories
    ):
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        service = ContentService(db_session)

        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=ContentCreate(title="Retitled Only"),
        )
        await service.update_content(
            content_id=content.id,
            workspace_id=workspace.id,
            user_id=user.id,
            data=ContentUpdate(title=f"Retitled Only {uuid4().hex[:6]}"),
        )

        events = await _events(db_session, workspace.id)
        assert [e.action for e in events] == [ACTION_CREATED, ACTION_UPDATED]
        # Nothing moved, so nothing is claimed to have moved.
        assert events[-1].old_values is None
