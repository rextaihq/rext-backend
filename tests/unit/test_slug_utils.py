"""
Unit tests for slug utilities.

Tests slug generation and uniqueness checking logic.
"""

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from src.utils.slug_utils import generate_unique_slug, generate_workspace_slug, slugify


class TestSlugify:
    """Tests for slugify function."""

    def test_slugify_converts_to_lowercase(self):
        """Test that slugify converts text to lowercase."""
        result = slugify("HELLO WORLD")
        assert result == "hello-world"

    def test_slugify_replaces_spaces_with_hyphens(self):
        """Test that spaces are replaced with hyphens."""
        result = slugify("hello world test")
        assert result == "hello-world-test"

    def test_slugify_replaces_underscores_with_hyphens(self):
        """Test that underscores are replaced with hyphens."""
        result = slugify("hello_world_test")
        assert result == "hello-world-test"

    def test_slugify_removes_special_characters(self):
        """Test that special characters are removed."""
        result = slugify("hello! @world# $test%")
        assert result == "hello-world-test"

    def test_slugify_removes_multiple_consecutive_hyphens(self):
        """Test that multiple hyphens are collapsed to single hyphen."""
        result = slugify("hello---world")
        assert result == "hello-world"

    def test_slugify_strips_leading_trailing_hyphens(self):
        """Test that leading and trailing hyphens are removed."""
        result = slugify("-hello-world-")
        assert result == "hello-world"

    def test_slugify_handles_multiple_spaces(self):
        """Test that multiple spaces are collapsed to single hyphen."""
        result = slugify("hello    world")
        assert result == "hello-world"

    def test_slugify_returns_default_for_empty_string(self):
        """Test that empty string returns default 'workspace'."""
        result = slugify("")
        assert result == "workspace"

    def test_slugify_returns_default_for_special_chars_only(self):
        """Test that string with only special chars returns default."""
        result = slugify("!@#$%^&*()")
        assert result == "workspace"

    def test_slugify_handles_mixed_case_with_special_chars(self):
        """Test complex string with mixed case and special characters."""
        result = slugify("My Awesome-Project_2024! (Beta)")
        assert result == "my-awesome-project-2024-beta"

    def test_slugify_handles_unicode_characters(self):
        """Test that unicode characters are removed."""
        result = slugify("hello 世界 world")
        assert result == "hello-world"

    def test_slugify_handles_numbers(self):
        """Test that numbers are preserved."""
        result = slugify("Project 2024 v1.5")
        assert result == "project-2024-v15"


