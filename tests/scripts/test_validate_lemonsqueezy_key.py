"""
Tests for LemonSqueezy API Key Validation Script

Tests the validate_lemonsqueezy_key.py script functionality.
"""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add scripts directory to path
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

# Import the validation script functions
from validate_lemonsqueezy_key import (  # noqa: E402 -- intentional: avoids a circular import
    check_key_format,
    validate_api_key,
)


class TestValidateApiKey:
    """Test API key validation against LemonSqueezy API"""

    @pytest.mark.asyncio
    @patch("validate_lemonsqueezy_key.httpx")
    async def test_validate_valid_key(self, mock_httpx):
        """Test validation of a valid API key"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"attributes": {"name": "Test User", "email": "test@example.com"}}
        }
        mock_httpx.get.return_value = mock_response

        # Validate key
        is_valid, message = validate_api_key("valid_key_12345678901234567890")

        # Assertions
        assert is_valid is True
        assert message == "Valid"
        mock_httpx.get.assert_called_once()

    @pytest.mark.asyncio
    @patch("validate_lemonsqueezy_key.httpx")
    async def test_validate_invalid_key_401(self, mock_httpx):
        """Test validation of invalid API key (401 response)"""
        # Mock 401 Unauthorized response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_httpx.get.return_value = mock_response

        # Validate key
        is_valid, message = validate_api_key("invalid_key_123")

        # Assertions
        assert is_valid is False
        assert "401 Unauthorized" in message

    @pytest.mark.asyncio
    @patch("validate_lemonsqueezy_key.httpx")
    async def test_validate_rate_limited_429(self, mock_httpx):
        """Test validation when rate limited (429 response)"""
        # Mock 429 Too Many Requests response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Too Many Requests"
        mock_httpx.get.return_value = mock_response

        # Validate key
        is_valid, message = validate_api_key("some_key_12345678901234567890")

        # Assertions
        assert is_valid is False
        assert "429 Too Many Requests" in message

    @pytest.mark.asyncio
    @patch("validate_lemonsqueezy_key.httpx")
    async def test_validate_unexpected_status_code(self, mock_httpx):
        """Test validation with unexpected HTTP status code"""
        # Mock unexpected response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_httpx.get.return_value = mock_response

        # Validate key
        is_valid, message = validate_api_key("some_key_12345678901234567890")

        # Assertions
        assert is_valid is False
        assert "Unexpected status code" in message

    @pytest.mark.asyncio
    @patch("validate_lemonsqueezy_key.httpx")
    async def test_validate_connection_timeout(self, mock_httpx):
        """Test validation when connection times out"""
        # Mock connection timeout
        from httpx import ConnectTimeout

        mock_httpx.get.side_effect = ConnectTimeout("Connection timeout")

        # Validate key
        is_valid, message = validate_api_key("some_key_12345678901234567890")

        # Assertions
        assert is_valid is False
        assert "Connection timeout" in message

    @pytest.mark.asyncio
    @patch("validate_lemonsqueezy_key.httpx")
    async def test_validate_http_error(self, mock_httpx):
        """Test validation when HTTP error occurs"""
        # Mock HTTP error
        from httpx import HTTPError

        mock_httpx.get.side_effect = HTTPError("HTTP error occurred")

        # Validate key
        is_valid, message = validate_api_key("some_key_12345678901234567890")

        # Assertions
        assert is_valid is False
        assert "HTTP error" in message


class TestCheckKeyFormat:
    """Test API key format validation"""

    def test_valid_key_format(self):
        """Test format check with valid key"""
        # Valid key: 40+ characters, no whitespace
        valid_key = "a" * 50

        format_ok = check_key_format(valid_key)

        assert format_ok is True

    def test_key_too_short(self):
        """Test format check with key that's too short"""
        short_key = "short_key_123"

        format_ok = check_key_format(short_key)

        assert format_ok is False

    def test_key_with_leading_whitespace(self):
        """Test format check with leading whitespace"""
        key_with_space = " " + ("a" * 50)

        format_ok = check_key_format(key_with_space)

        assert format_ok is False

    def test_key_with_trailing_whitespace(self):
        """Test format check with trailing whitespace"""
        key_with_space = ("a" * 50) + " "

        format_ok = check_key_format(key_with_space)

        assert format_ok is False

    def test_key_with_newline(self):
        """Test format check with newline characters"""
        key_with_newline = ("a" * 25) + "\n" + ("a" * 25)

        format_ok = check_key_format(key_with_newline)

        assert format_ok is False

    def test_placeholder_value_your_api_key_here(self):
        """Test format check with placeholder value"""
        placeholder = "your_api_key_here"

        format_ok = check_key_format(placeholder)

        assert format_ok is False

    def test_placeholder_value_replace_me(self):
        """Test format check with REPLACE_ME placeholder"""
        placeholder = "REPLACE_ME"

        format_ok = check_key_format(placeholder)

        assert format_ok is False

    def test_minimum_length_boundary(self):
        """Test format check at minimum length boundary (20 chars)"""
        # Exactly 20 characters (boundary case)
        boundary_key = "a" * 20

        format_ok = check_key_format(boundary_key)

        # Should still pass (>= 20 chars is ok, warning is for < 20)
        assert format_ok is True

    def test_just_below_minimum_length(self):
        """Test format check just below minimum length (19 chars)"""
        short_key = "a" * 19

        format_ok = check_key_format(short_key)

        assert format_ok is False


