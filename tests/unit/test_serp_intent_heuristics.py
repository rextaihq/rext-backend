import pytest

from src.flow.engines.serp.serp_intent_heuristics import (
    filter_paa_for_intent,
    filter_related_for_intent,
)


def test_paa_commercial_keeps_best_tools():
    assert filter_paa_for_intent(
        "What are the best SEO tools in 2026?",
        "commercial",
        "best seo tools",
    )


def test_paa_commercial_drops_pure_definition():
    assert not filter_paa_for_intent(
        "What is search engine optimization?",
        "commercial",
        "best seo tools",
    )


def test_related_overlap_query():
    assert filter_related_for_intent(
        "best seo tools free",
        "commercial",
        "best seo tools",
    )
