"""
Shopify Store Connector

Handles connecting and validating Shopify stores via Admin API.
Authentication uses Store URL + Shopify Admin Access Token (no OAuth).
"""

import logging
from typing import Any, Dict, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.api.middleware.exceptions import (
    ExternalServiceTimeoutException,
    RextExternalServiceException,
)

logger = logging.getLogger(__name__)

# Shopify Admin API version (pinned for stability)
SHOPIFY_API_VERSION = "2024-01"


class ShopifyConnector:
    """
    Shopify Admin API client for store connection management.

    Authenticates via the `X-Shopify-Access-Token` header using a
    private/custom app Admin API access token.
    """

    def __init__(self, store_url: str, access_token: str):
        """
        Initialise the Shopify connector.

        Args:
            store_url:     The Shopify store URL.  Accepts either the full
                           myshopify domain (e.g. ``my-store.myshopify.com``)
                           or a bare shop name (e.g. ``my-store``).
            access_token:  Shopify Admin API access token.
        """
        # Normalise store URL — always force HTTPS regardless of what was supplied
        store_url = store_url.strip().rstrip("/")
        # Strip any existing scheme (http:// or https://) so we can add https://
        for scheme in ("https://", "http://"):
            if store_url.startswith(scheme):
                store_url = store_url[len(scheme):]
                break
        # Append .myshopify.com if a bare shop name was given
        if not store_url.endswith(".myshopify.com") and "." not in store_url:
            store_url = f"{store_url}.myshopify.com"
        store_url = f"https://{store_url}"

        self.store_url = store_url
        self.access_token = access_token
        self.base_url = f"{self.store_url}/admin/api/{SHOPIFY_API_VERSION}"

        self._client = httpx.AsyncClient(
            headers={
                "X-Shopify-Access-Token": self.access_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=15.0,
        )

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ShopifyConnector":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Connection validation
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def test_connection(self) -> Dict[str, Any]:
        """
        Verify the store URL and access token by fetching shop details.

        Calls ``GET /admin/api/{version}/shop.json``.

        Returns:
            Dict with basic shop information (name, domain, email, plan, etc.)

        Raises:
            RextExternalServiceException:  Invalid credentials or unreachable store.
            ExternalServiceTimeoutException:  Request timed out.
        """
        endpoint = f"{self.base_url}/shop.json"

        try:
            logger.info(f"Testing Shopify connection for store: {self.store_url}")
            response = await self._client.get(endpoint)

            if response.status_code == 401:
                raise RextExternalServiceException(
                    message=(
                        "Shopify authentication failed. "
                        "Please check your access token."
                    ),
                    service_name="Shopify",
                )

            if response.status_code == 404:
                raise RextExternalServiceException(
                    message=(
                        "Shopify store not found. "
                        "Please verify your store URL."
                    ),
                    service_name="Shopify",
                )

            if response.status_code != 200:
                raise RextExternalServiceException(
                    message=(
                        f"Shopify API returned unexpected status {response.status_code}: "
                        f"{response.text[:200]}"
                    ),
                    service_name="Shopify",
                )

            shop_data: Dict[str, Any] = response.json().get("shop", {})
            logger.info(
                f"Shopify connection successful. Shop: {shop_data.get('name')} "
                f"({shop_data.get('myshopify_domain')})"
            )
            return {
                "name": shop_data.get("name"),
                "domain": shop_data.get("domain"),
                "myshopify_domain": shop_data.get("myshopify_domain"),
                "email": shop_data.get("email"),
                "plan_name": shop_data.get("plan_name"),
                "currency": shop_data.get("currency"),
                "timezone": shop_data.get("iana_timezone"),
            }

        except (RextExternalServiceException, ExternalServiceTimeoutException):
            raise

        except httpx.TimeoutException as exc:
            logger.error(f"Timeout connecting to Shopify store {self.store_url}: {exc}")
            raise ExternalServiceTimeoutException(
                service_name="Shopify", timeout_seconds=15
            )

        except httpx.HTTPError as exc:
            error_msg = f"HTTP error connecting to Shopify store {self.store_url}: {exc}"
            logger.error(error_msg)
            raise RextExternalServiceException(
                message=error_msg, service_name="Shopify"
            )

        except Exception as exc:
            error_msg = f"Unexpected error during Shopify connection test: {exc}"
            logger.error(error_msg)
            raise RextExternalServiceException(
                message=error_msg, service_name="Shopify"
            )

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def _get_default_blog_id(self) -> int:
        """
        Return the ID of the first blog in the store, creating one if needed.

        Shopify articles must belong to a blog.  Most stores have a single
        default blog (e.g. "News" or "Blog").  We pick the first one; if
        none exists we create a blog called "Rext AI Blog".
        """
        endpoint = f"{self.base_url}/blogs.json"
        response = await self._client.get(endpoint, params={"limit": 1})
        if response.status_code != 200:
            raise RextExternalServiceException(
                message=f"Failed to fetch Shopify blogs: {response.status_code} {response.text[:200]}",
                service_name="Shopify",
            )

        blogs = response.json().get("blogs", [])
        if blogs:
            return blogs[0]["id"]

        # No blog found — create a default one
        create_resp = await self._client.post(
            endpoint,
            json={"blog": {"title": "Rext AI Blog"}},
        )
        if create_resp.status_code not in (200, 201):
            raise RextExternalServiceException(
                message=f"Failed to create Shopify blog: {create_resp.status_code} {create_resp.text[:200]}",
                service_name="Shopify",
            )
        return create_resp.json()["blog"]["id"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def publish_blog_post(
        self,
        title: str,
        body_html: str,
        tags: Optional[list] = None,
        published: bool = True,
    ) -> Dict[str, Any]:
        """
        Publish a new article to the Shopify store blog.

        Selects (or creates) the store's default blog, then POSTs a new
        article.

        Args:
            title:      Article title.
            body_html:  Article body as HTML.  Markdown is accepted if the
                        store has the Markdown app, but HTML is universal.
            tags:       Optional list of tag strings.
            published:  Whether to publish immediately (True) or save as
                        draft (False).

        Returns:
            Dict with ``article_id``, ``article_url``, ``title``, and
            ``published_at``.

        Raises:
            RextExternalServiceException:   API error.
            ExternalServiceTimeoutException:  Request timed out.
        """
        try:
            blog_id = await self._get_default_blog_id()
            endpoint = f"{self.base_url}/blogs/{blog_id}/articles.json"

            payload: Dict[str, Any] = {
                "article": {
                    "title": title,
                    "body_html": body_html,
                    "published": published,
                }
            }
            if tags:
                payload["article"]["tags"] = ", ".join(str(t) for t in tags)

            logger.info(
                f"Publishing article '{title}' to Shopify store: {self.store_url} "
                f"(blog_id={blog_id}, published={published})"
            )

            response = await self._client.post(endpoint, json=payload, timeout=30.0)

            if response.status_code == 401:
                raise RextExternalServiceException(
                    message="Shopify authentication failed while publishing. Check your access token.",
                    service_name="Shopify",
                )

            if response.status_code not in (200, 201):
                raise RextExternalServiceException(
                    message=(
                        f"Shopify API error while publishing article "
                        f"({response.status_code}): {response.text[:300]}"
                    ),
                    service_name="Shopify",
                )

            article = response.json().get("article", {})
            article_id = article.get("id")

            # Build the public article URL  →  https://{domain}/blogs/{blog_handle}/{article_handle}
            # We fetch the blog handle separately to construct the URL cleanly.
            blog_resp = await self._client.get(f"{self.base_url}/blogs/{blog_id}.json")
            blog_handle = blog_resp.json().get("blog", {}).get("handle", "blog") if blog_resp.status_code == 200 else "blog"
            article_handle = article.get("handle", "")
            # Use the store's primary domain if available, else myshopify domain
            domain = self.store_url
            article_url = f"{domain}/blogs/{blog_handle}/{article_handle}"

            logger.info(
                f"Successfully published Shopify article! "
                f"ID: {article_id}, URL: {article_url}"
            )

            return {
                "article_id": article_id,
                "article_url": article_url,
                "title": article.get("title"),
                "published_at": article.get("published_at"),
            }

        except (RextExternalServiceException, ExternalServiceTimeoutException):
            raise

        except httpx.TimeoutException as exc:
            logger.error(f"Timeout publishing article to Shopify store {self.store_url}: {exc}")
            raise ExternalServiceTimeoutException(service_name="Shopify", timeout_seconds=30)

        except httpx.HTTPError as exc:
            error_msg = f"HTTP error publishing to Shopify: {exc}"
            logger.error(error_msg)
            raise RextExternalServiceException(message=error_msg, service_name="Shopify")

        except Exception as exc:
            error_msg = f"Unexpected error publishing to Shopify: {exc}"
            logger.error(error_msg)
            raise RextExternalServiceException(message=error_msg, service_name="Shopify")

