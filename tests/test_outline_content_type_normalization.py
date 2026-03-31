import pytest


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("how to guide", "how_to_guide"),
        ("How-To-Guide", "how_to_guide"),
        ("explainer", "explanatory_article"),
        ("article", "explanatory_article"),
        ("comparison", "product_comparison"),
        ("comarision", "product_comparison"),
        ("landing page", "landing_page"),
        ("landingpage", "landing_page"),
    ],
)
def test_normalize_content_type_aliases(raw, expected):
    from src.flow.prompts.human.outline import normalize_content_type

    assert normalize_content_type(raw) == expected

