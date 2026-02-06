"""
WordPress Publishing Service

Handles publishing content to WordPress via REST API.
"""

import logging
import os
import httpx
from typing import Dict, Optional
from src.api.schema.content_schema import ContentCreate, ContentUpdate, ContentResponse

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
        self.verify_ssl = verify_ssl if os.getenv("ENVIRONMENT") == "production" else False

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
            masked_key = f"{self.api_key[:10]}...{self.api_key[-6:]}" if len(self.api_key) > 16 else "***"
            logger.info(f"WordPress publisher initialized with API key: {masked_key}")
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
            else:
                error_msg = f"Rext-AI validation failed (Status {response.status_code}): {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except httpx.HTTPError as e:
            error_msg = f"Failed to connect to Rext-AI plugin at {endpoint}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    async def publish_post(
        self,
        data: ContentCreate,
        status: str = "publish",
        excerpt: Optional[str] = None,
        tags: Optional[list] = None,
        categories: Optional[list] = None,
        meta: Optional[Dict] = None
    ) -> Dict:
        """
        Publish a post to WordPress.

        Args:
            data: ContentCreate schema with content data
            status: Post status ('publish', 'draft', 'pending', 'private')
            excerpt: Post excerpt/meta description (falls back to SEO meta_description)
            tags: List of tag names (falls back to data.tags)
            categories: List of category names or IDs
            meta: Custom meta fields

        Returns:
            Dict containing post data from WordPress API

        Raises:
            Exception: If publishing fails
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

        post_data = {
            "title": title,
            "content": content,
            "status": status,
        }

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
            logger.info(f"Using endpoint: {endpoint}")

            response = await self.client.post(endpoint, json=post_data, timeout=30)
            response.raise_for_status()

            post = response.json()
            logger.info(
                f"Successfully published to WordPress! "
                f"Post ID: {post.get('id')}, Link: {post.get('link')}"
            )

            return {
                "success": True,
                "post_id": post.get("id"),
                "link": post.get("link"),
                "status": post.get("status"),
                "title": post.get("title", {}).get("rendered"),
            }

        except httpx.HTTPStatusError as e:
            error_msg = f"WordPress API error: {e}"
            if e.response is not None:
                error_msg += f" - {e.response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        except Exception as e:
            error_msg = f"Failed to publish to WordPress: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    async def _get_or_create_tags(self, tag_names: list) -> list:
        """
        Get tag IDs for tag names, creating them if they don't exist.

        Args:
            tag_names: List of tag names

        Returns:
            List of tag IDs
        """
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

    async def update_post(self, post_id: int, **kwargs) -> Dict:
        """
        Update an existing WordPress post.

        Args:
            post_id: WordPress post ID
            **kwargs: Fields to update (title, content, status, etc.)

        Returns:
            Dict containing updated post data
        """
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
