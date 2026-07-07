"""
Unit tests for URL normalization utility.

Tests URL normalization logic for consistent matching between
Google Analytics data and published article URLs.
"""

import pytest

from src.utils.url_normalizer import normalize_url


class TestNormalizeUrl:
    """Tests for normalize_url function."""

    def test_normalize_url_converts_to_lowercase(self):
        """Test that URL components are converted to lowercase."""
        result = normalize_url("https://Example.COM/Blog/Article")
        assert result == "https://example.com/blog/article"

    def test_normalize_url_removes_trailing_slash(self):
        """Test that trailing slash is removed from non-root paths."""
        result = normalize_url("https://example.com/blog/")
        assert result == "https://example.com/blog"

    def test_normalize_url_preserves_root_slash(self):
        """Test that root path keeps trailing slash."""
        result = normalize_url("https://example.com/")
        assert result == "https://example.com/"

    def test_normalize_url_adds_root_slash_when_missing(self):
        """Test that root path gets slash when missing."""
        result = normalize_url("https://example.com")
        assert result == "https://example.com/"

    def test_normalize_url_removes_fragment(self):
        """Test that URL fragments (# anchors) are removed."""
        result = normalize_url("https://example.com/blog#section")
        assert result == "https://example.com/blog"

    def test_normalize_url_removes_fragment_with_trailing_slash(self):
        """Test fragment removal with trailing slash."""
        result = normalize_url("https://example.com/blog/#section")
        assert result == "https://example.com/blog"

    def test_normalize_url_preserves_query_parameters(self):
        """Test that query parameters are preserved."""
        result = normalize_url("https://example.com/blog?query=test")
        assert result == "https://example.com/blog?query=test"

    def test_normalize_url_preserves_multiple_query_parameters(self):
        """Test that multiple query parameters are preserved."""
        result = normalize_url("https://example.com/blog?param1=value1&param2=value2")
        assert result == "https://example.com/blog?param1=value1&param2=value2"

    def test_normalize_url_preserves_query_and_removes_fragment(self):
        """Test that query is preserved while fragment is removed."""
        result = normalize_url("https://example.com/blog?query=test#section")
        assert result == "https://example.com/blog?query=test"

    def test_normalize_url_handles_empty_string(self):
        """Test that empty string is returned unchanged."""
        result = normalize_url("")
        assert result == ""

    def test_normalize_url_handles_none_equivalent(self):
        """Test that empty/falsy values are handled gracefully."""
        result = normalize_url("")
        assert result == ""

    def test_normalize_url_lowercases_scheme(self):
        """Test that URL scheme is lowercased."""
        result = normalize_url("HTTPS://example.com/blog")
        assert result == "https://example.com/blog"

    def test_normalize_url_lowercases_domain(self):
        """Test that domain is lowercased."""
        result = normalize_url("https://EXAMPLE.COM/blog")
        assert result == "https://example.com/blog"

    def test_normalize_url_lowercases_path(self):
        """Test that path is lowercased."""
        result = normalize_url("https://example.com/BLOG/ARTICLE")
        assert result == "https://example.com/blog/article"

    def test_normalize_url_handles_http_scheme(self):
        """Test that HTTP (non-HTTPS) URLs are handled correctly."""
        result = normalize_url("http://example.com/blog")
        assert result == "http://example.com/blog"

    def test_normalize_url_complex_path(self):
        """Test normalization of complex path with multiple segments."""
        result = normalize_url("https://example.com/blog/2024/my-article/")
        assert result == "https://example.com/blog/2024/my-article"

    def test_normalize_url_preserves_path_with_file_extension(self):
        """Test that file extensions in paths are preserved."""
        result = normalize_url("https://example.com/page.html")
        assert result == "https://example.com/page.html"

    def test_normalize_url_complete_transformation(self):
        """Test complete normalization with all transformations."""
        result = normalize_url("HTTPS://Example.COM/Blog/Article/#section")
        assert result == "https://example.com/blog/article"

    def test_normalize_url_with_port_number(self):
        """Test that port numbers are handled correctly."""
        result = normalize_url("https://example.com:8080/blog")
        assert result == "https://example.com:8080/blog"

    def test_normalize_url_with_subdomain(self):
        """Test that subdomains are normalized."""
        result = normalize_url("https://Blog.Example.COM/article")
        assert result == "https://blog.example.com/article"

    def test_normalize_url_removes_multiple_trailing_slashes(self):
        """Test that multiple trailing slashes are removed."""
        result = normalize_url("https://example.com/blog///")
        assert result == "https://example.com/blog"

    def test_normalize_url_query_with_uppercase(self):
        """Test that query parameters maintain their case (URL path is lowercased but query values stay)."""
        # Note: The path is lowercased, but query parameter keys and values are preserved as-is
        result = normalize_url("https://example.com/Blog?Query=Test")
        assert result == "https://example.com/blog?Query=Test"

    def test_normalize_url_with_path_and_query_and_fragment(self):
        """Test normalization with path, query, and fragment all present."""
        result = normalize_url("https://Example.com/Blog/Article?id=123&ref=home#comments")
        assert result == "https://example.com/blog/article?id=123&ref=home"

    def test_normalize_url_idempotent(self):
        """Test that normalizing an already normalized URL returns the same result."""
        url = "https://example.com/blog"
        result1 = normalize_url(url)
        result2 = normalize_url(result1)
        assert result1 == result2

    def test_normalize_url_with_encoded_characters(self):
        """Test that URL-encoded characters are preserved."""
        result = normalize_url("https://example.com/blog/my%20article")
        assert result == "https://example.com/blog/my%20article"

    def test_normalize_url_relative_url(self):
        """Test handling of relative URLs (edge case)."""
        # Relative URLs without scheme/netloc should still be processed
        result = normalize_url("/Blog/Article/")
        assert result == "/blog/article"

    def test_normalize_url_relative_url_with_query(self):
        """Test relative URL with query parameters."""
        result = normalize_url("/Blog?param=value")
        assert result == "/blog?param=value"

    def test_normalize_url_relative_url_with_fragment(self):
        """Test relative URL with fragment."""
        result = normalize_url("/Blog#section")
        assert result == "/blog"

    def test_normalize_url_single_slash(self):
        """Test that single slash (root) is preserved."""
        result = normalize_url("/")
        assert result == "/"

    def test_normalize_url_with_params(self):
        """Test that URL params (semicolon-separated) are preserved."""
        result = normalize_url("https://example.com/blog;param=value")
        assert result == "https://example.com/blog;param=value"
