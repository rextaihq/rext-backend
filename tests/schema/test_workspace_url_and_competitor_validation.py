import pytest
from pydantic import ValidationError

from src.api.schema.knowledge_schema import BrandSchema
from src.api.schema.workspace_schema import (
    BrandVoiceSchema,
    WorkspaceSchema,
    WorkspaceUpdateSchema,
)


def test_workspace_url_normalization_and_validation():
    # Auto-prefixes https:// if missing
    ws = WorkspaceSchema(name="Test", url="example.com")
    assert str(ws.url) == "https://example.com/"

    # Valid https URL
    ws2 = WorkspaceSchema(name="Test 2", url="https://subdomain.acme-corp.com/path")
    assert str(ws2.url) == "https://subdomain.acme-corp.com/path"

    # WorkspaceUpdateSchema optional URL normalization
    update_data = WorkspaceUpdateSchema(url="my-brand.io")
    assert str(update_data.url) == "https://my-brand.io/"


def test_workspace_url_rejection_forbidden_hosts():
    # Localhost
    with pytest.raises(ValidationError) as exc_info:
        WorkspaceSchema(name="Bad", url="http://localhost:8000")
    assert "Localhost and private IP addresses are not permitted" in str(exc_info.value)

    # 127.0.0.1
    with pytest.raises(ValidationError) as exc_info:
        WorkspaceSchema(name="Bad 2", url="https://127.0.0.1/admin")
    assert "Localhost and private IP addresses are not permitted" in str(exc_info.value)

    # Private IP 192.168.1.1
    with pytest.raises(ValidationError) as exc_info:
        WorkspaceSchema(name="Bad 3", url="https://192.168.1.10")
    assert "Localhost and private IP addresses are not permitted" in str(exc_info.value)

    # Missing TLD
    with pytest.raises(ValidationError) as exc_info:
        WorkspaceSchema(name="Bad 4", url="https://invalidhost")
    assert "URL must contain a valid domain with a top-level domain" in str(exc_info.value)


def test_brand_voice_competitor_validation_and_sanitization():
    # Test valid competitors, HTML tag stripping, URL domain cleaning, and deduplication
    input_competitors = [
        "  Stripe  ",
        "https://www.shopify.com/about",
        "<script>alert('xss')</script>Adyen",
        "stripe",  # Duplicate case variation should be removed
        "Square",
    ]

    bv = BrandVoiceSchema(competitors=input_competitors)
    assert bv.competitors == ["Stripe", "shopify.com", "Adyen", "Square"]

    bs = BrandSchema(competitors=input_competitors)
    assert bs.competitors == ["Stripe", "shopify.com", "Adyen", "Square"]


def test_brand_voice_competitor_max_limit_rejection():
    too_many = [f"Competitor_{i}" for i in range(25)]
    with pytest.raises(ValidationError) as exc_info:
        BrandVoiceSchema(competitors=too_many)
    assert "Maximum of 20 competitors allowed" in str(exc_info.value)
