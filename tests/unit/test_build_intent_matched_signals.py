import pytest

from src.flow.engines.serp.competitor import build_intent_matched_signals_from_competitors


class _FakeResult:
    def __init__(self, intent: str):
        self.intent = intent


def test_signals_only_from_matching_competitors():
    domain_groups = {
        "a.com": {
            "top_result": {"title": "Best Tools A", "snippet": "snippet a"},
        },
        "b.com": {
            "top_result": {"title": "How SEO Works", "snippet": "snippet b"},
        },
    }
    results_map = {
        "a.com": _FakeResult("COMMERCIAL"),
        "b.com": _FakeResult("INFORMATIONAL"),
    }
    serp_normalized = {
        "normalize_results": [],
        "related_topics": ["best seo tools reddit"],
        "questions": ["What is SEO?"],
    }

    signals = build_intent_matched_signals_from_competitors(
        query="best seo tools",
        primary_intent="COMMERCIAL",
        domain_groups=domain_groups,
        results_map=results_map,
        serp_normalized=serp_normalized,
    )

    assert signals["primary_intent"] == "COMMERCIAL"
    assert signals["titles"] == ["Best Tools A"]
    assert "b.com" not in (signals.get("matched_domains") or [])
    assert "a.com" in signals["matched_domains"]
