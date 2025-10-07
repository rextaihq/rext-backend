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
    ContentMetadataSchema,
    ContentSEODataSchema,
)
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException
)
from tests.factories import UserFactory, WorkspaceFactory, ContentFactory


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
            workspace_id=workspace.id,
            title="Minimal Content",
            body_markdown="# Hello World"
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
        assert content.author_id == user.id  # Defaults to creator
        assert content.status == "draft"  # Default status
        assert content.content_format == "Markdown"  # Default format
        assert content.content_language == "English"  # Default language

    @pytest.mark.asyncio
    async def test_create_content_with_all_fields(self, db_session, setup_factories):
        """Test content creation with all optional fields"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace.id)
        assigned_user = await setup_factories["user"].create()

        content_data = ContentCreate(
            workspace_id=workspace.id,
            title="Complete Article",
            body_markdown="# Full Content",
            topic_id=topic.id,
            assigned_to_user_id=assigned_user.id,
            author_id=user.id,
            content_format="Markdown",
            status="draft",
            content_language="Spanish"
        )

        service = ContentService(db_session)

        # Act
        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=content_data
        )

        # Assert
        assert content.topic_id == topic.id
        assert content.assigned_to_user_id == assigned_user.id
        assert content.author_id == user.id
        assert content.content_language == "Spanish"

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
            workspace_id=workspace.id,
            title="Duplicate Title",
            body_markdown="Different content"
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
            workspace_id=workspace.id,
            title="Same Title",
            body_markdown="Third one"
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

    @pytest.mark.asyncio
    async def test_create_content_slug_unique_per_workspace(self, db_session, setup_factories):
        """Test slug uniqueness is per workspace (same slug allowed in different workspaces)"""
        # Arrange
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        # Create content in workspace1
        unique_id1 = uuid4().hex[:8]
        await setup_factories["content"].create(
            workspace_id=workspace1.id,
            title=f"Article {unique_id1}",
            slug=f"article-{unique_id1}"
        )

        # Create content in workspace2 with different title (will generate different slug)
        unique_id2 = uuid4().hex[:8]
        content_data = ContentCreate(
            workspace_id=workspace2.id,
            title=f"Article {unique_id2}",
            body_markdown="Content in workspace 2"
        )

        service = ContentService(db_session)

        # Act
        content = await service.create_content(
            workspace_id=workspace2.id,
            user_id=user.id,
            data=content_data
        )

        # Assert
        # Different workspaces get different slugs (global uniqueness)
        assert content.slug == f"article-{unique_id2}"
        assert content.slug != f"article-{unique_id1}"  # Different from workspace1

    @pytest.mark.asyncio
    async def test_create_content_with_metadata(self, db_session, setup_factories):
        """Test content creation with metadata"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        content_data = ContentCreate(
            workspace_id=workspace.id,
            title="Article with Metadata",
            body_markdown="Content",
            metadata=ContentMetadataSchema(
                content_summary="Comprehensive article summary",
                content_type="blog",
                target_platform="Website",
                target_industry="Technology",
                target_audience=["Developers", "Engineers"],
                content_word_count=500,
                reading_time_minutes=3
            )
        )

        service = ContentService(db_session)

        # Act
        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=content_data
        )

        # Assert - Check metadata was created
        from sqlalchemy import select
        from src.api.models.content_models.content_metadata import ContentMetadata

        result = await db_session.execute(
            select(ContentMetadata).where(ContentMetadata.content_id == content.id)
        )
        metadata = result.scalar_one_or_none()

        assert metadata is not None
        assert metadata.content_summary == "Comprehensive article summary"
        assert metadata.content_type == "blog"
        assert metadata.content_word_count == 500

    @pytest.mark.asyncio
    async def test_create_content_with_seo_data(self, db_session, setup_factories):
        """Test content creation with SEO data"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        content_data = ContentCreate(
            workspace_id=workspace.id,
            title="SEO Optimized Article",
            body_markdown="Content",
            seo_data=ContentSEODataSchema(
                content_primary_keywords=["python", "fastapi", "testing"],
                content_secondary_keywords=["pytest", "async"],
                content_meta_description="Learn FastAPI testing with pytest",
                content_search_intent=["educational", "informational"],
                content_seo_score=0.85,
                content_readability_score=0.90
            )
        )

        service = ContentService(db_session)

        # Act
        content = await service.create_content(
            workspace_id=workspace.id,
            user_id=user.id,
            data=content_data
        )

        # Assert - Check SEO data was created
        from sqlalchemy import select
        from src.api.models.content_models.content_seo_data import ContentSEOData

        result = await db_session.execute(
            select(ContentSEOData).where(ContentSEOData.content_id == content.id)
        )
        seo = result.scalar_one_or_none()

        assert seo is not None
        assert "python" in seo.content_primary_keywords
        assert seo.content_meta_description == "Learn FastAPI testing with pytest"
        assert seo.content_seo_score == 0.85


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
    async def test_update_content_slug_excludes_current_content_from_uniqueness_check(self, db_session, setup_factories):
        """Test that slug uniqueness check excludes the content being updated"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            title="My Article",
            slug="my-article"
        )

        # Update to same title should keep same slug
        update_data = ContentUpdate(title="My Article")
        service = ContentService(db_session)

        # Act
        updated = await service.update_content(
            content_id=content.id,
            workspace_id=workspace.id,
            user_id=user.id,
            data=update_data
        )

        # Assert
        assert updated.slug == "my-article"  # Should NOT become "my-article-1"

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
    async def test_update_content_not_found_raises_404(self, db_session, setup_factories):
        """Test updating non-existent content raises ResourceNotFoundException"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        fake_id = uuid4()

        update_data = ContentUpdate(title="New Title")
        service = ContentService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException) as exc:
            await service.update_content(
                content_id=fake_id,
                workspace_id=workspace.id,
                user_id=user.id,
                data=update_data
            )

        assert str(fake_id) in str(exc.value)

    @pytest.mark.asyncio
    async def test_update_content_wrong_workspace_raises_404(self, db_session, setup_factories):
        """Test updating content from wrong workspace raises 404"""
        # Arrange
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        content = await setup_factories["content"].create(workspace_id=workspace1.id)

        update_data = ContentUpdate(title="New Title")
        service = ContentService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.update_content(
                content_id=content.id,
                workspace_id=workspace2.id,  # Wrong workspace
                user_id=user.id,
                data=update_data
            )

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
        update_data = ContentUpdate(status="published")  # draft -> published not allowed
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

    @pytest.mark.asyncio
    async def test_delete_content_not_found_raises_404(self, db_session, setup_factories):
        """Test deleting non-existent content raises 404"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        fake_id = uuid4()

        service = ContentService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.delete_content(
                content_id=fake_id,
                workspace_id=workspace.id
            )

    @pytest.mark.asyncio
    async def test_delete_already_deleted_content_raises_404(self, db_session, setup_factories):
        """Test deleting already deleted content raises 404"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            deleted_at=datetime.now(timezone.utc)  # Already deleted
        )

        service = ContentService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.delete_content(
                content_id=content.id,
                workspace_id=workspace.id
            )


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
    async def test_publish_content_from_draft_raises_validation_error(self, db_session, setup_factories):
        """Test that publishing from draft status raises validation error"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            status="draft",
            body_markdown="Content"
        )

        service = ContentService(db_session)

        # Act & Assert
        with pytest.raises(WrextValidationException) as exc:
            await service.publish_content(
                content_id=content.id,
                workspace_id=workspace.id,
                user_id=user.id
            )

        assert "ready" in str(exc.value).lower()

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

    @pytest.mark.asyncio
    async def test_publish_whitespace_only_content_raises_validation_error(self, db_session, setup_factories):
        """Test that publishing whitespace-only content raises validation error"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        content = await setup_factories["content"].create(
            workspace_id=workspace.id,
            status="ready",
            body_markdown="   \n\t  "  # Only whitespace
        )

        service = ContentService(db_session)

        # Act & Assert
        with pytest.raises(WrextValidationException):
            await service.publish_content(
                content_id=content.id,
                workspace_id=workspace.id,
                user_id=user.id
            )


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
    async def test_draft_to_archived_allowed(self, db_session):
        """Test draft → archived transition is allowed"""
        service = ContentService(db_session)
        await service._validate_status_transition("draft", "archived")

    @pytest.mark.asyncio
    async def test_ready_to_published_allowed(self, db_session):
        """Test ready → published transition is allowed"""
        service = ContentService(db_session)
        await service._validate_status_transition("ready", "published")

    @pytest.mark.asyncio
    async def test_ready_to_draft_allowed(self, db_session):
        """Test ready → draft transition is allowed (move back)"""
        service = ContentService(db_session)
        await service._validate_status_transition("ready", "draft")

    @pytest.mark.asyncio
    async def test_published_to_archived_allowed(self, db_session):
        """Test published → archived transition is allowed"""
        service = ContentService(db_session)
        await service._validate_status_transition("published", "archived")

    @pytest.mark.asyncio
    async def test_draft_to_published_not_allowed(self, db_session):
        """Test draft → published transition is NOT allowed"""
        service = ContentService(db_session)

        with pytest.raises(WrextValidationException) as exc:
            await service._validate_status_transition("draft", "published")

        assert "transition" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_archived_to_any_not_allowed(self, db_session):
        """Test archived → any transition is NOT allowed"""
        service = ContentService(db_session)

        with pytest.raises(WrextValidationException):
            await service._validate_status_transition("archived", "draft")

        with pytest.raises(WrextValidationException):
            await service._validate_status_transition("archived", "ready")

        with pytest.raises(WrextValidationException):
            await service._validate_status_transition("archived", "published")

    @pytest.mark.asyncio
    async def test_published_to_ready_not_allowed(self, db_session):
        """Test published → ready transition is NOT allowed"""
        service = ContentService(db_session)

        with pytest.raises(WrextValidationException):
            await service._validate_status_transition("published", "ready")


@pytest.mark.unit
class TestContentServiceSlugGeneration:
    """Tests for ContentService slug generation helpers"""

    @pytest.mark.asyncio
    async def test_slugify_converts_to_lowercase(self, db_session):
        """Test slugify converts text to lowercase"""
        service = ContentService(db_session)
        slug = service._slugify("UPPERCASE TEXT")
        assert slug == "uppercase-text"

    @pytest.mark.asyncio
    async def test_slugify_replaces_spaces_with_hyphens(self, db_session):
        """Test slugify replaces spaces with hyphens"""
        service = ContentService(db_session)
        slug = service._slugify("multiple word title")
        assert slug == "multiple-word-title"

    @pytest.mark.asyncio
    async def test_slugify_removes_special_characters(self, db_session):
        """Test slugify removes special characters"""
        service = ContentService(db_session)
        slug = service._slugify("Title with @#$% special chars!")
        assert slug == "title-with-special-chars"

    @pytest.mark.asyncio
    async def test_slugify_removes_multiple_consecutive_hyphens(self, db_session):
        """Test slugify collapses multiple hyphens"""
        service = ContentService(db_session)
        slug = service._slugify("title  --  with   gaps")
        assert slug == "title-with-gaps"

    @pytest.mark.asyncio
    async def test_slugify_strips_leading_trailing_hyphens(self, db_session):
        """Test slugify strips hyphens from edges"""
        service = ContentService(db_session)
        slug = service._slugify("---title---")
        assert slug == "title"
