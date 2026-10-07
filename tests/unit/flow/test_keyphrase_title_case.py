"""Titles write the focus keyphrase in the title's own case (G49, #463).

The model copied the user's lowercase keyphrase into Title Case titles: E6's real run on the
keyword "seo agency for small business" offered "Find the Best seo agency for small business in
2026" and three more like it. Matching ignores case, so the keyphrase is now written in each
title's case: capitalized in a Title Case title, acronyms in capitals, names as the batch writes
them. Only the letters' case changes, never a word, and the title stays valid.
"""

from unittest.mock import AsyncMock

import pytest

from src.flow.engines.content.generation import topic_generation as tg
from src.flow.engines.content.generation.seo_title_rules import (
    display_keyphrase,
    keyphrase_spellings,
    keyphrase_title,
    recase_keyphrase,
    repair_title,
    title_is_valid,
)
from src.flow.model.structure.topics import SEOTopic, SEOTopics

KEYPHRASE = "seo agency for small business"
# The five titles of E6's run on the local stack, 2026-10-06 (rext-control looks/app/255).
RECORDED = [
    "Find the Best seo agency for small business in 2026",
    "How to Choose the Right seo agency for small business",
    "Top Affordable seo agency for small business Options Today",
    "Must-Read Reviews of seo agency for small business Services",
    "SEO Agency for Small Business: Understanding Your Expenses",
]


@pytest.mark.asyncio
async def test_the_recorded_titles_write_the_keyphrase_in_their_case():
    model = AsyncMock()
    model.ainvoke.return_value = SEOTopics(
        topics=[SEOTopic(title=t, recommended=(i == 0)) for i, t in enumerate(RECORDED)]
    )

    result = await tg._generate_and_validate_topics(
        model=model, messages=[], query=KEYPHRASE, keyphrase=KEYPHRASE
    )

    assert [topic.title for topic in result.topics] == [
        "Find the Best SEO Agency for Small Business in 2026",
        "How to Choose the Right SEO Agency for Small Business",
        "Top Affordable SEO Agency for Small Business Options Today",
        "Must-Read Reviews of SEO Agency for Small Business Services",
        "SEO Agency for Small Business: Understanding Your Expenses",
    ]
    for topic, recorded in zip(result.topics, RECORDED):
        assert len(topic.title) == len(recorded)
        assert title_is_valid(topic.title, KEYPHRASE)


@pytest.mark.asyncio
async def test_the_article_before_a_recased_keyphrase_follows_its_new_case():
    """The model copies "seo" in lowercase and writes "a" or "an" before it: the keyphrase is
    recased first, so the article is judged by "SEO" (G49 with G65)."""
    model = AsyncMock()
    model.ainvoke.return_value = SEOTopics(
        topics=[
            SEOTopic(title="How to Choose a seo agency for small business Today", recommended=True),
            SEOTopic(title="Why Hiring an seo agency for small business Pays Off"),
        ]
    )

    result = await tg._generate_and_validate_topics(
        model=model, messages=[], query=KEYPHRASE, keyphrase=KEYPHRASE
    )

    assert [topic.title for topic in result.topics] == [
        "How to Choose an SEO Agency for Small Business Today",
        "Why Hiring an SEO Agency for Small Business Pays Off",
    ]


def test_the_last_article_pass_keeps_a_title_valid():
    """After the last recasing the article is put right only where the title stays within its
    limits: nothing checks the titles after that."""
    at_the_limit = "Why Every Local Store Needs a SEO Agency for Small Business"
    assert title_is_valid(at_the_limit, KEYPHRASE)
    assert not title_is_valid(at_the_limit.replace(" a SEO", " an SEO"), KEYPHRASE)
    roomy = "How to Hire a SEO Agency for Small Business in 2026"
    topics = SEOTopics(topics=[SEOTopic(title=at_the_limit), SEOTopic(title=roomy)])

    tg._fix_articles_keeping_valid(topics, KEYPHRASE)

    assert [topic.title for topic in topics.topics] == [
        at_the_limit,
        "How to Hire an SEO Agency for Small Business in 2026",
    ]


