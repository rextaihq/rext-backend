from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.api.middleware.exceptions import RextExternalServiceException
from src.api.schema.content_schema import ContentCreate
from src.utils.storage import storage_service
from src.web.wordpress import WordPressPublisher


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test here reaches the network. The publisher sends through client.request (its retry
    helper), and these tests mock the client's get and post, so a request goes to the mock its
    method names; anything left unmocked fails here instead of calling example.com."""

    async def request(self, method, url, **kwargs):
        mocked = self.__dict__.get(method.lower())
        if mocked is None:
            raise AssertionError(f"unmocked {method} {url} in a unit test")
        return await mocked(url, **kwargs)

    async def send(self, request, **kwargs):
        raise AssertionError(f"network call in a unit test: {request.method} {request.url}")

    monkeypatch.setattr(httpx.AsyncClient, "request", request)
    monkeypatch.setattr(httpx.AsyncClient, "send", send)


@pytest.mark.asyncio
async def test_downloads_own_minio_image_through_storage_client(monkeypatch):
    publisher = WordPressPublisher(
        site_url="https://example.com",
        username="user",
        app_password="pass",
    )
    image_bytes = b"\x89PNG\r\n\x1a\nstored-image"
    download_file = Mock(return_value=image_bytes)
    to_thread = AsyncMock(side_effect=lambda function, *args: function(*args))
    monkeypatch.setattr(storage_service, "download_file", download_file)
    monkeypatch.setattr("src.web.wordpress.asyncio.to_thread", to_thread)

    response = await publisher._download_image(
        "http://localhost:9000/rext-media/generated-images/source.png?X-Amz-Signature=expired"
    )

    download_file.assert_called_once_with("generated-images/source.png")
    to_thread.assert_awaited_once()
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == image_bytes


@pytest.mark.asyncio
async def test_feature_image_download_retries_connect_error_with_exact_reason(
    monkeypatch,
):
    publisher = WordPressPublisher(
        site_url="https://example.com",
        username="user",
        app_password="pass",
    )
    request = httpx.Request("GET", "https://cdn.rext.test/image.png")
    download = AsyncMock(
        side_effect=httpx.ConnectError(
            "connection refused",
            request=request,
        )
    )
    sleep = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "get", download)
    monkeypatch.setattr("src.web.wordpress.asyncio.sleep", sleep)

    with pytest.raises(
        RextExternalServiceException,
        match=(
            r"download network connection failed.*cdn\.rext\.test/image\.png"
            r".*after 3 attempts.*ConnectError"
        ),
    ):
        await publisher._upload_featured_image("https://cdn.rext.test/image.png")

    assert download.await_count == 3
    assert sleep.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["publish", "draft", "pending"])
async def test_publish_post_sends_and_confirms_selected_wordpress_status(status):
    publisher = WordPressPublisher(
        site_url="https://example.com",
        username="user",
        app_password="pass",
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201,
            json={
                "id": 90,
                "status": status,
                "title": "Status test",
            },
        )
    )

    result = await publisher.publish_post(
        ContentCreate(
            title="Status test",
            body_html="<p>Content</p>",
        ),
        status=status,
    )

    assert publisher.client.post.await_args.kwargs["json"]["status"] == status
    assert result["status"] == status


@pytest.mark.asyncio
async def test_publish_post_maps_review_alias_to_wordpress_pending():
    publisher = WordPressPublisher(
        site_url="https://example.com",
        username="user",
        app_password="pass",
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"id": 91, "status": "pending"},
        )
    )

    result = await publisher.publish_post(
        ContentCreate(title="Review alias", body_html="<p>Content</p>"),
        status="review",
    )

    assert publisher.client.post.await_args.kwargs["json"]["status"] == "pending"
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_publish_post_rejects_unconfirmed_wordpress_status():
    publisher = WordPressPublisher(
        site_url="https://example.com",
        username="user",
        app_password="pass",
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"id": 92, "status": "draft"},
        )
    )
    publisher.client.get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"id": 92, "status": "draft"},
        )
    )

    with pytest.raises(
        RextExternalServiceException,
        match="did not confirm the requested post status",
    ):
        await publisher.publish_post(
            ContentCreate(
                title="Status mismatch",
                body_html="<p>Content</p>",
            ),
            status="pending",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selected_status", "expected_status"),
    [
        ("publish", "publish"),
        ("draft", "draft"),
        ("pending", "pending"),
        ("review", "pending"),
    ],
)
async def test_update_post_sends_and_confirms_wordpress_status(
    selected_status,
    expected_status,
):
    publisher = WordPressPublisher(
        site_url="https://example.com",
        username="user",
        app_password="pass",
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"id": 93, "status": expected_status},
        )
    )

    result = await publisher.update_post(93, status=selected_status)

    assert publisher.client.post.await_args.kwargs["json"]["status"] == expected_status
    assert result["status"] == expected_status


@pytest.mark.asyncio
async def test_publish_post_uploads_feature_image_and_sets_featured_media():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )

    image_bytes = b"\x89PNG\r\n\x1a\nfake-image-bytes"
    image_response = httpx.Response(
        200,
        content=image_bytes,
        headers={"content-type": "image/png"},
        request=httpx.Request("GET", "https://cdn.rext.test/ai-image.png"),
    )
    upload_response = httpx.Response(
        201,
        json={
            "id": 42,
            "source_url": "https://example.com/wp-content/uploads/2024/07/ai-image.jpg",
            "link": "https://example.com/wp-content/uploads/2024/07/ai-image.jpg",
        },
    )
    publish_response = httpx.Response(
        201,
        json={
            "id": 99,
            "url": "https://example.com/post",
            "status": "publish",
            "title": "Test",
            "featured_media": 42,
        },
    )
    publisher._download_image = AsyncMock(return_value=image_response)
    publisher.client.send = AsyncMock(return_value=upload_response)
    publisher.client.post = AsyncMock(return_value=publish_response)

    data = ContentCreate(
        title="Hello world",
        body_markdown="Here is the generated image: ![image](https://cdn.rext.test/ai-image.png)",
        images_data={"feature_image_url": "https://cdn.rext.test/ai-image.png"},
    )

    result = await publisher.publish_post(data=data, status="publish")

    assert result["success"] is True
    assert result["post_id"] == 99

    upload_request = publisher.client.send.await_args.args[0]
    assert upload_request.url == "https://example.com/wp-json/wp/v2/media"
    assert upload_request.headers["content-type"].startswith("multipart/form-data; boundary=")

    publish_call = publisher.client.post.await_args
    payload = publish_call.kwargs["json"]
    assert payload["featured_media"] == 42
    assert "featured_image" not in payload
    # The theme shows the featured image, so its inline copy is dropped (it would show twice).
    assert "https://example.com/wp-content/uploads/2024/07/ai-image.jpg" not in payload["content"]
    assert "https://cdn.rext.test/ai-image.png" not in payload["content"]


@pytest.mark.asyncio
async def test_publish_post_uses_image_from_body_markdown_when_images_data_missing():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )

    image_response = httpx.Response(
        200,
        content=b"\x89PNG\r\n\x1a\nfake-image-bytes",
        headers={"content-type": "image/png"},
        request=httpx.Request("GET", "https://cdn.rext.test/body-image.png"),
    )
    upload_response = httpx.Response(
        201,
        json={
            "id": 77,
            "source_url": "https://example.com/wp-content/uploads/2024/07/body-image.png",
            "link": "https://example.com/wp-content/uploads/2024/07/body-image.png",
        },
    )
    publish_response = httpx.Response(
        201,
        json={
            "id": 100,
            "url": "https://example.com/post",
            "status": "publish",
            "title": "Body test",
            "featured_media": 77,
        },
    )
    publisher._download_image = AsyncMock(return_value=image_response)
    publisher.client.send = AsyncMock(return_value=upload_response)
    publisher.client.post = AsyncMock(return_value=publish_response)

    data = ContentCreate(
        title="Hello body",
        body_markdown="Here is the generated image: ![image](https://cdn.rext.test/body-image.png)",
        images_data={},
    )

    result = await publisher.publish_post(data=data, status="publish")

    assert result["success"] is True
    publish_call = publisher.client.post.await_args
    payload = publish_call.kwargs["json"]
    assert payload["featured_media"] == 77
    # The theme shows the featured image, so its inline copy is dropped (it would show twice).
    assert "https://example.com/wp-content/uploads/2024/07/body-image.png" not in payload["content"]
    assert "https://cdn.rext.test/body-image.png" not in payload["content"]


@pytest.mark.asyncio
async def test_publish_post_uploads_every_embedded_image_without_uploading_links():
    publisher = WordPressPublisher(
        site_url="https://example.com",
        username="user",
        app_password="pass",
    )
    first_source = "https://minio.example.com/rext-media/blog-images/first.png"
    second_source = "https://minio.example.com/rext-media/blog-images/second.jpg"
    citation_url = "https://docs.example.org/reference"

    publisher._upload_featured_image = AsyncMock(
        side_effect=[
            {
                "media_id": 41,
                "url": "https://example.com/wp-content/uploads/first.png",
            },
            {
                "media_id": 42,
                "url": "https://example.com/wp-content/uploads/second.jpg",
            },
        ]
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201,
            json={
                "id": 101,
                "status": "publish",
                "featured_media": 41,
            },
        )
    )

    await publisher.publish_post(
        ContentCreate(
            title="Multiple inline images",
            body_markdown=(
                f"![First]({first_source})\n\n"
                f"Read the [reference]({citation_url}).\n\n"
                f"![Second]({second_source})"
            ),
        )
    )

    payload = publisher.client.post.await_args.kwargs["json"]
    assert publisher._upload_featured_image.await_count == 2
    assert first_source not in payload["content"]
    assert second_source not in payload["content"]
    assert "https://example.com/wp-content/uploads/first.png" in payload["content"]
    assert "https://example.com/wp-content/uploads/second.jpg" in payload["content"]
    assert citation_url in payload["content"]


@pytest.mark.asyncio
async def test_inline_image_already_in_destination_wordpress_media_is_not_reuploaded():
    publisher = WordPressPublisher(
        site_url="https://example.com",
        username="user",
        app_password="pass",
    )
    wordpress_image = "https://example.com/wp-content/uploads/2026/07/existing.png"
    publisher._upload_featured_image = AsyncMock()

    content = await publisher._sync_embedded_images_to_wordpress(
        f'<p>Existing image</p><img src="{wordpress_image}">',
    )

    assert wordpress_image in content
    publisher._upload_featured_image.assert_not_awaited()


@pytest.mark.asyncio
async def test_media_upload_failure_prevents_broken_post_from_being_published():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )
    publisher._download_image = AsyncMock(
        return_value=httpx.Response(
            200,
            content=b"\x89PNG\r\n\x1a\nimage",
            headers={"content-type": "image/png"},
            request=httpx.Request("GET", "https://cdn.rext.test/image.png"),
        )
    )
    publisher.client.send = AsyncMock(
        return_value=httpx.Response(
            401,
            json={"code": "rest_cannot_create", "message": "Unauthorized"},
        )
    )
    publisher.client.post = AsyncMock()

    with pytest.raises(RextExternalServiceException, match="HTTP 401"):
        await publisher.publish_post(
            ContentCreate(
                title="Upload must succeed",
                body_html='<img src="https://cdn.rext.test/image.png">',
            )
        )

    publisher.client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_html_disguised_as_image_is_rejected_before_upload():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )
    publisher._download_image = AsyncMock(
        return_value=httpx.Response(
            200,
            content=b"<html><body>expired signed URL</body></html>",
            headers={"content-type": "text/html"},
            request=httpx.Request("GET", "https://cdn.rext.test/expired.png"),
        )
    )
    publisher.client.send = AsyncMock()
    publisher.client.post = AsyncMock()

    with pytest.raises(RextExternalServiceException, match="not a valid image"):
        await publisher.publish_post(
            ContentCreate(
                title="Reject HTML",
                body_html='<img src="https://cdn.rext.test/expired.png">',
            )
        )

    publisher.client.send.assert_not_awaited()
    publisher.client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_body_image_that_cannot_be_uploaded_stops_the_publish():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )
    first = "https://cdn.rext.test/first.png"
    second = "https://cdn.rext.test/second.png?X-Amz-Signature=secret-token"
    publisher._upload_featured_image = AsyncMock(
        side_effect=[
            {"media_id": 41, "url": "https://example.com/wp-content/uploads/first.png"},
            RextExternalServiceException(
                message="WordPress media API returned HTTP 413; expected HTTP 201; body=too large",
                service_name="WordPress",
            ),
        ]
    )
    publisher.client.post = AsyncMock()

    with pytest.raises(RextExternalServiceException, match="Publishing stopped") as raised:
        await publisher.publish_post(
            ContentCreate(
                title="Two images",
                body_html=f'<img src="{first}"><p>Text</p><img src="{second}">',
            )
        )

    assert "HTTP 413" in raised.value.message
    assert "https://cdn.rext.test/second.png" in raised.value.message
    assert "secret-token" not in raised.value.message
    publisher.client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_featured_image_the_body_shows_is_not_downloaded_twice_when_it_fails():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )
    publisher._upload_featured_image = AsyncMock(
        side_effect=RextExternalServiceException(
            message="Downloaded resource is not a valid image", service_name="WordPress"
        )
    )
    publisher.client.post = AsyncMock()

    with pytest.raises(RextExternalServiceException, match="Publishing stopped"):
        await publisher.publish_post(
            ContentCreate(
                title="Featured and inline",
                body_markdown="![Hero](https://cdn.rext.test/hero.png)\n\nText.",
                images_data={"feature_image_url": "https://cdn.rext.test/hero.png"},
            )
        )

    assert publisher._upload_featured_image.await_count == 1
    publisher.client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_featured_image_already_in_the_sites_library_does_not_stop_the_publish():
    # Not example.com: the publisher drops images on such placeholder hosts before any upload.
    publisher = WordPressPublisher(
        site_url="https://blog.rext.test", username="user", app_password="pass"
    )
    hero = "https://blog.rext.test/wp-content/uploads/2026/07/hero.png"
    publisher._upload_featured_image = AsyncMock(
        side_effect=RextExternalServiceException(
            message="WordPress media API returned HTTP 403", service_name="WordPress"
        )
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201, json={"id": 92, "status": "publish", "title": "Own image", "featured_media": 0}
        )
    )

    await publisher.publish_post(
        ContentCreate(
            title="Own image",
            body_html=f'<img src="{hero}"><p>Text.</p>',
            images_data={"feature_image_url": hero},
        )
    )

    payload = publisher.client.post.await_args.kwargs["json"]
    assert payload["featured_media"] == 0
    assert hero in payload["content"]
    assert publisher._upload_featured_image.await_count == 1


def test_a_scheduled_publish_tells_the_person_which_image_and_what_to_do():
    from src.tasks.scheduled_tasks import _get_publish_failure_reason
    from src.web.wordpress import BodyImageUploadError

    error = BodyImageUploadError(
        "https://cdn.rext.test/images/second.png?X-Amz-Signature=secret-token",
        "WordPress media API returned HTTP 413",
    )

    notice = _get_publish_failure_reason(error)

    assert "second.png" in notice
    assert "Replace or remove it" in notice
    assert "secret-token" not in notice
    assert "HTTP 413" not in notice
    assert "HTTP 413" in error.message


@pytest.mark.asyncio
async def test_a_featured_image_outside_the_body_that_fails_is_left_out():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )
    publisher._upload_featured_image = AsyncMock(
        side_effect=RextExternalServiceException(
            message="Downloaded resource is not a valid image", service_name="WordPress"
        )
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201, json={"id": 91, "status": "publish", "title": "No hero", "featured_media": 0}
        )
    )

    result = await publisher.publish_post(
        ContentCreate(
            title="No hero",
            body_html="<p>Text only.</p>",
            images_data={"feature_image_url": "https://cdn.rext.test/hero.png"},
        )
    )

    assert result["post_id"] == 91
    assert publisher.client.post.await_args.kwargs["json"]["featured_media"] == 0


@pytest.mark.asyncio
async def test_post_must_confirm_featured_media_id():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )
    publisher._download_image = AsyncMock(
        return_value=httpx.Response(
            200,
            content=b"\x89PNG\r\n\x1a\nimage",
            headers={"content-type": "image/png"},
            request=httpx.Request("GET", "https://cdn.rext.test/image.png"),
        )
    )
    publisher.client.send = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"id": 42, "source_url": "https://example.com/uploads/image.png"},
        )
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"id": 99, "status": "publish", "featured_media": 0},
        )
    )
    publisher.client.get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"id": 99, "status": "publish", "featured_media": 0},
        )
    )

    with pytest.raises(RextExternalServiceException, match="did not confirm"):
        await publisher.publish_post(
            ContentCreate(
                title="Verify response",
                body_html='<img src="https://cdn.rext.test/image.png">',
            )
        )


@pytest.mark.asyncio
async def test_fetches_created_post_when_plugin_response_omits_featured_media():
    publisher = WordPressPublisher(
        site_url="https://example.com",
        api_endpoint="https://example.com/wp-json/rext-ai/v1",
        api_key="secret",
    )
    publisher._download_image = AsyncMock(
        return_value=httpx.Response(
            200,
            content=b"\x89PNG\r\n\x1a\nimage",
            headers={"content-type": "image/png"},
            request=httpx.Request("GET", "https://cdn.rext.test/image.png"),
        )
    )
    publisher.client.send = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"id": 89, "source_url": "https://example.com/uploads/image.png"},
        )
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"data": {"id": 101, "status": "publish", "url": "https://example.com/post"}},
        )
    )
    publisher.client.get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 101, "status": "publish", "featured_media": 89}},
        )
    )

    result = await publisher.publish_post(
        ContentCreate(
            title="Plugin response omits field",
            body_html='<img src="https://cdn.rext.test/image.png">',
        )
    )

    assert result["success"] is True
    assert result["post_id"] == 101
    assert result["featured_media"] == 89
    payload = publisher.client.post.await_args.kwargs["json"]
    assert payload["featured_media"] == 89
    assert payload["featured_image"] == 89
    # The created post is read back for its thumbnail (the categories are listed first).
    publisher.client.get.assert_any_await(
        "https://example.com/wp-json/rext-ai/v1/posts/101",
        timeout=30,
    )


@pytest.mark.asyncio
async def test_confirms_draft_featured_image_from_plugin_response_shape():
    publisher = WordPressPublisher(
        site_url="https://example.com",
        api_endpoint="https://example.com/wp-json/rext-ai/v1",
        api_key="secret",
    )
    publisher._download_image = AsyncMock(
        return_value=httpx.Response(
            200,
            content=b"\x89PNG\r\n\x1a\nimage",
            headers={"content-type": "image/png"},
            request=httpx.Request("GET", "https://cdn.rext.test/image.png"),
        )
    )
    publisher.client.send = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"id": 89, "source_url": "https://example.com/uploads/image.png"},
        )
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"data": {"id": 102, "status": "draft"}},
        )
    )
    publisher.client.get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "id": 102,
                    "status": "draft",
                    "featured_image": {
                        "id": 89,
                        "url": "https://example.com/uploads/image.png",
                    },
                },
            },
        )
    )

    result = await publisher.publish_post(
        ContentCreate(
            title="Draft plugin image",
            body_html='<img src="https://cdn.rext.test/image.png">',
        ),
        status="draft",
    )

    assert result["success"] is True
    assert result["status"] == "draft"
    assert result["featured_media"] == 89


def test_reads_plugin_category_term_ids():
    assert WordPressPublisher._taxonomy_ids(
        [
            {"term_id": 7, "name": "WordPress"},
            {"id": 9, "name": "SEO"},
            11,
        ]
    ) == {7, 9, 11}


@pytest.mark.asyncio
async def test_replaces_html_escaped_signed_image_url():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )
    signed_url = "https://cdn.rext.test/image.png?token=a&expires=123"
    publisher._download_image = AsyncMock(
        return_value=httpx.Response(
            200,
            content=b"\x89PNG\r\n\x1a\nimage",
            headers={"content-type": "image/png"},
            request=httpx.Request("GET", signed_url),
        )
    )
    publisher.client.send = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"id": 42, "source_url": "https://example.com/uploads/image.png"},
        )
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201,
            json={"id": 99, "status": "publish", "featured_media": 42},
        )
    )

    await publisher.publish_post(
        ContentCreate(
            title="Signed URL",
            body_html=('<img src="https://cdn.rext.test/image.png?token=a&amp;expires=123">'),
            images_data={"featured_image_url": signed_url},
        )
    )

    payload = publisher.client.post.await_args.kwargs["json"]
    assert payload["featured_media"] == 42
    # The inline copy, written with &amp;, is recognised as the featured image and dropped (the theme
    # shows the featured image), so no form of the signed address is left in the post.
    assert signed_url not in payload["content"]
    assert "token=a&amp;expires" not in payload["content"]
    assert "localhost" not in payload["content"]


@pytest.mark.asyncio
async def test_uses_existing_wordpress_category_by_exact_name():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )
    publisher.client.get = AsyncMock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 3, "name": "WordPress News"},
                {"id": 7, "name": "WordPress"},
            ],
        )
    )
    publisher.client.post = AsyncMock(
        return_value=httpx.Response(
            201,
            json={
                "id": 110,
                "status": "publish",
                "categories": [7],
            },
        )
    )

    result = await publisher.publish_post(
        ContentCreate(
            title="Category lookup",
            body_html="<p>Content</p>",
            category="WordPress",
        )
    )

    assert result["success"] is True
    # The categories are listed, then searched by name; the exact name wins over "WordPress News".
    publisher.client.get.assert_any_await(
        "https://example.com/wp-json/wp/v2/categories",
        params={"search": "WordPress", "per_page": 100},
        timeout=30,
    )
    payload = publisher.client.post.await_args.kwargs["json"]
    assert payload["categories"] == [7]


@pytest.mark.asyncio
async def test_creates_missing_wordpress_category_and_assigns_its_id():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="user", app_password="pass"
    )
    publisher.client.get = AsyncMock(return_value=httpx.Response(200, json=[]))
    publisher.client.post = AsyncMock(
        side_effect=[
            httpx.Response(201, json={"id": 12, "name": "WordPress"}),
            httpx.Response(
                201,
                json={"id": 111, "status": "publish", "categories": [12]},
            ),
        ]
    )

    await publisher.publish_post(
        ContentCreate(
            title="Category creation",
            body_html="<p>Content</p>",
            category="WordPress",
        )
    )

    create_call, publish_call = publisher.client.post.await_args_list
    assert create_call.args[0] == "https://example.com/wp-json/wp/v2/categories"
    assert create_call.kwargs["json"] == {"name": "WordPress"}
    assert publish_call.kwargs["json"]["categories"] == [12]
