"""
URL Normalizer Utility

Normalizes URLs for consistent matching between Google Analytics data and internal articles.
Applied at read time when querying metrics, not when storing data.
"""

from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent matching.
    
    Transformations:
    - Convert to lowercase (scheme, netloc, path)
    - Remove trailing slash (except root path "/")
    - Remove URL fragments (# anchors)
    - Preserve protocol (http/https)
    - Preserve query parameters
    
    Examples:
    - "https://Example.com/Blog/" → "https://example.com/blog"
    - "https://example.com/blog#section" → "https://example.com/blog"
    - "https://example.com/" → "https://example.com/"
    - "https://example.com" → "https://example.com/"
    - "" → ""
    - None → None (handled gracefully)
    
    Args:
        url: URL string to normalize
        
    Returns:
        Normalized URL string
        
    Raises:
        None - handles edge cases gracefully
    """
    if not url:
        return url or ""
    
    try:
        parsed = urlparse(url)
        
        # Lowercase scheme, netloc, and path
        scheme = parsed.scheme.lower() if parsed.scheme else ""
        netloc = parsed.netloc.lower() if parsed.netloc else ""
        path = parsed.path.lower() if parsed.path else ""
        
        # Handle path normalization
        if path and path != "/" and path.endswith("/"):
            # Remove trailing slash (except for root)
            path = path.rstrip("/")
        elif not path and netloc:
            # Ensure root path has slash for domains
            path = "/"
        
        # Remove fragment, preserve query and params
        fragment = ""
        query = parsed.query if parsed.query else ""
        params = parsed.params if parsed.params else ""
        
        return urlunparse((scheme, netloc, path, params, query, fragment))
        
    except Exception:
        # If URL parsing fails, return original URL
        # This handles malformed URLs gracefully
        return url