class TestMainFunction:
    """Test the main validation script entry point"""

    @patch.dict(os.environ, {}, clear=True)
    def test_main_no_api_key_env_var(self):
        """Test main function when LEMONSQUEEZY_API_KEY is not set"""
        from validate_lemonsqueezy_key import main

        # Should exit with code 1 when env var is missing
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch.dict(os.environ, {"LEMONSQUEEZY_API_KEY": "a" * 50})
    @patch("validate_lemonsqueezy_key.validate_api_key")
    def test_main_valid_key(self, mock_validate):
        """Test main function with valid API key"""
        from validate_lemonsqueezy_key import main

        # Mock successful validation
        mock_validate.return_value = (True, "Valid")

        # Should exit with code 0 on success
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0

    @patch.dict(os.environ, {"LEMONSQUEEZY_API_KEY": "invalid_key"})
    @patch("validate_lemonsqueezy_key.validate_api_key")
    def test_main_invalid_key(self, mock_validate):
        """Test main function with invalid API key"""
        from validate_lemonsqueezy_key import main

        # Mock failed validation
        mock_validate.return_value = (False, "Invalid key")

        # Should exit with code 1 on failure
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


class TestIntegrationScenarios:
    """Integration tests for common scenarios"""

    @patch("validate_lemonsqueezy_key.httpx")
    def test_rotation_scenario_new_key_valid(self, mock_httpx):
        """Test scenario: Rotating to a new valid key"""
        # Mock successful validation of new key
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"attributes": {"name": "Production User", "email": "prod@example.com"}}
        }
        mock_httpx.get.return_value = mock_response

        new_key = "new_production_key_12345678901234567890123456789012345"

        # Validate format first
        format_ok = check_key_format(new_key)
        assert format_ok is True

        # Validate with API
        is_valid, message = validate_api_key(new_key)
        assert is_valid is True

    @patch("validate_lemonsqueezy_key.httpx")
    def test_rotation_scenario_accidentally_copied_with_space(self, mock_httpx):
        """Test scenario: Key copied with trailing space (common mistake)"""
        # Key with trailing space (common copy-paste error)
        key_with_space = "new_key_12345678901234567890123456789012345 "

        # Format check should catch this
        format_ok = check_key_format(key_with_space)
        assert format_ok is False

    def test_rotation_scenario_placeholder_not_replaced(self):
        """Test scenario: Forgot to replace placeholder in .env"""
        placeholder = "your_api_key_here"

        # Format check should catch placeholder
        format_ok = check_key_format(placeholder)
        assert format_ok is False

    @patch("validate_lemonsqueezy_key.httpx")
    def test_rotation_scenario_old_key_revoked(self, mock_httpx):
        """Test scenario: Old key already revoked in LemonSqueezy"""
        # Mock 401 response (key revoked)
        mock_response = Mock()
        mock_response.status_code = 401
        mock_httpx.get.return_value = mock_response

        revoked_key = "old_revoked_key_12345678901234567890123456789012"

        # Validation should fail
        is_valid, message = validate_api_key(revoked_key)
        assert is_valid is False
        assert "401" in message
