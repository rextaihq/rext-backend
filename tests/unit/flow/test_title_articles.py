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
        # "Ex-box", and a name said by its first letter.
        (
            "A Xbox Setup Guide for Parents and New Players",
            "An Xbox Setup Guide for Parents and New Players",
        ),
        (
            "A mRNA Vaccine Guide for Curious Readers and Students",
            "An mRNA Vaccine Guide for Curious Readers and Students",
        ),
        ("How to build an URL structure that ranks", "How to build a URL structure that ranks"),
        # No word from the short English list, and all ASCII: English.
        (
            "A Effective Content Strategy Blueprint: Marketing Plan",
            "An Effective Content Strategy Blueprint: Marketing Plan",
        ),
        ("A Unidentified Risk in Your Content Plan", "An Unidentified Risk in Your Content Plan"),
        ("A Unindexed Page Guide for SEO Teams", "An Unindexed Page Guide for SEO Teams"),
        # A single letter by its name.
        (
            "A X-Ray Guide for Medical Content Teams and Writers",
            "An X-Ray Guide for Medical Content Teams and Writers",
        ),
        (
            "An U-Turn Strategy for Content Marketing Teams Today",
            "A U-Turn Strategy for Content Marketing Teams Today",
        ),
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
        (
            "A Unitemized Expense Guide for Small Teams",
            "An Unitemized Expense Guide for Small Teams",
        ),
        ("An Utensil Guide for First-Time Home Cooks", "A Utensil Guide for First-Time Home Cooks"),
        (
            "A Unaware Team's Guide to Content Planning",
            "An Unaware Team's Guide to Content Planning",
        ),
        ("A Update Guide for Your Content Plan", "An Update Guide for Your Content Plan"),
        ("An URL's Role in SEO: A Guide for Teams", "A URL's Role in SEO: A Guide for Teams"),
        ("A M2 MacBook Guide for Content Teams", "An M2 MacBook Guide for Content Teams"),
        ("How to Write a H1 Heading for Your Blog", "How to Write an H1 Heading for Your Blog"),
        ("An ONE-PAGE SEO Checklist for Small Teams", "A ONE-PAGE SEO Checklist for Small Teams"),
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
        # An all-caps word read as a word, and an acronym's possessive or plural.
        "A ONE-PAGE SEO Checklist for Small Business Websites",
        "A EURO Currency Guide for Small Business Owners in Europe",
        "A EUROPEAN Guide to SEO for Small Teams",
        "An EU Guide to Content Rules for Small Teams",
        "A URL's Role in SEO: A Guide for Content Marketing Teams",
        "An API's Role in SEO: A Guide for Content Teams",
        "An SEO Brief Template for Your Team",
        "How to Uninstall a Plugin: An Uninstall Checklist",
        "A Unidirectional Data Flow Architecture for React Apps",
        "A Unimodal Analytics Model for Modern Marketing Teams",
        "An Unitemized Expense Guide for Small Business Tax Teams",
        "A Utensil Guide for First-Time Home Cooks and Bakers",
        # "u", one consonant, a vowel: unsure.
        "An Uber Guide for Small Business Teams",
        "A Ouija Board Guide for Paranormal Content Creators",
        # "Euler" is "oiler": not the "you" of "European".
        "An Euler Diagram Guide for Content Strategy Teams Today",
        "A Euler Diagram Guide for Content Strategy Teams Today",
        "AN EULER DIAGRAM GUIDE FOR CONTENT STRATEGY TEAMS",
        # A vowel letter that says "w" or "you" in a borrowed word or a name, in capitals too.
        "A OUIJA Board Guide for Paranormal Content Creators",
        "A Oaxaca Travel Guide for First-Time Visitors to Mexico",
        "A Ewing Sarcoma Guide for Patients and Their Families",
        "An Ewok Costume Guide for Star Wars Fans and Cosplayers",
        # "You-nary", and a name said as a word.
        "A Unary Operator Guide for Python Developers and Students",
        "A Unesco Heritage Site Guide for Curious Travelers",
        # Only the "wun" words take "a": "oneiric" and "onerous" start with a vowel sound.
        "An Oneiric Art Guide for Creative Content Teams Today",
        "An Onerous Contract Guide for Small Business Owners",
        "A Oneness Meditation Guide for Complete Beginners",
        # "An" before an h word is a silent h or a dialect more often than a mistake.
        "An Hors d'Oeuvre Guide for Caterers and Event Planners",
        "A Hors d'Oeuvre Guide for Caterers and Event Planners",
        "An Hotel Booking Guide for Budget Travelers in Europe",
        # An x word it doesn't know, and y before a consonant: the sound isn't clear.
        "A Xylophone Buying Guide for Parents and Music Teachers",
        "A Xhosa Language Guide for South African Travelers",
        # "Unit" is "you-nit" only in its own words; "u" and a vowel or y may say "w".
        "An Unitalicized Text Guide for Accessible Content Teams",
        "A Uyghur Culture Guide for Global Content Creators Today",
        "A Uighur Culture Guide for Global Content Creators Today",
        # A leading zero is "oh" or "zero".
        "An '08 Model Buying Guide for Used Car Shoppers Today",
        "An Yves Saint Laurent Bag Guide for First-Time Buyers",
        # A small letter, then a capital: said by the letter's name.
        "An mRNA Vaccine Guide for Curious Readers and Students",
        "A pH Testing Guide for Home Gardeners and Pool Owners",
        "An Xbox Setup Guide for Parents and New Players",
        "An M2 MacBook Guide for Creative Content Teams Today",
        "A B2B Content Plan for Small Teams",
        "A Uber Guide for Small Business Teams",
        "An Unindexed Page Guide for SEO Teams and Site Owners",
        # A "uni" word it doesn't know: unsure.
        "A Unigram Model Guide for Search Teams",
        "An Unigram Model Guide for Search Teams",
        # Said either way by dialect.
        "An Herb Gardening Guide for First-Time Home Growers",
        "A Herb Gardening Guide for First-Time Home Growers",
        # A digit that isn't 0-9: unsure, and no error.
        "A ①-Step Guide to Better Content Briefs",
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
        "Marketing a Efektywna Strategia SEO dla Polskich Firm",
        "Ideas a Evitar: Plan Marketing Digital SEO Profesional",
        # ASCII, but no English word: not taken for English.
        "Marketing a Efektywna Strategia SEO Polskich Firm",
        # A word English shares with the language ("in", "guide", "complete") proves nothing alone.
        "Strategie a Impatto nel Marketing Digitale in Italia",
        "Strategie a Impatto: Marketing Digitale in Italia",
        "Guide a Impatto: Marketing Digitale SEO Avanzato",
        "Strategie a Impatto in Italia: Best Marketing Digitale",
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


def test_two_options_never_become_the_same_title():
    """Options that differed only by an article stay distinct: the second keeps its wording."""
    fixed = fix_title_articles(
        _topics(
            "An Effective Content Strategy Guide for Small Business",
            "A Effective Content Strategy Guide for Small Business",
        ),
        "content strategy",
    )
    titles = [topic.title for topic in fixed.topics]
    assert len(set(titles)) == 2
    assert titles[0] == "An Effective Content Strategy Guide for Small Business"
