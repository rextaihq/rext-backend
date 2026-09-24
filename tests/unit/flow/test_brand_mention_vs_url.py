"""Regression tests: a brand name inside a URL is not a brand mention.

The reported shape, found by running all 34 content types through the
validation gate with a compliant article:

A workspace's approved internal links point at the workspace's OWN site, which
is the promoted brand's site — so on almost every promoted article the brand
name appears inside an ordinary internal-link URL (`https://rankwell.io/blog/…`)
BEFORE it appears in prose. Four brand checks located the mention with a raw,
unbounded `str.find` / substring test, so they graded that URL instead of the
real mention:

* `check_brand_url_accuracy` read the internal link's URL as the brand's own
  hyperlink and reported a correctly-linked mention as pointing at the wrong
  URL. That is blocking, unfixable by repair (nothing is actually wrong), and
  therefore burned both repair attempts on every affected article.
* `check_brand_presence` (and humanization's post-rewrite brand-survival test)
  passed on an article whose approved mention had been deleted, because the
  name survived inside the link URL.

`_brand_occurrences` / `_normalize_for_mentions` already existed for exactly
this reason and `check_brand_placement_policy` already used them; these checks
were simply never migrated onto them.
"""

from __future__ import annotations

import pytest

from src.flow.engines.content.generation.humanize_content import (
    _mention_present as humanize_mention_present,
)
from src.flow.engines.content.generation.validation import (
    brand_mention_index,
    check_brand_placement,
    check_brand_presence,
    check_brand_url_accuracy,
)

BRAND_URL = "https://rankwell.io"
INTERNAL_URL = "https://rankwell.io/blog/keyword-clustering-guide"

SPEC = {
    "brand_context": {
        "brand_name": "Rankwell",
        "brand_url": BRAND_URL,
        "about": "Rankwell turns a keyword into a brief, a draft and a published post.",
        "selling_position": "For lean in-house teams that need a full content pipeline.",
    }
}

# An internal link on the brand's own domain, EARLIER in the article than the
# brand mention itself — the ordering that exposed the defect.
_INTRO_WITH_SAME_SITE_LINK = (
    "Teams lose the most time before anyone writes. See "
    f"[our guide to keyword clustering]({INTERNAL_URL}) for the planning step that "
    "removes most of it."
)
_CORRECT_BRAND_SENTENCE = (
    f"A platform such as [Rankwell]({BRAND_URL}) turns a keyword into a researched brief, "
    "drafts the article from it and holds it at an editor approval step before publishing."
)


def _article(body: str, intro: str = _INTRO_WITH_SAME_SITE_LINK) -> dict:
    return {"introduction": intro, "body_markdown": body}


def test_correctly_linked_brand_is_not_blamed_for_an_earlier_same_site_link():
    result = check_brand_url_accuracy(_article(_CORRECT_BRAND_SENTENCE), SPEC)
    assert result["passed"], result["detail"]


@pytest.mark.parametrize(
    "body, expect_detail",
    [
        (
            "A platform such as [Rankwell](https://some-other-site.example/tool) turns a "
            "keyword into a brief for a lean team.",
            "https://some-other-site.example/tool",
        ),
        (
            "A platform such as Rankwell turns a keyword into a brief for a lean team.",
            "no hyperlink",
        ),
    ],
)
def test_real_brand_url_failures_still_block(body, expect_detail):
    result = check_brand_url_accuracy(_article(body), SPEC)
    assert not result["passed"]
    assert result["severity"] == "blocking"
    assert expect_detail in result["detail"]


def test_brand_surviving_only_inside_a_url_is_reported_as_missing():
    """The false NEGATIVE half: the mention was deleted, the domain remained."""
    article = _article("The planning step is what most teams skip.")
    presence = check_brand_presence(article, SPEC)
    assert not presence["passed"]
    assert presence["severity"] == "blocking"
    # …and the placement check keeps deferring to it rather than disagreeing.
    assert check_brand_placement(article, SPEC)["passed"]


def test_humanization_sees_the_same_deleted_mention():
    """Humanization's own survival test must not be satisfied by the URL either,
    or no post-humanize brand repair is ever triggered for a dropped mention."""
    assert not humanize_mention_present(_INTRO_WITH_SAME_SITE_LINK, "Rankwell")
    assert humanize_mention_present(_CORRECT_BRAND_SENTENCE, "Rankwell")


@pytest.mark.parametrize(
    "text, brand, expected",
    [
        # Inside a markdown link target — not reader-visible.
        (f"[the guide]({INTERNAL_URL})", "Rankwell", None),
        # Inside a bare URL — likewise.
        (f"See {INTERNAL_URL} for more.", "Rankwell", None),
        # Anchor text IS reader-visible.
        (f"[Rankwell]({BRAND_URL}) does this.", "Rankwell", 1),
        # Boundary-anchored: a longer word that merely contains the name is not it.
        ("Rankwellness is a different company entirely.", "Rankwell", None),
        # Punctuation directly after the name is still a match.
        ("Rankwell's editor approval step.", "Rankwell", 0),
    ],
)
def test_brand_mention_index_reads_reader_visible_prose_only(text, brand, expected):
    assert brand_mention_index(text, brand) == expected