def test_a_sentence_case_title_changes_only_acronyms_names_and_its_opening():
    assert recase_keyphrase("Why every seo agency for small business needs a plan", KEYPHRASE) == (
        "Why every SEO agency for small business needs a plan"
    )
    assert recase_keyphrase("seo agency for small business: what to expect in 2026", KEYPHRASE) == (
        "SEO agency for small business: what to expect in 2026"
    )
    # A name another title writes with a capital, mid-sentence, keeps it.
    spellings = keyphrase_spellings(
        ["Where to find coffee shops in London this year"], "coffee shops in london"
    )
    assert recase_keyphrase(
        "Best coffee shops in london for remote work in 2026", "coffee shops in london", spellings
    ) == ("Best coffee shops in London for remote work in 2026")


def test_names_in_a_sentence_case_title_dont_make_it_title_case():
    title = "Why seo tools work with Google, Microsoft, and Apple today"
    assert recase_keyphrase(title, "seo tools") == (
        "Why SEO tools work with Google, Microsoft, and Apple today"
    )


def test_the_users_own_capitals_and_the_models_own_casing_are_kept():
    # Typed with capitals: those stay, and the rest follows the title.
    assert recase_keyphrase("Find the Best SEO agency in London for 2026", "SEO agency") == (
        "Find the Best SEO Agency in London for 2026"
    )
    # Written another way by the model: left as it wrote it.
    assert recase_keyphrase("Find the Best Seo-Agency Partners for 2026", KEYPHRASE) == (
        "Find the Best Seo-Agency Partners for 2026"
    )


def test_acronyms_and_title_case_short_words():
    assert display_keyphrase("seo agency") == "SEO Agency"
    assert display_keyphrase("kpis for saas startups") == "KPIs for SaaS Startups"
    assert display_keyphrase("best crm for b2b") == "Best CRM for B2B"
    assert display_keyphrase("what it costs") == "What It Costs"  # "it" is a word, not IT


def test_each_part_of_a_joined_word_is_cased():
    assert recase_keyphrase(
        "The Complete Guide to seo-friendly content for Small Business Teams",
        "seo-friendly content",
    ) == ("The Complete Guide to SEO-Friendly Content for Small Business Teams")
    assert recase_keyphrase(
        "Why every team needs seo-friendly content in their plan", "seo-friendly content"
    ) == ("Why every team needs SEO-friendly content in their plan")
    assert display_keyphrase("ai-powered tools") == "AI-Powered Tools"
    assert display_keyphrase("seo's benefits") == "SEO's Benefits"
    assert display_keyphrase("seo–friendly tools") == "SEO–Friendly Tools"
    assert display_keyphrase("don't skip seo") == "Don't Skip SEO"
    assert display_keyphrase("step-by-step seo guide") == "Step-by-Step SEO Guide"


def test_a_keyphrase_written_against_chinese_characters_is_recased():
    """Matching takes "seo" in "最佳seo工具" as a word, so the recase does too."""
    assert recase_keyphrase("最佳seo工具推荐: Complete Guide for Small Business Teams", "seo") == (
        "最佳SEO工具推荐: Complete Guide for Small Business Teams"
    )


def test_the_users_capitals_belong_to_the_word_they_typed():
    """The user typed the acronym "IT" and the word "it": each keeps its own case."""
    assert display_keyphrase("what it costs for IT teams") == "What It Costs for IT Teams"
    assert display_keyphrase("how US taxes affect us abroad") == "How US Taxes Affect Us Abroad"


def test_the_repairs_keyphrase_lead_and_the_fallback_title_use_it():
    assert repair_title("The complete guide to hiring the right partner", "seo agency") == (
        "SEO Agency: The complete guide to hiring the right partner"
    )
    assert keyphrase_title(KEYPHRASE).startswith("SEO Agency for Small Business")


@pytest.mark.parametrize(
    ("title", "keyphrase"),
    [
        ("Die besten straße Ideen für kleine Teams im Jahr 2026", "straße"),  # ß has no 1:1 upper
        ("2026年最佳项目管理软件推荐", "项目管理软件"),  # no case
        ("أفضل برامج إدارة المشاريع للفرق الصغيرة", "برامج إدارة المشاريع"),
    ],
)
def test_a_title_without_a_case_to_follow_is_unchanged(title, keyphrase):
    assert recase_keyphrase(title, keyphrase) == title
