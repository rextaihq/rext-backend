import pytest


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("how to guide", "how-to-guide"),
        ("How-To-Guide", "how-to-guide"),
        ("explainer", "explainer"),
        ("article", "blog"),
        ("comparison", "comparison"),
        ("comarision", "comparison"),
        ("landing page", "landing-page"),
        ("landingpage", "landing-page"),
        ("unknown-type", ""),
    ],
)
def test_normalize_content_type_aliases(raw, expected):
    from src.flow.prompts.human.outline import normalize_content_type

    assert normalize_content_type(raw) == expected
