"""
Unit tests for KnowledgeService.

Tests cover:
- File knowledge operations (upload, validation, duplicate detection)
- Text knowledge operations
- Vector store integration (mocked)
- File cleanup and deletion
"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from io import BytesIO

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile

from src.services.knowledge_service import KnowledgeService
from src.api.models.knowledge_models.knowledge_model import KnowledgeFiles, TextKnowledge
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
    DuplicateResourceException,
    RextExternalServiceException
)


# ========================================================================
# Test Class: KnowledgeService Add File Knowledge
# ========================================================================

@pytest.mark.asyncio
class TestKnowledgeServiceAddFileKnowledge:
    """Test suite for add_file_knowledge() method"""

    async def test_add_file_knowledge_success(self, db_session, setup_factories):
        """Test successfully adding file knowledge"""
        # Arrange
        workspace = await setup_factories["workspace"].create()

        # Create mock file
        file_content = b"Test PDF content"
        file = UploadFile(
            filename="test.pdf",
            file=BytesIO(file_content)
        )

        service = KnowledgeService(db_session)

        # Mock external dependencies
        with patch('src.services.knowledge_service.validate_and_store_file') as mock_validate, \
             patch('src.services.knowledge_service.load_split_file_data') as mock_load, \
             patch('src.services.knowledge_service.add_to_vector_store') as mock_vector:

            mock_validate.return_value = {
                "safe_filename": "test.pdf",
                "secure_path": "/uploads/test123.pdf",
                "hash": "abc123hash",
                "mime_type": "application/pdf",
                "size": len(file_content)
            }
            mock_load.return_value = ["chunk1", "chunk2", "chunk3"]
            mock_vector.return_value = True

            # Act
            result = await service.add_file_knowledge(
                workspace_id=workspace.id,
                file=file,
                allowed_types=["application/pdf"],
                max_size_mb=10
            )

        # Assert
        assert result.workspace_id == workspace.id
        assert result.file_name == "test.pdf"
        assert result.file_hash == "abc123hash"
        assert result.chunk_count == 3
        mock_validate.assert_called_once()
        mock_load.assert_called_once_with("/uploads/test123.pdf")
        mock_vector.assert_called_once()

    async def test_add_file_knowledge_duplicate_detected(self, db_session, setup_factories):
        """Test that duplicate file is rejected"""
        # Arrange
        workspace = await setup_factories["workspace"].create()

        # Create existing file knowledge with same hash
        existing_hash = "duplicate_hash_123"
        existing = await setup_factories["knowledge_files"].create(
            workspace_id=workspace.id,
            file_name="existing.pdf",
            file_hash=existing_hash,
            file_type="application/pdf",
            file_size=1000,
            file_path="/uploads/existing.pdf",
            mime_type="application/pdf",
            chunk_count=5
        )

        # Create mock file with same hash
        file = UploadFile(filename="duplicate.pdf", file=BytesIO(b"content"))
        service = KnowledgeService(db_session)

        # Mock external dependencies
        with patch('src.services.knowledge_service.validate_and_store_file') as mock_validate, \
             patch('src.services.knowledge_service.delete_file') as mock_delete:

            mock_validate.return_value = {
                "safe_filename": "duplicate.pdf",
                "secure_path": "/uploads/duplicate123.pdf",
                "hash": existing_hash,  # Same hash as existing
                "mime_type": "application/pdf",
                "size": 1000
            }

            # Act & Assert
            with pytest.raises(DuplicateResourceException):
                await service.add_file_knowledge(
                    workspace_id=workspace.id,
                    file=file,
                    allowed_types=["application/pdf"]
                )

            # Verify duplicate file was deleted
            mock_delete.assert_called_once_with("/uploads/duplicate123.pdf")

    async def test_add_file_knowledge_no_content_extracted(self, db_session, setup_factories):
        """Test failure when no content can be extracted from file"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        file = UploadFile(filename="empty.pdf", file=BytesIO(b""))
        service = KnowledgeService(db_session)

        # Mock external dependencies
        with patch('src.services.knowledge_service.validate_and_store_file') as mock_validate, \
             patch('src.services.knowledge_service.load_split_file_data') as mock_load:

            mock_validate.return_value = {
                "safe_filename": "empty.pdf",
                "secure_path": "/uploads/empty.pdf",
                "hash": "emptyhash",
                "mime_type": "application/pdf",
                "size": 0
            }
            mock_load.return_value = []  # No chunks extracted

            # Act & Assert
            with pytest.raises(RextValidationException) as exc_info:
                await service.add_file_knowledge(
                    workspace_id=workspace.id,
                    file=file,
                    allowed_types=["application/pdf"]
                )

            assert "Failed to extract content" in str(exc_info.value.message)

    async def test_add_file_knowledge_vector_store_failure(self, db_session, setup_factories):
        """Test handling of vector store insertion failure"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        file = UploadFile(filename="test.pdf", file=BytesIO(b"content"))
        service = KnowledgeService(db_session)

        # Mock external dependencies
        with patch('src.services.knowledge_service.validate_and_store_file') as mock_validate, \
             patch('src.services.knowledge_service.load_split_file_data') as mock_load, \
             patch('src.services.knowledge_service.add_to_vector_store') as mock_vector:

            mock_validate.return_value = {
                "safe_filename": "test.pdf",
                "secure_path": "/uploads/test.pdf",
                "hash": "hash123",
                "mime_type": "application/pdf",
                "size": 1000
            }
            mock_load.return_value = ["chunk1", "chunk2"]
            mock_vector.return_value = False  # Vector store returns False

            # Act & Assert
            with pytest.raises(RextExternalServiceException) as exc_info:
                await service.add_file_knowledge(
                    workspace_id=workspace.id,
                    file=file,
                    allowed_types=["application/pdf"]
                )

            assert "vector store" in str(exc_info.value.message).lower()


# ========================================================================
# Test Class: KnowledgeService Delete File Knowledge
# ========================================================================

@pytest.mark.asyncio
class TestKnowledgeServiceDeleteFileKnowledge:
    """Test suite for delete_file_knowledge() method"""

    async def test_delete_file_knowledge_success(self, db_session, setup_factories):
        """Test successfully deleting file knowledge"""
        # Arrange
        workspace = await setup_factories["workspace"].create()

        # Create file knowledge using factory
        knowledge = await setup_factories["knowledge_files"].create(
            workspace_id=workspace.id,
            file_name="test.pdf",
            file_hash="hash123",
            file_type="application/pdf",
            file_size=1000,
            file_path="/uploads/test.pdf",
            mime_type="application/pdf",
            chunk_count=5
        )

        service = KnowledgeService(db_session)

        # Mock external dependencies
        with patch('src.services.knowledge_service.delete_vectors') as mock_del_vectors, \
             patch('src.services.knowledge_service.delete_file') as mock_del_file:

            mock_del_vectors.return_value = True

            # Act
            await service.delete_file_knowledge(
                file_id=knowledge.id,
                workspace_id=workspace.id
            )

        # Assert
        mock_del_vectors.assert_called_once()
        mock_del_file.assert_called_once_with("/uploads/test.pdf")

    async def test_delete_file_knowledge_not_found(self, db_session, setup_factories):
        """Test deleting non-existent file knowledge raises 404"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        non_existent_id = uuid4()
        service = KnowledgeService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.delete_file_knowledge(
                file_id=non_existent_id,
                workspace_id=workspace.id
            )

    async def test_delete_file_knowledge_wrong_workspace(self, db_session, setup_factories):
        """Test deleting file from different workspace raises 404"""
        # Arrange
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()

        knowledge = await setup_factories["knowledge_files"].create(
            workspace_id=workspace1.id,
            file_name="test.pdf",
            file_hash="hash123",
            file_type="application/pdf",
            file_size=1000,
            file_path="/uploads/test.pdf",
            mime_type="application/pdf",
            chunk_count=5
        )

        service = KnowledgeService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.delete_file_knowledge(
                file_id=knowledge.id,
                workspace_id=workspace2.id  # Wrong workspace
            )


