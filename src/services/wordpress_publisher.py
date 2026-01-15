"""
WordPress Publishing Service

Handles publishing content to WordPress via REST API.
"""

import logging
import os
import requests
import urllib3
from typing import Dict, Optional

# Disable SSL warnings for local development (remove in production!)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class WordPressPublisher:
    """WordPress REST API client for publishing content."""
    
    def __init__(
        self,
        site_url: Optional[str] = None,
        username: Optional[str] = None,
        app_password: Optional[str] = None,
        verify_ssl: bool = True
    ):
        """
        Initialize WordPress publisher.
        
        Args:
            site_url: WordPress site URL (e.g., https://example.com)
            username: WordPress username
            app_password: WordPress Application Password
            verify_ssl: Whether to verify SSL certificates (set False for local dev)
        """
        self.site_url = site_url or os.getenv("WORDPRESS_SITE_URL", "")
        self.username = username or os.getenv("WORDPRESS_USERNAME", "")
        self.app_password = app_password or os.getenv("WORDPRESS_APP_PASSWORD", "")
        self.verify_ssl = verify_ssl if os.getenv("ENVIRONMENT") == "production" else False
        
        # Remove trailing slash from site URL
        self.site_url = self.site_url.rstrip("/")
        
        # Remove spaces from application password
        self.app_password = self.app_password.replace(" ", "")
        
        if not all([self.site_url, self.username, self.app_password]):
            logger.warning(
                "WordPress credentials not fully configured. "
                "Set WORDPRESS_SITE_URL, WORDPRESS_USERNAME, and WORDPRESS_APP_PASSWORD"
            )
    
    def publish_post(
        self,
        title: str,
        content: str,
        status: str = "publish",
        excerpt: Optional[str] = None,
        tags: Optional[list] = None,
        categories: Optional[list] = None,
        meta: Optional[Dict] = None
    ) -> Dict:
        """
        Publish a post to WordPress.
        
        Args:
            title: Post title
            content: Post content (HTML or markdown converted to HTML)
            status: Post status ('publish', 'draft', 'pending', 'private')
            excerpt: Post excerpt/meta description
            tags: List of tag names
            categories: List of category names or IDs
            meta: Custom meta fields
        
        Returns:
            Dict containing post data from WordPress API
        
        Raises:
            Exception: If publishing fails
        """
        endpoint = f"{self.site_url}/wp-json/wp/v2/posts"
        
        # Prepare post data
        post_data = {
            "title": title,
            "content": content,
            "status": status,
        }
        
        if excerpt:
            post_data["excerpt"] = excerpt
        
        if tags:
            # Get or create tags
            tag_ids = self._get_or_create_tags(tags)
            if tag_ids:
                post_data["tags"] = tag_ids
        
        if categories:
            post_data["categories"] = categories
        
        if meta:
            post_data["meta"] = meta
        
        try:
            logger.info(f"Publishing post to WordPress: {title}")
            
            response = requests.post(
                endpoint,
                json=post_data,
                auth=(self.username, self.app_password),
                verify=self.verify_ssl,
                timeout=30
            )
            
            response.raise_for_status()
            
            post = response.json()
            logger.info(
                f"✅ Successfully published to WordPress! "
                f"Post ID: {post.get('id')}, Link: {post.get('link')}"
            )
            
            return {
                "success": True,
                "post_id": post.get("id"),
                "link": post.get("link"),
                "status": post.get("status"),
                "title": post.get("title", {}).get("rendered"),
            }
        
        except requests.exceptions.HTTPError as e:
            error_msg = f"WordPress API error: {e}"
            if hasattr(e.response, 'text'):
                error_msg += f" - {e.response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        except Exception as e:
            error_msg = f"Failed to publish to WordPress: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def _get_or_create_tags(self, tag_names: list) -> list:
        """
        Get tag IDs for tag names, creating them if they don't exist.
        
        Args:
            tag_names: List of tag names
        
        Returns:
            List of tag IDs
        """
        tag_ids = []
        endpoint = f"{self.site_url}/wp-json/wp/v2/tags"
        
        for tag_name in tag_names:
            try:
                # Search for existing tag
                response = requests.get(
                    endpoint,
                    params={"search": tag_name},
                    auth=(self.username, self.app_password),
                    verify=self.verify_ssl,
                    timeout=10
                )
                
                if response.status_code == 200:
                    tags = response.json()
                    if tags:
                        tag_ids.append(tags[0]["id"])
                    else:
                        # Create new tag
                        create_response = requests.post(
                            endpoint,
                            json={"name": tag_name},
                            auth=(self.username, self.app_password),
                            verify=self.verify_ssl,
                            timeout=10
                        )
                        if create_response.status_code == 201:
                            tag_ids.append(create_response.json()["id"])
            
            except Exception as e:
                logger.warning(f"Could not process tag '{tag_name}': {e}")
                continue
        
        return tag_ids
    
    def update_post(self, post_id: int, **kwargs) -> Dict:
        """
        Update an existing WordPress post.
        
        Args:
            post_id: WordPress post ID
            **kwargs: Fields to update (title, content, status, etc.)
        
        Returns:
            Dict containing updated post data
        """
        endpoint = f"{self.site_url}/wp-json/wp/v2/posts/{post_id}"
        
        try:
            response = requests.post(
                endpoint,
                json=kwargs,
                auth=(self.username, self.app_password),
                verify=self.verify_ssl,
                timeout=30
            )
            
            response.raise_for_status()
            return response.json()
        
        except Exception as e:
            logger.error(f"Failed to update post {post_id}: {e}")
            raise
