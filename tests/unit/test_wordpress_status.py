import pytest
from pydantic import ValidationError

from src.api.schema.content_schema import PublishToSiteRequest
from src.utils.wordpress_status import (
    content_status_for_wordpress_status,
    normalize_wordpress_post_status,
)


@pytest.mark.parametrize("status", ["publish", "draft", "pending"])
def test_publish_request_preserves_selectable_wordpress_status(status):
    assert PublishToSiteRequest(status=status).status == status


def test_publish_request_maps_review_label_to_pending():
    assert PublishToSiteRequest(status="review").status == "pending"


def test_publish_request_keeps_existing_future_and_private_statuses():
    assert PublishToSiteRequest(status="future").status == "future"
    assert PublishToSiteRequest(status="private").status == "private"


def test_publish_request_rejects_unknown_wordpress_status():
    with pytest.raises(ValidationError, match="Unsupported WordPress post status"):
        PublishToSiteRequest(status="invalid")


@pytest.mark.parametrize(
    ("wordpress_status", "content_status"),
    [
        ("publish", "published"),
        ("draft", "draft"),
        ("pending", "review"),
        ("future", "scheduled"),
    ],
)
def test_wordpress_status_maps_to_internal_content_status(
    wordpress_status,
    content_status,
):
    assert content_status_for_wordpress_status(wordpress_status) == content_status


def test_missing_wordpress_status_preserves_existing_publish_default():
    assert normalize_wordpress_post_status(None) == "publish"