# ========================================================================
# Test Class: KnowledgeService Add Text Knowledge
# ========================================================================

@pytest.mark.asyncio
class TestKnowledgeServiceAddTextKnowledge:
    """Test suite for add_text_knowledge() method"""

    async def test_add_text_knowledge_success(self, db_session, setup_factories):
        """Test successfully adding text knowledge"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        title = "Important Notes"
        content = "This is important information about our product."

        service = KnowledgeService(db_session)

        # Mock vector store
        with patch('src.services.knowledge_service.add_to_vector_store') as mock_vector:
            mock_vector.return_value = True

            # Act
            result = await service.add_text_knowledge(
                workspace_id=workspace.id,
                title=title,
                content=content
            )

        # Assert
        assert result.workspace_id == workspace.id
        assert result.title == title
        assert result.content == content
        assert result.title == title
        mock_vector.assert_called_once()


# ========================================================================
# Test Class: KnowledgeService Delete Text Knowledge
# ========================================================================

@pytest.mark.asyncio
class TestKnowledgeServiceDeleteTextKnowledge:
    """Test suite for delete_text_knowledge() method"""

    async def test_delete_text_knowledge_success(self, db_session, setup_factories):
        """Test successfully deleting text knowledge"""
        # Arrange
        workspace = await setup_factories["workspace"].create()

        knowledge = TextKnowledge(
            workspace_id=workspace.id,
            title="Test Knowledge",
            content="Test content",
            # No chunk_count field
        )
        db_session.add(knowledge)
        await db_session.flush()
        await db_session.refresh(knowledge)

        service = KnowledgeService(db_session)

        # Mock vector store
        with patch('src.services.knowledge_service.delete_vectors') as mock_del_vectors:
            mock_del_vectors.return_value = True

            # Act
            await service.delete_text_knowledge(
                knowledge_id=knowledge.id,
                workspace_id=workspace.id
            )

        # Assert
        mock_del_vectors.assert_called_once()

    async def test_delete_text_knowledge_not_found(self, db_session, setup_factories):
        """Test deleting non-existent text knowledge raises 404"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        non_existent_id = uuid4()
        service = KnowledgeService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.delete_text_knowledge(
                knowledge_id=non_existent_id,
                workspace_id=workspace.id
            )

    async def test_delete_text_knowledge_wrong_workspace(self, db_session, setup_factories):
        """Test deleting text from different workspace raises 404"""
        # Arrange
        workspace1 = await setup_factories["workspace"].create()
        workspace2 = await setup_factories["workspace"].create()

        knowledge = TextKnowledge(
            workspace_id=workspace1.id,
            title="Test Knowledge",
            content="Test content",
            # No chunk_count field
        )
        db_session.add(knowledge)
        await db_session.flush()
        await db_session.refresh(knowledge)

        service = KnowledgeService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.delete_text_knowledge(
                knowledge_id=knowledge.id,
                workspace_id=workspace2.id  # Wrong workspace
            )
