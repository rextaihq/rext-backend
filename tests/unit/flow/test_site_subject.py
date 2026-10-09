"""An article's reader is the site's customer only where the subject is the site's own
(revnix/rext-control#816).

A workspace's profile says whom the site serves and what it knows, and both shaped every
article on any keyword: for a site that sells an AI writing tool, an article on standing desks
told its reader to "stand during a site-crawl review". Where the keyword and the title share
no word with anything the profile says, the customers and the company's expertise are left
out of the outline's and the writer's instructions; in between, both are asked to judge.
"""

import pytest

from src.flow.engines.content.generation.article_voice import (
    article_voice,
    format_voice_for_rewrite,
    format_voice_for_writer,
)
from src.flow.engines.content.generation.outline import _format_reader_and_offer
from src.flow.engines.content.generation.site_subject import (
    outside_the_sites_subject,
    subject_overlap,
    without_customers_and_expertise,
)
from src.flow.prompts.human.outline import get_outline_prompt

# The profile of the staging workspace the four launch-night articles were written in.
WRITING_TOOL = {
    "brand_name": "Rext AI",
    "about": (
        "Rext AI is a smart AI writing tool designed for agencies and niche site owners, "
        "focusing on generating human-like, SEO-optimized content."
    ),
    "selling_position": (
        "A specialized AI article writer that delivers high-quality, SEO-focused content "
        "quickly and efficiently."
    ),
    "customer_profile": (
        "Agencies, business owners, and marketing teams looking for efficient content "
        "creation solutions."
    ),
    "target_audience": ["Content Agencies", "Business Owners", "Marketing Teams"],
    "content_pillars": ["SEO Optimization", "Content Creation", "Keyword Research"],
}
GARDEN_APP = {
    "brand_name": "Fernhill Garden Planner",
    "about": (
        "Fernhill Garden Planner is a small app for home gardeners. It helps people plan "
        "vegetable beds, track sowing dates and rotate crops."
    ),
    "customer_profile": "Hobby gardeners in the UK who plan their vegetable gardens.",
    "target_audience": ["Home Gardeners"],
    "content_pillars": ["Garden Planning Tips", "Crop Rotation Strategies"],
}


@pytest.mark.parametrize(
    ("keyword", "title"),
    [
        ("benefits of standing desks", "Discover the Benefits of Standing Desks for Your Health"),
        ("compound interest", "Compound Interest Explained: How Your Savings Grow"),
        ("how to care for houseplants", "How to Care for Houseplants: A Beginner's Routine"),
        ("how to pull an espresso shot", "How to Pull an Espresso Shot at Home"),
        ("morning routine ideas for remote workers", "Morning Routine Ideas For Remote Workers"),
    ],
)
def test_a_keyword_that_shares_no_word_with_the_site_is_outside_its_subject(keyword, title):
    assert subject_overlap(WRITING_TOOL, keyword=keyword, title=title) == 0
    assert outside_the_sites_subject(WRITING_TOOL, keyword=keyword, title=title) is True


@pytest.mark.parametrize(
    ("profile", "keyword", "title"),
    [
        (
            WRITING_TOOL,
            "ai writing tools for small business",
            "AI Writing Tools for Small Business",
        ),
        (WRITING_TOOL, "seo content brief template", "An SEO Content Brief Template That Works"),
        # One word in common is enough to leave the judgement to the outline and the writer.
        (
            WRITING_TOOL,
            "email marketing tips for nonprofits",
            "Email Marketing Tips for Nonprofits",
        ),
        (GARDEN_APP, "how to plan a vegetable garden", "How To Plan A Vegetable Garden"),
        (GARDEN_APP, "crop rotation for beginners", "Crop Rotation for Beginners"),
    ],
)
def test_a_keyword_the_site_speaks_to_is_not(profile, keyword, title):
    assert subject_overlap(profile, keyword=keyword, title=title) > 0
    assert outside_the_sites_subject(profile, keyword=keyword, title=title) is False


def test_the_sites_own_name_does_not_make_a_subject_its_own():
    """A site is not about gardens because it is called a garden planner; it is because its
    profile says it helps gardeners plan."""
    named_only = {"brand_name": "Summit Desk", "about": "Summit Desk makes accounting software."}

    assert (
        outside_the_sites_subject(named_only, keyword="standing desk", title="Standing Desk")
        is True
    )
    assert outside_the_sites_subject(GARDEN_APP, keyword="garden planner", title="") is False


def test_nothing_to_compare_is_not_outside():
    assert subject_overlap({}, keyword="standing desks", title="Standing Desks") is None
    assert outside_the_sites_subject({}, keyword="standing desks", title="x") is False
    assert outside_the_sites_subject(None, keyword="standing desks", title="x") is False
    assert outside_the_sites_subject(WRITING_TOOL, keyword="", title=None) is False


# -- The outline ---------------------------------------------------------------------------


def test_the_outline_is_not_told_the_sites_customers_for_a_subject_outside_it():
    inside = _format_reader_and_offer(WRITING_TOOL)
    outside = _format_reader_and_offer(WRITING_TOOL, outside_the_subject=True)

    assert "Marketing Teams" in inside and inside.startswith("WHO THE SITE SERVES:\n")
    # The customers are gone, the reason is said, and what the brand offers stays (its
    # mention has its own rules).
    assert "Marketing Teams" not in outside and "Agencies" not in outside.split("WHAT THE BRAND")[0]
    assert outside.startswith("WHO THE SITE SERVES: left out.")
    assert "its customers are not this article's readers" in outside
    assert "WHAT THE BRAND OFFERS:" in outside


def test_the_outlines_reader_rule_asks_whether_the_subject_is_the_sites():
    human = get_outline_prompt().messages[-1].prompt.template

    assert "12. WRITE FOR THE PERSON SEARCHING THIS KEYWORD:" in human
    assert "AS THIS SITE'S CUSTOMER" not in human
    assert (
        "First decide whether the keyword's subject is one those customers come to this site for"
        in human
    )
    assert "no section, example or wording is aimed at the site's customers" in human
    assert "Never copy the site's customer list into `target_audience`" in human


# -- The writer and the rewrite ------------------------------------------------------------


def test_the_writer_of_an_outside_subject_keeps_the_voice_and_is_told_nothing_of_the_customers():
    profile = {**WRITING_TOOL, "traits": ["direct", "practical"]}

    inside = article_voice("Warm and plain", profile)
    outside = article_voice("Warm and plain", without_customers_and_expertise(profile))

    told = format_voice_for_writer(outside)
    assert "direct, practical" in told
    for theirs in ("Agencies", "Marketing Teams", "SEO", "KNOWS AND OFFERS", "writes for"):
        assert theirs not in told, theirs
    assert "Written for" not in format_voice_for_rewrite(outside)
    # Inside the site's subject nothing is withheld, and the block says what it is for.
    told = format_voice_for_writer(inside)
    assert "Who the brand writes for:" in told and "Marketing Teams" in told
    assert "where the article's subject is this company's own field" in told
    assert "bring in nothing of the company's customers or their work" in told
    assert without_customers_and_expertise(None) is None
