import pytest

from src.flow.model.structure.outlines import (
    BlogOutline,
    LandingPageOutline,
    get_outline_model,
    normalize_content_type as normalize_outline_content_type,
)
from src.flow.model.structure.contents import (
    normalize_content_type as normalize_generated_content_type,
)


@pytest.mark.unit
def test_normalize_content_type_kebab_case_passthrough():
    assert normalize_outline_content_type("landing-page") == "landing-page"


@pytest.mark.unit
def test_normalize_content_type_converts_spaces_and_underscores():
    assert normalize_outline_content_type("Landing Page") == "landing-page"
    assert normalize_outline_content_type("landing_page") == "landing-page"


@pytest.mark.unit
def test_normalize_content_type_article_aliases_to_blog():
    assert normalize_outline_content_type("article") == "blog"
    assert normalize_outline_content_type("ARTICLE") == "blog"
    assert normalize_outline_content_type("listicle") == "blog"


@pytest.mark.unit
def test_get_outline_model_selects_correct_outline_schema():
    assert get_outline_model("Landing Page") is LandingPageOutline
    assert get_outline_model("landing_page") is LandingPageOutline
    assert get_outline_model("blog") is BlogOutline
    # Unknown types fall back to BlogOutline (safe default)
    assert get_outline_model("some-new-type") is BlogOutline


@pytest.mark.unit
def test_generated_content_normalize_matches_outline_normalize():
    # Keep outline/content generation aligned on canonical keys
    assert normalize_generated_content_type("Landing Page") == "landing-page"
    assert normalize_generated_content_type("landing_page") == "landing-page"
    assert normalize_generated_content_type("article") == "blog"

