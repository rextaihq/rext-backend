"""
Unit tests for TopicService.

Tests cover:
- Topic creation with enrichment
- Batch operations
- Topic updates
- Topic deletion
- Topic approval workflow
- Topic retrieval with filtering
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.topic_service import TopicService
 as Topics
from src.api.schema.topic_schema import UpdateTopicRequest
from src.states.schemas import (
    SaveTopicRequest,
    BasicTopicScore,
    TopicGeneration,
    TopicScore,
    SuggestedDefaults,
    GoalAlignment,
    ContentGuidance,
    ContentHooks,
    SEOOpportunities,
    AudienceInsights,
    InternalResearchConfig,
    UserSettings
)
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException
)


# ========================================================================
# Test Class: TopicService Create Topics
# ========================================================================

@pytest.mark.asyncio
class TestTopicServiceCreateTopics:
    """Test suite for create_topics() method"""

    async def test_create_single_topic_with_enrichment(self, db_session, setup_factories):
        """Test creating a single topic with enrichment"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        topic_id = str(uuid4())
        topic_data = SaveTopicRequest(
            id=topic_id,
            workspace_id=str(workspace.id),
            title="How to Build a RESTful API",
            angle="Beginner-friendly guide with practical examples",
            description="Complete guide to building RESTful APIs from scratch",
            channel_fit=["Website", "Blog"],
            audience_fit=["Developers", "Students"],
            why_it_works="High search volume and evergreen content",
            tags=["api", "development", "tutorial"],
            scores=BasicTopicScore(
                relevance=0.9,
                seo_potential=0.85,
                trend_level=0.7,
                uniqueness=0.8,
                reader_interest=0.85,
                actionable_potential=0.95,
                brand_alignment=0.9,
                controversy=0.1
            ),
            suggested_defaults={"platform": "Website"},
            input_params={"industry": "Technology", "purpose": ["Educate"]}
        )

        service = TopicService(db_session)

        # Act
        with patch.object(service.enrichment_service, 'enrich_topic') as mock_enrich:
            # Mock enriched topic response
            mock_enriched = self._create_mock_enriched_topic(topic_id, topic_data)
            mock_enrich.return_value = mock_enriched

            topics = await service.create_topics(
                workspace_id=workspace.id,
                user_id=user.id,
                topics_data=[topic_data]
            )

        # Assert
        assert len(topics) == 1
        topic = topics[0]
        assert topic.id == UUID(topic_id)
        assert topic.workspace_id == workspace.id
        assert topic.title == topic_data.title
        assert topic.angle == topic_data.angle
        assert topic.approved is False
        assert topic.approved_at is None
        mock_enrich.assert_called_once()

    async def test_create_multiple_topics_batch(self, db_session, setup_factories):
        """Test batch creation of multiple topics"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        topics_data = []
        for i in range(3):
            topic_data = SaveTopicRequest(
                id=str(uuid4()),
                workspace_id=str(workspace.id),
                title=f"Topic {i+1}",
                angle=f"Angle {i+1}",
                description=f"Description {i+1}",
                channel_fit=["Website"],
                audience_fit=["Businesses"],
                why_it_works=f"Reason {i+1}",
                tags=[f"tag{i+1}"],
                scores=BasicTopicScore(
                    relevance=0.8,
                    seo_potential=0.8,
                    trend_level=0.7,
                    uniqueness=0.8,
                    reader_interest=0.8,
                    actionable_potential=0.8,
                    brand_alignment=0.8,
                    controversy=0.2
                ),
                suggested_defaults={},
                input_params={}
            )
            topics_data.append(topic_data)

        service = TopicService(db_session)

        # Act
        with patch.object(service.enrichment_service, 'enrich_topic') as mock_enrich:
            # Mock enriched topic for each call
            mock_enrich.side_effect = [
                self._create_mock_enriched_topic(td.id, td) for td in topics_data
            ]

            topics = await service.create_topics(
                workspace_id=workspace.id,
                user_id=user.id,
                topics_data=topics_data
            )

        # Assert
        assert len(topics) == 3
        assert mock_enrich.call_count == 3
        for i, topic in enumerate(topics):
            assert topic.title == f"Topic {i+1}"
            assert topic.approved is False

    async def test_create_topics_continues_on_individual_failure(self, db_session, setup_factories):
        """Test that batch creation continues when individual topics fail"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        topic_data_1 = self._create_save_topic_request("Topic 1", str(workspace.id))
        topic_data_2 = self._create_save_topic_request("Topic 2", str(workspace.id))
        topic_data_3 = self._create_save_topic_request("Topic 3", str(workspace.id))

        service = TopicService(db_session)

        # Act
        with patch.object(service.enrichment_service, 'enrich_topic') as mock_enrich:
            # First succeeds, second fails, third succeeds
            mock_enrich.side_effect = [
                self._create_mock_enriched_topic(topic_data_1.id, topic_data_1),
                Exception("Enrichment failed"),
                self._create_mock_enriched_topic(topic_data_3.id, topic_data_3)
            ]

            topics = await service.create_topics(
                workspace_id=workspace.id,
                user_id=user.id,
                topics_data=[topic_data_1, topic_data_2, topic_data_3]
            )

        # Assert - only 2 topics saved (1st and 3rd)
        assert len(topics) == 2
        assert topics[0].title == "Topic 1"
        assert topics[1].title == "Topic 3"

    async def test_create_topics_raises_when_all_fail(self, db_session, setup_factories):
        """Test that exception is raised when all topics fail to save"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()

        topic_data = self._create_save_topic_request("Topic 1", str(workspace.id))

        service = TopicService(db_session)

        # Act & Assert
        with patch.object(service.enrichment_service, 'enrich_topic') as mock_enrich:
            mock_enrich.side_effect = Exception("Enrichment failed")

            with pytest.raises(RextValidationException) as exc_info:
                await service.create_topics(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    topics_data=[topic_data]
                )

            assert "No topics could be saved successfully" in str(exc_info.value.message)

    async def test_create_topics_defaults_to_unapproved(self, db_session, setup_factories):
        """Test that created topics default to approved=False"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        topic_data = self._create_save_topic_request("Topic 1", str(workspace.id))

        service = TopicService(db_session)

        # Act
        with patch.object(service.enrichment_service, 'enrich_topic') as mock_enrich:
            mock_enrich.return_value = self._create_mock_enriched_topic(topic_data.id, topic_data)
            topics = await service.create_topics(
                workspace_id=workspace.id,
                user_id=user.id,
                topics_data=[topic_data]
            )

        # Assert
        assert topics[0].approved is False
        assert topics[0].approved_at is None

    async def test_create_topics_uses_provided_uuid(self, db_session, setup_factories):
        """Test that provided UUID from frontend is preserved"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        specific_uuid = str(uuid4())
        topic_data = self._create_save_topic_request("Topic 1", str(workspace.id), topic_id=specific_uuid)

        service = TopicService(db_session)

        # Act
        with patch.object(service.enrichment_service, 'enrich_topic') as mock_enrich:
            mock_enrich.return_value = self._create_mock_enriched_topic(specific_uuid, topic_data)
            topics = await service.create_topics(
                workspace_id=workspace.id,
                user_id=user.id,
                topics_data=[topic_data]
            )

        # Assert
        assert str(topics[0].id) == specific_uuid


# ========================================================================
# Test Class: TopicService Update Topics
# ========================================================================

@pytest.mark.asyncio
class TestTopicServiceUpdateTopic:
    """Test suite for update_topic() method"""

    async def test_update_topic_title(self, db_session, setup_factories):
        """Test updating topic title"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace.id)
        original_title = topic.title

        update_data = UpdateTopicRequest(
            topic_id=str(topic.id),
            title="Updated Title"
        )

        service = TopicService(db_session)

        # Act
        updated_topic = await service.update_topic(
            topic_id=topic.id,
            workspace_id=workspace.id,
            data=update_data
        )

        # Assert
        assert updated_topic.title == "Updated Title"
        assert updated_topic.title != original_title
        assert updated_topic.id == topic.id

    async def test_update_topic_multiple_fields(self, db_session, setup_factories):
        """Test updating multiple fields at once"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace.id)

        update_data = UpdateTopicRequest(
            topic_id=str(topic.id),
            title="New Title",
            angle="New Angle",
            description="New Description",
            tags=["new", "tags"]
        )

        service = TopicService(db_session)

        # Act
        updated_topic = await service.update_topic(
            topic_id=topic.id,
            workspace_id=workspace.id,
            data=update_data
        )

        # Assert
        assert updated_topic.title == "New Title"
        assert updated_topic.angle == "New Angle"
        assert updated_topic.description == "New Description"
        assert updated_topic.tags == ["new", "tags"]

    async def test_update_topic_partial_update(self, db_session, setup_factories):
        """Test partial update - only provided fields are updated"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(
            workspace_id=workspace.id,
            title="Original Title",
            angle="Original Angle"
        )

        update_data = UpdateTopicRequest(
            topic_id=str(topic.id),
            title="Updated Title"
            # angle not provided - should remain unchanged
        )

        service = TopicService(db_session)

        # Act
        updated_topic = await service.update_topic(
            topic_id=topic.id,
            workspace_id=workspace.id,
            data=update_data
        )

        # Assert
        assert updated_topic.title == "Updated Title"
        assert updated_topic.angle == "Original Angle"  # Unchanged

    async def test_update_topic_sets_approved_timestamp(self, db_session, setup_factories):
        """Test that setting approved=True sets approved_at timestamp"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(
            workspace_id=workspace.id,
            approved=False,
            approved_at=None
        )

        update_data = UpdateTopicRequest(
            topic_id=str(topic.id),
            approved=True
        )

        service = TopicService(db_session)
        before_update = datetime.now(timezone.utc)

        # Act
        updated_topic = await service.update_topic(
            topic_id=topic.id,
            workspace_id=workspace.id,
            data=update_data
        )

        after_update = datetime.now(timezone.utc)

        # Assert
        assert updated_topic.approved is True
        assert updated_topic.approved_at is not None
        assert before_update <= updated_topic.approved_at <= after_update

    async def test_update_topic_not_found(self, db_session, setup_factories):
        """Test updating non-existent topic raises 404"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        non_existent_id = uuid4()

        update_data = UpdateTopicRequest(
            topic_id=str(non_existent_id),
            title="New Title"
        )

        service = TopicService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException) as exc_info:
            await service.update_topic(
                topic_id=non_existent_id,
                workspace_id=workspace.id,
                data=update_data
            )

        assert "Topic" in str(exc_info.value.message)

    async def test_update_topic_wrong_workspace(self, db_session, setup_factories):
        """Test updating topic from different workspace raises 404"""
        # Arrange
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace1.id)

        update_data = UpdateTopicRequest(
            topic_id=str(topic.id),
            title="New Title"
        )

        service = TopicService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.update_topic(
                topic_id=topic.id,
                workspace_id=workspace2.id,  # Wrong workspace
                data=update_data
            )

    async def test_update_topic_updates_timestamp(self, db_session, setup_factories):
        """Test that updating topic updates updated_at timestamp"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace.id)
        original_updated_at = topic.updated_at

        update_data = UpdateTopicRequest(
            topic_id=str(topic.id),
            title="New Title"
        )

        service = TopicService(db_session)

        # Act
        updated_topic = await service.update_topic(
            topic_id=topic.id,
            workspace_id=workspace.id,
            data=update_data
        )

        # Assert
        assert updated_topic.updated_at > original_updated_at


# ========================================================================
# Test Class: TopicService Delete Topics
# ========================================================================

@pytest.mark.asyncio
class TestTopicServiceDeleteTopics:
    """Test suite for delete_topics() method"""

    async def test_delete_single_topic(self, db_session, setup_factories):
        """Test deleting a single topic"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace.id)

        service = TopicService(db_session)

        # Act
        result = await service.delete_topics(
            topic_ids=[topic.id],
            workspace_id=workspace.id
        )

        # Assert
        assert result["deleted_count"] == 1
        assert topic.id in result["deleted_ids"]
        assert result["missing_ids"] is None

    async def test_delete_multiple_topics(self, db_session, setup_factories):
        """Test batch deletion of multiple topics"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        topics = await setup_factories["topic"].create_batch(
            size=3,
            workspace_id=workspace.id
        )
        topic_ids = [t.id for t in topics]

        service = TopicService(db_session)

        # Act
        result = await service.delete_topics(
            topic_ids=topic_ids,
            workspace_id=workspace.id
        )

        # Assert
        assert result["deleted_count"] == 3
        assert len(result["deleted_ids"]) == 3
        for topic_id in topic_ids:
            assert topic_id in result["deleted_ids"]

    async def test_delete_topics_with_missing_ids(self, db_session, setup_factories):
        """Test deletion when some IDs don't exist"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        existing_topic = await setup_factories["topic"].create(workspace_id=workspace.id)
        non_existent_id = uuid4()

        service = TopicService(db_session)

        # Act
        result = await service.delete_topics(
            topic_ids=[existing_topic.id, non_existent_id],
            workspace_id=workspace.id
        )

        # Assert
        assert result["deleted_count"] == 1
        assert existing_topic.id in result["deleted_ids"]
        assert non_existent_id in result["missing_ids"]
        assert len(result["missing_ids"]) == 1

    async def test_delete_topics_all_missing_raises_404(self, db_session, setup_factories):
        """Test that deleting only non-existent IDs raises 404"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        non_existent_ids = [uuid4(), uuid4()]

        service = TopicService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException) as exc_info:
            await service.delete_topics(
                topic_ids=non_existent_ids,
                workspace_id=workspace.id
            )

        assert "No topics found" in str(exc_info.value.message)

    async def test_delete_topics_wrong_workspace_raises_404(self, db_session, setup_factories):
        """Test that deleting topics from different workspace raises 404"""
        # Arrange
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace1.id)

        service = TopicService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.delete_topics(
                topic_ids=[topic.id],
                workspace_id=workspace2.id  # Wrong workspace
            )

    async def test_delete_topics_workspace_scoping(self, db_session, setup_factories):
        """Test that deletion is properly scoped to workspace"""
        # Arrange
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        topic1 = await setup_factories["topic"].create(workspace_id=workspace1.id)
        topic2 = await setup_factories["topic"].create(workspace_id=workspace2.id)

        service = TopicService(db_session)

        # Act - try to delete both topics using workspace1
        result = await service.delete_topics(
            topic_ids=[topic1.id, topic2.id],
            workspace_id=workspace1.id
        )

        # Assert - only topic1 should be deleted
        assert result["deleted_count"] == 1
        assert topic1.id in result["deleted_ids"]
        assert topic2.id in result["missing_ids"]


# ========================================================================
# Test Class: TopicService Approve Topic
# ========================================================================

@pytest.mark.asyncio
class TestTopicServiceApproveTopic:
    """Test suite for approve_topic() method"""

    async def test_approve_topic_sets_approved_true(self, db_session, setup_factories):
        """Test that approving topic sets approved=True"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        topic = await setup_factories["topic"].create(
            workspace_id=workspace.id,
            approved=False
        )

        service = TopicService(db_session)

        # Act
        approved_topic = await service.approve_topic(
            topic_id=topic.id,
            workspace_id=workspace.id,
            user_id=user.id
        )

        # Assert
        assert approved_topic.approved is True

    async def test_approve_topic_sets_approved_at_timestamp(self, db_session, setup_factories):
        """Test that approving topic sets approved_at timestamp"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        topic = await setup_factories["topic"].create(
            workspace_id=workspace.id,
            approved=False,
            approved_at=None
        )

        service = TopicService(db_session)
        before_approval = datetime.now(timezone.utc)

        # Act
        approved_topic = await service.approve_topic(
            topic_id=topic.id,
            workspace_id=workspace.id,
            user_id=user.id
        )

        after_approval = datetime.now(timezone.utc)

        # Assert
        assert approved_topic.approved_at is not None
        assert before_approval <= approved_topic.approved_at <= after_approval

    async def test_approve_topic_updates_timestamp(self, db_session, setup_factories):
        """Test that approving topic updates updated_at timestamp"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace.id)
        original_updated_at = topic.updated_at

        service = TopicService(db_session)

        # Act
        approved_topic = await service.approve_topic(
            topic_id=topic.id,
            workspace_id=workspace.id,
            user_id=user.id
        )

        # Assert
        assert approved_topic.updated_at > original_updated_at

    async def test_approve_topic_not_found_raises_404(self, db_session, setup_factories):
        """Test approving non-existent topic raises 404"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        non_existent_id = uuid4()

        service = TopicService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.approve_topic(
                topic_id=non_existent_id,
                workspace_id=workspace.id,
                user_id=user.id
            )

    async def test_approve_already_approved_topic(self, db_session, setup_factories):
        """Test approving already approved topic (idempotent)"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        user = await setup_factories["user"].create()
        original_approved_at = datetime.now(timezone.utc)
        topic = await setup_factories["topic"].create(
            workspace_id=workspace.id,
            approved=True,
            approved_at=original_approved_at
        )

        service = TopicService(db_session)

        # Act
        approved_topic = await service.approve_topic(
            topic_id=topic.id,
            workspace_id=workspace.id,
            user_id=user.id
        )

        # Assert
        assert approved_topic.approved is True
        assert approved_topic.approved_at > original_approved_at  # Updated