class TestGenerateUniqueSlug:
    """Tests for generate_unique_slug function."""

    def test_generate_unique_slug_returns_base_when_unique(self):
        """Test that base slug is returned when it's unique."""
        # Arrange
        mock_db = MagicMock()
        mock_model = MagicMock()

        # Mock query chain
        mock_query = MagicMock()
        mock_query.first.return_value = None  # No existing slug
        mock_db.query.return_value.filter.return_value = mock_query

        # Act
        result = generate_unique_slug(mock_db, "test-slug", mock_model)

        # Assert
        assert result == "test-slug"
        mock_db.query.assert_called_once_with(mock_model)

    def test_generate_unique_slug_appends_counter_when_exists(self):
        """Test that counter is appended when slug exists."""
        # Arrange
        mock_db = MagicMock()
        mock_model = MagicMock()

        # Mock query chain - first returns existing, second returns None
        mock_query_1 = MagicMock()
        mock_query_1.first.return_value = MagicMock()  # Slug exists

        mock_query_2 = MagicMock()
        mock_query_2.first.return_value = None  # Slug with -1 doesn't exist

        mock_db.query.return_value.filter.side_effect = [mock_query_1, mock_query_2]

        # Act
        result = generate_unique_slug(mock_db, "test-slug", mock_model)

        # Assert
        assert result == "test-slug-1"

    def test_generate_unique_slug_increments_counter_multiple_times(self):
        """Test that counter increments until unique slug found."""
        # Arrange
        mock_db = MagicMock()
        mock_model = MagicMock()

        # Mock query chain - first 3 return existing, 4th returns None
        mock_query_1 = MagicMock()
        mock_query_1.first.return_value = MagicMock()

        mock_query_2 = MagicMock()
        mock_query_2.first.return_value = MagicMock()

        mock_query_3 = MagicMock()
        mock_query_3.first.return_value = MagicMock()

        mock_query_4 = MagicMock()
        mock_query_4.first.return_value = None  # test-slug-3 is unique

        mock_db.query.return_value.filter.side_effect = [
            mock_query_1,
            mock_query_2,
            mock_query_3,
            mock_query_4,
        ]

        # Act
        result = generate_unique_slug(mock_db, "test-slug", mock_model)

        # Assert
        assert result == "test-slug-3"

    def test_generate_unique_slug_excludes_id_when_provided(self):
        """Test that exclude_id filters out the record being updated."""
        # Arrange
        mock_db = MagicMock()
        mock_model = MagicMock()
        exclude_id = uuid4()

        # Mock query chain with filter chaining
        mock_filter_1 = MagicMock()
        mock_filter_2 = MagicMock()
        mock_filter_2.first.return_value = None
        mock_filter_1.filter.return_value = mock_filter_2
        mock_db.query.return_value.filter.return_value = mock_filter_1

        # Act
        result = generate_unique_slug(mock_db, "test-slug", mock_model, exclude_id=exclude_id)

        # Assert
        assert result == "test-slug"
        # Verify filter was called with exclude condition
        mock_filter_1.filter.assert_called_once()

    def test_generate_unique_slug_uses_custom_slug_field(self):
        """Test that custom slug field name is used."""
        # Arrange
        mock_db = MagicMock()
        mock_model = MagicMock()

        mock_query = MagicMock()
        mock_query.first.return_value = None
        mock_db.query.return_value.filter.return_value = mock_query

        # Act
        result = generate_unique_slug(mock_db, "test-slug", mock_model, slug_field="custom_slug")

        # Assert
        assert result == "test-slug"


class TestGenerateWorkspaceSlug:
    """Tests for generate_workspace_slug function."""

    def test_generate_workspace_slug_normal_name(self):
        """Test workspace slug generation for normal name."""
        result = generate_workspace_slug("My Awesome Workspace")
        assert result == "my-awesome-workspace"

    def test_generate_workspace_slug_short_name_gets_prefixed(self):
        """Test that short names (< 3 chars) get prefixed."""
        result = generate_workspace_slug("AB")
        assert result == "workspace-ab"

    def test_generate_workspace_slug_two_char_name(self):
        """Test two character name gets workspace prefix."""
        result = generate_workspace_slug("XY")
        assert result == "workspace-xy"

    def test_generate_workspace_slug_one_char_name(self):
        """Test single character name gets workspace prefix."""
        result = generate_workspace_slug("A")
        assert result == "workspace-a"

    def test_generate_workspace_slug_empty_name(self):
        """Test empty name returns default workspace."""
        result = generate_workspace_slug("")
        assert result == "workspace"

    def test_generate_workspace_slug_special_chars_only(self):
        """Test name with only special characters returns default."""
        result = generate_workspace_slug("!!!")
        assert result == "workspace"

    def test_generate_workspace_slug_preserves_length_for_long_names(self):
        """Test that long names are preserved."""
        result = generate_workspace_slug("Enterprise Business Solutions")
        assert result == "enterprise-business-solutions"

    def test_generate_workspace_slug_exactly_three_chars(self):
        """Test that exactly 3 character slug is not prefixed."""
        result = generate_workspace_slug("ABC")
        assert result == "abc"

    def test_generate_workspace_slug_with_numbers(self):
        """Test workspace slug with numbers."""
        result = generate_workspace_slug("Team 2024")
        assert result == "team-2024"

    def test_generate_workspace_slug_removes_special_characters(self):
        """Test that special characters are removed properly."""
        result = generate_workspace_slug("My-Company! (2024)")
        assert result == "my-company-2024"
