"""
WordPress Publishing Service

Handles publishing content to WordPress via REST API.
Move from src/services/wordpress_publisher.py to src/web/wordpress.py.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
from src.api.schema.content_schema import ContentCreate
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx
from src.api.middleware.exceptions import RextExternalServiceException, ExternalServiceTimeoutException

logger = logging.getLogger(__name__)


class WordPressPublisher:
    """WordPress REST API client for publishing content."""

    def __init__(
        self,
        site_url: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        username: Optional[str] = None,
        app_password: Optional[str] = None,
        api_key: Optional[str] = None,
        verify_ssl: bool = True
    ):
        """
        Initialize WordPress publisher.

        Args:
            site_url: WordPress site URL (e.g., https://example.com)
            api_endpoint: Custom Rext-AI Plugin API endpoint (e.g. https://site.com/wp-json/rext-ai/v1/)
            username: WordPress username
            app_password: WordPress Application Password
            api_key: Rext-AI Plugin API Key (Bearer Token)
            verify_ssl: Whether to verify SSL certificates (set False for local dev)
        """
        self.site_url = site_url or os.getenv("WORDPRESS_SITE_URL", "")
        self.api_endpoint = api_endpoint or os.getenv("WORDPRESS_API_ENDPOINT", "")
        self.username = username or os.getenv("WORDPRESS_USERNAME", "")
        self.app_password = app_password or os.getenv("WORDPRESS_APP_PASSWORD", "")
        self.api_key = api_key or os.getenv("WORDPRESS_API_KEY", "")
        
        # SSL verification logic
        env = os.getenv("ENVIRONMENT", "development")
        if env == "production":
            self.verify_ssl = verify_ssl
        else:
            self.verify_ssl = False

        # Remove trailing slash from URLs
        self.site_url = self.site_url.rstrip("/")
        if self.api_endpoint:
            self.api_endpoint = self.api_endpoint.rstrip("/")

        # Remove spaces from application password
        self.app_password = self.app_password.replace(" ", "")

        # Build client config
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        auth = None

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            logger.info(f"WordPress publisher initialized with API key for site: {self.site_url}")
        elif self.username and self.app_password:
            auth = httpx.BasicAuth(self.username, self.app_password)
        else:
            logger.warning(
                "WordPress credentials not fully configured. "
                "Set WORDPRESS_SITE_URL, WORDPRESS_USERNAME, and WORDPRESS_APP_PASSWORD"
            )

        self.client = httpx.AsyncClient(
            verify=self.verify_ssl,
            headers=headers,
            auth=auth,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit, ensures client is closed."""
        await self.close()

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def validate_plugin(self) -> bool:
        """
        Validate the Rext-AI WordPress plugin connection.

        Returns:
            True if valid, raises an exception if invalid.
        """
        endpoint = self.api_endpoint if self.api_endpoint else f"{self.site_url}/wp-json/rext-ai/v1/"

        try:
            response = await self.client.get(endpoint, timeout=15)

            if response.status_code == 200:
                return True
        except httpx.TimeoutException as e:
            error_msg = f"Timeout connecting to Rext-AI plugin at {endpoint}: {str(e)}"
            logger.error(error_msg)
            raise ExternalServiceTimeoutException(service_name="WordPress (Plugin)", timeout_seconds=15)
            
        except httpx.HTTPError as e:
            error_msg = f"Failed to connect to Rext-AI plugin at {endpoint}: {str(e)}"
            logger.error(error_msg)
            raise RextExternalServiceException(message=error_msg, service_name="WordPress")
        
        except Exception as e:
            error_msg = f"Unexpected error during WordPress plugin validation: {str(e)}"
            logger.error(error_msg)
            raise RextExternalServiceException(message=error_msg, service_name="WordPress")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True
    )
    async def publish_post(
        self,
        data: ContentCreate,
        status: str = "publish",
        excerpt: Optional[str] = None,
        tags: Optional[List[str]] = None,
        categories: Optional[List[int]] = None,
        meta: Optional[Dict[str, Any]] = None,
        scheduled_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Publish a post to WordPress.

        Args:
            data: ContentCreate schema with content data
            status: Post status ('publish', 'draft', 'pending', 'private')
            excerpt: Post excerpt/meta description
            tags: List of tag names
            categories: List of category names or IDs
            meta: Custom meta fields

        Returns:
            Dict containing post data from WordPress API
        """
        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/posts"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/posts"

        # Extract content from ContentCreate schema
        title = data.title

        content_parts = []
        if data.introduction:
            content_parts.append(data.introduction)

        if data.body_html:
            content_parts.append(data.body_html)
        elif data.body_markdown:
            content_parts.append(data.body_markdown)

        content = "\n\n".join(content_parts) if content_parts else ""

        if not content:
            raise ValueError("Content body (HTML or Markdown) is required for publishing")

        if not excerpt and data.seo_data and data.seo_data.meta_description:
            excerpt = data.seo_data.meta_description

        if not tags and data.tags:
            tags = data.tags

        # If scheduled_at is in the future, override status to "future" and set date_gmt
        if scheduled_at:
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            if scheduled_at > datetime.now(timezone.utc):
                status = "future"

        post_data = {
            "title": title,
            "content": content,
            "status": status,
        }

        if status == "future" and scheduled_at:
            # WP REST API: date_gmt must be UTC — convert regardless of incoming tz offset
            post_data["date_gmt"] = scheduled_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        if excerpt:
            post_data["excerpt"] = excerpt

        if tags:
            tag_ids = await self._get_or_create_tags(tags)
            if tag_ids:
                post_data["tags"] = tag_ids

        if categories:
            post_data["categories"] = categories

        if meta:
            post_data["meta"] = meta

        try:
            logger.info(f"Publishing post to WordPress: {title}")
            
            response = await self.client.post(endpoint, json=post_data, timeout=30)
            response.raise_for_status()

            raw = response.json()

            # Rext-AI plugin wraps payload under "data"; standard WP REST API is flat.
            post = raw.get("data") if isinstance(raw.get("data"), dict) else raw

            post_id = post.get("id")
            link = post.get("url") or post.get("link")   # plugin uses "url", REST uses "link"
            post_status = post.get("status")
            raw_title = post.get("title")
            post_title = raw_title.get("rendered") if isinstance(raw_title, dict) else raw_title

            logger.info(f"Successfully published to WordPress! Post ID: {post_id}, Link: {link}")

            return {
                "success": True,
                "post_id": post_id,
                "link": link,
                "status": post_status,
                "title": post_title,
            }

        except httpx.TimeoutException as e:
            error_msg = f"Timeout publishing to WordPress: {e}"
            logger.error(error_msg)
            raise ExternalServiceTimeoutException(service_name="WordPress", timeout_seconds=30)

        except httpx.HTTPStatusError as e:
            error_msg = f"WordPress API error: {e}"
            if e.response is not None:
                error_msg += f" - {e.response.text}"
            logger.error(error_msg)
            raise RextExternalServiceException(message=error_msg, service_name="WordPress")

        except Exception as e:
            error_msg = f"Unexpected failure to publish to WordPress: {str(e)}"
            logger.error(error_msg)
            raise RextExternalServiceException(message=error_msg, service_name="WordPress")

    async def _get_or_create_tags(self, tag_names: List[str]) -> List[int]:
        """Get tag IDs for tag names, creating them if they don't exist."""
        tag_ids = []
        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/tags"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/tags"

        for tag_name in tag_names:
            try:
                response = await self.client.get(
                    endpoint,
                    params={"search": tag_name},
                    timeout=10
                )

                if response.status_code == 200:
                    tags = response.json()
                    if tags:
                        tag_ids.append(tags[0]["id"])
                    else:
                        create_response = await self.client.post(
                            endpoint,
                            json={"name": tag_name},
                            timeout=10
                        )
                        if create_response.status_code == 201:
                            tag_ids.append(create_response.json()["id"])

            except Exception as e:
                logger.warning(f"Could not process tag '{tag_name}': {e}")
                continue

        return tag_ids

    async def update_post(self, post_id: int, **kwargs) -> Dict[str, Any]:
        """Update an existing WordPress post."""
        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/posts/{post_id}"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/posts/{post_id}"

        try:
            response = await self.client.post(endpoint, json=kwargs, timeout=30)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to update post {post_id}: {e}")
            raise

    async def get_post_status(self, post_id: int) -> Dict[str, Any]:
        """
        Fetch the current status of a WordPress post.
        
        Returns:
            Dict with 'status' ('publish', 'draft', 'trash', etc.) and 'link'.
            If the post is not found (404), returns status 'deleted'.
        """
        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/posts/{post_id}"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/posts/{post_id}"

        try:
            response = await self.client.get(endpoint, timeout=15)
            
            if response.status_code == 404:
                return {"status": "deleted", "success": True}
                
            response.raise_for_status()
            raw = response.json()
            data = raw.get("data") if isinstance(raw.get("data"), dict) else raw

            return {
                "status": data.get("status"),
                "link": data.get("url") or data.get("link"),
                "success": True,
            }
        except Exception as e:
            logger.error(f"Failed to fetch WordPress post status for {post_id}: {e}")
            return {"status": "unknown", "success": False, "error": str(e)}

