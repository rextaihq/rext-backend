"""
Comprehensive unit tests for ContentService.

Tests cover:
- Content creation with all variations (metadata, SEO, custom fields)
- Content updates with edge cases
- Content deletion (soft delete)
- Content publishing with validation
- Slug generation and uniqueness
- Status transitions and validations
- Error handling and exceptions
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from src.services.content_service import ContentService
from src.api.schema.content_schema import (
    ContentCreate,
    ContentUpdate,
)
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException
)


@pytest.mark.unit
class TestContentServiceCreate:
    """Tests for ContentService.create_content()"""

    @pytest.mark.asyncio
    async def test_create_content_minimal_fields(self, db_session, setup_factories):
        """Test content creation with only required fields"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        content_data = ContentCreate(
            title="Minimal Content"
        )

        service = ContentService(db_session)

        # Act
        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=content_data
        )

        # Assert
        assert content.id is not None
        assert content.title == "Minimal Content"
        assert content.slug == "minimal-content"
        assert content.workspace_id == workspace.id
        assert content.created_by_user_id == user.id
        assert content.status == "draft"  # Default status
        assert content.content_language == "English"  # Default language

    @pytest.mark.asyncio
    async def test_create_content_with_all_fields(self, db_session, setup_factories):
        """Test content creation with all optional fields (flattened)"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        content_data = ContentCreate(
            title="Complete Article",
            body_markdown="# Full Content",
            status="draft",
            content_language="Spanish",
            meta_title="SEO Title",
            meta_description="SEO Description",
            focus_keyphrase="keyphrase",
            tags=["tag1", "tag2"]
        )

        service = ContentService(db_session)

        # Act
        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=content_data
        )

        # Assert
        assert content.title == "Complete Article"
        assert content.body_markdown == "# Full Content"
        assert content.content_language == "Spanish"
        assert content.meta_title == "SEO Title"
        assert content.meta_description == "SEO Description"
        assert content.focus_keyphrase == "keyphrase"
        assert content.tags == ["tag1", "tag2"]

    @pytest.mark.asyncio
    async def test_create_content_generates_unique_slug_on_duplicate(self, db_session, setup_factories):
        """Test slug uniqueness when title already exists in workspace"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        # Create first content
        await setup_factories["content"].create(
            workspace_id=workspace.id,
            title="Duplicate Title",
            slug="duplicate-title"
        )

        content_data = ContentCreate(
            title="Duplicate Title"
        )

        service = ContentService(db_session)

        # Act
        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=content_data
        )

        # Assert
        assert content.slug == "duplicate-title-1"

    @pytest.mark.asyncio
    async def test_create_content_multiple_duplicates_increments_counter(self, db_session, setup_factories):
        """Test slug counter increments for multiple duplicates"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        # Create three contents with same title
        await setup_factories["content"].create(
            workspace_id=workspace.id,
            title="Same Title",
            slug="same-title"
        )
        await setup_factories["content"].create(
            workspace_id=workspace.id,
            title="Same Title",
            slug="same-title-1"
        )

        content_data = ContentCreate(
            title="Same Title"
        )

        service = ContentService(db_session)

        # Act
        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=content_data
        )

        # Assert
        assert content.slug == "same-title-2"


@pytest.mark.unit
class TestContentServiceUpdate:
    """Tests for ContentService.update_content()"""

    @pytest.mark.asyncio
    async def test_update_content_title_regenerates_slug(self, db_session, setup_factories):
        """Test that updating title regenerates slug"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            title="Original Title",
            slug="original-title"
        )

        update_data = ContentUpdate(title="Updated Title")
        service = ContentService(db_session)

        # Act
        updated = await service.update_content(
            content_id=content.id,
            workspace_id=workspace.id,
            user_id=user.id,
            data=update_data
        )

        # Assert
        assert updated.title == "Updated Title"
        assert updated.slug == "updated-title"

    @pytest.mark.asyncio
    async def test_update_content_partial_fields(self, db_session, setup_factories):
        """Test updating only some fields leaves others unchanged"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            title="Original",
            body_markdown="Original body",
            status="draft",
            content_language="English"
        )

        update_data = ContentUpdate(
            body_markdown="Updated body only"
        )
        service = ContentService(db_session)

        # Act
        updated = await service.update_content(
            content_id=content.id,
            workspace_id=workspace.id,
            user_id=user.id,
            data=update_data
        )

        # Assert
        assert updated.title == "Original"  # Unchanged
        assert updated.body_markdown == "Updated body only"  # Changed
        assert updated.status == "draft"  # Unchanged
        assert updated.content_language == "English"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_content_status_validates_transition(self, db_session, setup_factories):
        """Test status update validates allowed transitions"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            status="draft"
        )

        # Try invalid transition
        update_data = ContentUpdate(status="published")  # draft -> published not allowed directly
        service = ContentService(db_session)

        # Act & Assert
        with pytest.raises(WrextValidationException) as exc:
            await service.update_content(
                content_id=content.id,
                workspace_id=workspace.id,
                user_id=user.id,
                data=update_data
            )

        assert "transition" in str(exc.value).lower()


@pytest.mark.unit
class TestContentServiceDelete:
    """Tests for ContentService.delete_content()"""

    @pytest.mark.asyncio
    async def test_delete_content_sets_deleted_at_timestamp(self, db_session, setup_factories):
        """Test that delete sets deleted_at timestamp (soft delete)"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            deleted_at=None
        )

        service = ContentService(db_session)

        # Act
        await service.delete_content(
            content_id=content.id,
            workspace_id=workspace.id
        )

        # Assert
        await db_session.refresh(content)
        assert content.deleted_at is not None
        assert isinstance(content.deleted_at, datetime)


@pytest.mark.unit
class TestContentServicePublish:
    """Tests for ContentService.publish_content()"""

    @pytest.mark.asyncio
    async def test_publish_content_from_ready_status_succeeds(self, db_session, setup_factories):
        """Test publishing content that is in 'ready' status"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            status="ready",
            body_markdown="# Complete article with content"
        )

        service = ContentService(db_session)

        # Act
        published = await service.publish_content(
            content_id=content.id,
            workspace_id=workspace.id,
            user_id=user.id
        )

        # Assert
        assert published.status == "published"

    @pytest.mark.asyncio
    async def test_publish_empty_content_raises_validation_error(self, db_session, setup_factories):
        """Test that publishing empty content raises validation error"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            status="ready",
            body_markdown=""  # Empty
        )

        service = ContentService(db_session)

        # Act & Assert
        with pytest.raises(WrextValidationException) as exc:
            await service.publish_content(
                content_id=content.id,
                workspace_id=workspace.id,
                user_id=user.id
            )

        assert "empty" in str(exc.value).lower()


@pytest.mark.unit
class TestContentServiceStatusTransitions:
    """Tests for ContentService._validate_status_transition()"""

    @pytest.mark.asyncio
    async def test_draft_to_ready_allowed(self, db_session):
        """Test draft → ready transition is allowed"""
        service = ContentService(db_session)
        # Should not raise
        await service._validate_status_transition("draft", "ready")

    @pytest.mark.asyncio
    async def test_ready_to_published_allowed(self, db_session):
        """Test ready → published transition is allowed"""
        service = ContentService(db_session)
        await service._validate_status_transition("ready", "published")

    @pytest.mark.asyncio
    async def test_draft_to_published_not_allowed(self, db_session):
        """Test draft → published transition is NOT allowed"""
        service = ContentService(db_session)

        with pytest.raises(WrextValidationException) as exc:
            await service._validate_status_transition("draft", "published")

        assert "transition" in str(exc.value).lower()
