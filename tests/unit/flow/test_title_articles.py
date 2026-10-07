"""'a' or 'an' by the next word's sound in an English title (G65)."""

import pytest

from src.flow.engines.content.generation.title_articles import (
    fix_indefinite_articles,
    fix_title_articles,
)
from src.flow.model.structure.topics import SEOTopics


@pytest.mark.parametrize(
    ("written", "fixed"),
    [
        # Staging, 2026-10-07: the recommended title.
        (
            "How to Create a Effective Content Brief Template for 2026",
            "How to Create an Effective Content Brief Template for 2026",
        ),
        ("An Guide to Content Briefs for Small Teams", "A Guide to Content Briefs for Small Teams"),
        ("How to write a SEO brief that ranks", "How to write an SEO brief that ranks"),
        ("An Unique Way to Plan Content for the Year", "A Unique Way to Plan Content for the Year"),
        ("Why You Need a Hour-by-Hour Content Plan", "Why You Need an Hour-by-Hour Content Plan"),
        ("A Honest Review of the Best SEO Tools", "An Honest Review of the Best SEO Tools"),
        ("An One-Page SEO Checklist for Your Site", "A One-Page SEO Checklist for Your Site"),
        ("How to build an URL structure that ranks", "How to build a URL structure that ranks"),
        # No word from the short English list, and all ASCII: English.
        (
            "A Effective Content Strategy Blueprint: Marketing Plan",
            "An Effective Content Strategy Blueprint: Marketing Plan",
        ),
        ("A Unidentified Risk in Your Content Plan", "An Unidentified Risk in Your Content Plan"),
        (
            "A Éclair Guide for Bakers and Pastry Shops",
            "An Éclair Guide for Bakers and Pastry Shops",
        ),
        # After an opening quote, its quote kept.
        (
            "How to Build “a Effective Content Strategy” for Growth",
            "How to Build “an Effective Content Strategy” for Growth",
        ),
        (
            "SEO Basics: A Effective Plan for Small Teams",
            "SEO Basics: An Effective Plan for Small Teams",
        ),
        ("A 8-Step Guide to Better Content Briefs", "An 8-Step Guide to Better Content Briefs"),
        ("A 11-Point Checklist for Your Blog Posts", "An 11-Point Checklist for Your Blog Posts"),
        (
            "How to Run a A/B Test on Your Landing Pages",
            "How to Run an A/B Test on Your Landing Pages",
        ),
        (
            "How to Write a “Evergreen” Post for Your Blog",
            "How to Write an “Evergreen” Post for Your Blog",
        ),
        ("Hiring a LLM Engineer: What to Look For", "Hiring an LLM Engineer: What to Look For"),
        ("How to Start an Podcast on YouTube", "How to Start a Podcast on YouTube"),
    ],
)
def test_the_article_follows_the_next_words_sound(written, fixed):
    assert fix_indefinite_articles(written) == fixed


@pytest.mark.parametrize(
    "title",
    [
        "How to Create an Effective Content Brief Template for 2026",
        "A Unique Way to Plan Content for the Year",
        "A European Guide to SEO for Small Teams",
        "A 2026 Guide to Content Briefs for Beginners",
        "A 100-Day Content Plan for Your Blog",
        "A UX Audit Checklist for Your Website",
        "An SEO Brief Template for Your Team",
        "How to Uninstall a Plugin: An Uninstall Checklist",
        "A Unidirectional Data Flow Architecture for React Apps",
        "A Unimodal Analytics Model for Modern Marketing Teams",
        "An Éclair Guide for Bakers and Pastry Shops Everywhere",
        # A capital "A" or "An" inside a title may be a letter: left as written.
        "Point A Explained: What It Means for Your Marketing Plan",
        "How to Build An URL Structure That Ranks",
        # A letter, not an article.
        "Vitamin A Explained: What It Does for You",
        "Plan A or Plan B: How to Choose for Your Blog",
        "The A to Z of SEO for Small Business Owners",
        "Grade A Eggs: How to Choose the Best Ones",
        "Why A Is Better Than B for Your Content",
        # Said both ways, or as a word: left as written.
        "A FAQ Page Template for Your SaaS Website",
        "An FAQ Page Template for Your SaaS Website",
        "A SQL Guide for Marketers and Analysts",
        "A REST API Guide for Developers and Product Teams",
        "A RADAR Chart Guide for Product Teams",
        # A four-digit 11… or 18… may be a year: "an 1800s", "a 1,800".
        "An 1800s Fashion Guide for Historical Costume Designers",
        "A 1800s Fashion Guide for Historical Costume Designers",
        "A SaaS Marketing Plan for the Year Ahead",
        # Not a letter or a digit next.
        "How to Plan a $500 Content Budget for Your Team",
    ],
)
def test_what_is_right_or_unsure_is_left_alone(title):
    assert fix_indefinite_articles(title) == title


@pytest.mark.parametrize(
    "title",
    [
        "Cómo viajar a Europa con poco dinero",
        "Briefe an Kunden schreiben: Tipps und Vorlagen",
        "Guia para a estratégia de conteúdo em 2026",
        "Les meilleures astuces pour a écrire un blog",
    ],
)
def test_a_title_in_another_language_is_left_alone(title):
    assert fix_indefinite_articles(title) == title


def test_spacing_and_the_rest_of_the_title_are_kept():
    assert (
        fix_indefinite_articles("How to  Create a  Effective Brief:  Tips for 2026")
        == "How to  Create an  Effective Brief:  Tips for 2026"
    )


def _topics(*titles):
    return SEOTopics.model_validate(
        {
            "topics": [
                {"title": title, "recommended": index == 0} for index, title in enumerate(titles)
            ]
        }
    )


def test_every_title_is_put_right_but_never_at_the_keyphrases_cost():
    parsed = _topics(
        "How to Create a Effective Content Brief Template for 2026",
        "A Effective Guide to Content Brief Templates for 2026",
    )

    fixed = fix_title_articles(parsed, "content brief template")
    assert [topic.title for topic in fixed.topics] == [
        "How to Create an Effective Content Brief Template for 2026",
        "An Effective Guide to Content Brief Templates for 2026",
    ]

    # The user's own keyphrase says "a effective guide": its "a" stays, or the title would no
    # longer carry it. The title's other articles are still put right.
    kept = fix_title_articles(
        _topics("A Effective Guide: How to Write a SEO Brief for Teams"), "a effective guide"
    )
    assert kept.topics[0].title == "A Effective Guide: How to Write an SEO Brief for Teams"