# ========================================================================
# Test Class: TopicService Get Topics
# ========================================================================

@pytest.mark.asyncio
class TestTopicServiceGetTopics:
    """Test suite for get_topics() method"""

    async def test_get_all_topics_in_workspace(self, db_session, setup_factories):
        """Test retrieving all topics in a workspace"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        topics = await setup_factories["topic"].create_batch(
            size=3,
            workspace_id=workspace.id
        )

        service = TopicService(db_session)

        # Act
        retrieved_topics = await service.get_topics(workspace_id=workspace.id)

        # Assert
        assert len(retrieved_topics) == 3

    async def test_get_topics_approved_only(self, db_session, setup_factories):
        """Test retrieving only approved topics"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        approved_topic = await setup_factories["topic"].create(
            workspace_id=workspace.id,
            approved=True
        )
        unapproved_topic = await setup_factories["topic"].create(
            workspace_id=workspace.id,
            approved=False
        )

        service = TopicService(db_session)

        # Act
        retrieved_topics = await service.get_topics(
            workspace_id=workspace.id,
            approved_only=True
        )

        # Assert
        assert len(retrieved_topics) == 1
        assert retrieved_topics[0].id == approved_topic.id

    async def test_get_topics_workspace_scoping(self, db_session, setup_factories):
        """Test that topics are scoped to workspace"""
        # Arrange
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        topic1 = await setup_factories["topic"].create(workspace_id=workspace1.id)
        topic2 = await setup_factories["topic"].create(workspace_id=workspace2.id)

        service = TopicService(db_session)

        # Act
        workspace1_topics = await service.get_topics(workspace_id=workspace1.id)

        # Assert
        assert len(workspace1_topics) == 1
        assert workspace1_topics[0].id == topic1.id

    async def test_get_topics_empty_workspace(self, db_session, setup_factories):
        """Test retrieving topics from workspace with no topics"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        service = TopicService(db_session)

        # Act
        retrieved_topics = await service.get_topics(workspace_id=workspace.id)

        # Assert
        assert len(retrieved_topics) == 0

    async def test_get_topics_ordered_by_updated_at_desc(self, db_session, setup_factories):
        """Test that topics are ordered by updated_at descending"""
        # Arrange
        workspace = await setup_factories["workspace"].create()

        # Create topics with different updated_at timestamps
        from datetime import timedelta
        now = datetime.now(timezone.utc)

        topic1 = await setup_factories["topic"].create(workspace_id=workspace.id)
        topic1.updated_at = now - timedelta(days=2)

        topic2 = await setup_factories["topic"].create(workspace_id=workspace.id)
        topic2.updated_at = now - timedelta(days=1)

        topic3 = await setup_factories["topic"].create(workspace_id=workspace.id)
        topic3.updated_at = now

        await db_session.flush()

        service = TopicService(db_session)

        # Act
        retrieved_topics = await service.get_topics(workspace_id=workspace.id)

        # Assert
        assert len(retrieved_topics) == 3
        assert retrieved_topics[0].id == topic3.id  # Most recent
        assert retrieved_topics[1].id == topic2.id
        assert retrieved_topics[2].id == topic1.id  # Oldest


# ========================================================================
# Test Class: TopicService Get Single Topic
# ========================================================================

@pytest.mark.asyncio
class TestTopicServiceGetTopic:
    """Test suite for get_topic() method"""

    async def test_get_topic_by_id(self, db_session, setup_factories):
        """Test retrieving a single topic by ID"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace.id)

        service = TopicService(db_session)

        # Act
        retrieved_topic = await service.get_topic(
            topic_id=topic.id,
            workspace_id=workspace.id
        )

        # Assert
        assert retrieved_topic.id == topic.id
        assert retrieved_topic.title == topic.title

    async def test_get_topic_not_found_raises_404(self, db_session, setup_factories):
        """Test getting non-existent topic raises 404"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        non_existent_id = uuid4()

        service = TopicService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.get_topic(
                topic_id=non_existent_id,
                workspace_id=workspace.id
            )

    async def test_get_topic_wrong_workspace_raises_404(self, db_session, setup_factories):
        """Test getting topic from different workspace raises 404"""
        # Arrange
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()
        topic = await setup_factories["topic"].create(workspace_id=workspace1.id)

        service = TopicService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.get_topic(
                topic_id=topic.id,
                workspace_id=workspace2.id  # Wrong workspace
            )


# ========================================================================
# Helper Methods
# ========================================================================

@pytest.mark.asyncio
class TestTopicServiceCreateTopics:  # Add helper methods to first test class

    def _create_save_topic_request(self, title: str, workspace_id: str, topic_id: str = None) -> SaveTopicRequest:
        """Helper to create SaveTopicRequest"""
        return SaveTopicRequest(
            id=topic_id or str(uuid4()),
            workspace_id=workspace_id,
            title=title,
            angle="Test angle",
            description="Test description",
            channel_fit=["Website"],
            audience_fit=["Businesses"],
            why_it_works="Test reason",
            tags=["test"],
            scores=BasicTopicScore(
                relevance=0.8,
                seo_potential=0.8,
                trend_level=0.7,
                uniqueness=0.8,
                reader_interest=0.8,
                actionable_potential=0.8,
                brand_alignment=0.8,
                controversy=0.2
            ),
            suggested_defaults={},
            input_params={}
        )

    def _create_mock_enriched_topic(self, topic_id: str, save_request: SaveTopicRequest) -> TopicGeneration:
        """Helper to create mock enriched topic"""
        return TopicGeneration(
            id=topic_id,
            title=save_request.title,
            angle=save_request.angle,
            description=save_request.description,
            channel_fit=save_request.channel_fit,
            audience_fit=save_request.audience_fit,
            why_it_works=save_request.why_it_works,
            tags=save_request.tags,
            scores=TopicScore(
                relevance=0.8,
                seo_potential=0.8,
                trend_level=0.7,
                uniqueness=0.8,
                reader_interest=0.8,
                actionable_potential=0.8,
                brand_alignment=0.8,
                controversy=0.2
            ),
            suggested_defaults=SuggestedDefaults(
                platform="Website",
                industry="Technology",
                audienceType=["Businesses"],
                readingLevel=["Intermediate"],
                goals=["Educate"],
                tone=["Professional"],
                region="Global",
                contentLength="Medium",
                primaryKeywords=["test"],
                secondaryKeywords=["test2"],
                includeTOC=True,
                includeSummary=True,
                includeKeyTakeaways=True,
                includeCTABlock=True,
                contentStyle="Article"
            ),
            goal_alignment=GoalAlignment(
                primary_goals=["Educate"],
                secondary_goals=["Drive SEO"],
                goal_difficulty={"Educate": "easy"}
            ),
            content_guidance=ContentGuidance(
                recommended_structure="How-to",
                research_complexity="Medium",
                estimated_sections=["Introduction", "Body", "Conclusion"],
                content_hooks=ContentHooks(
                    opening_angles=["Hook 1"],
                    key_questions=["Question 1"],
                    pain_points=["Pain 1"]
                ),
                seo_opportunities=SEOOpportunities(
                    featured_snippet_potential="High",
                    long_tail_keywords=["keyword1"],
                    search_volume_estimate="Medium"
                )
            ),
            audience_insights=AudienceInsights(),
            internal_research_config=InternalResearchConfig(
                enableSimilarArticles=True,
                maxSimilarArticles=5,
                researchDepth="medium",
                includeCompetitorAnalysis=True,
                searchQuerySeeds=["query1"],
                dateRange="past_year",
                sourcesAllowed=["web"],
                includeNews=True,
                retrievalK=10
            ),
            user_settings=UserSettings(
                research_level="medium",
                include_latest_info=True,
                include_examples=True,
                fact_checking="standard",
                content_freshness="recent",
                include_statistics=True,
                include_quotes=True,
                competitor_analysis=True
            )
        )
