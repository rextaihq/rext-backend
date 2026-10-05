"""The content-type and topic gates carry what the SERP shows.

The content-type gate gets the dominant format of the top ten, the People-Also-
Ask count and the AI Overview flag; the topic gate gets the top-ten titles.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.flow.engines.content.generation.content_type as content_type_module
import src.flow.engines.content.generation.topic_generation as topic_module
from src.flow.engines.serp.fetch_serp import _empty_serp_state, _parse_serp_response
from src.flow.engines.serp.normalization import normalize_serp_results
from src.flow.engines.serp.serp_evidence import (
    build_serp_evidence,
    build_serp_titles,
    classify_result_format,
)


@pytest.mark.parametrize(
    ("title", "url", "expected"),
    [
        ("10 Best Headless CMS Platforms for 2026", "https://a.test/best", "list"),
        ("Best Headless CMS for Small Business", "https://a.test/x", "list"),
        ("Top 7 CMS picks", "https://a.test/x", "list"),
        # titles from a live SERP ("best headless cms", 2026-10-05)
        ("Top Headless CMS Development Companies", "https://a.test/x", "list"),
        ("Headless CMS Agency: 10 Best Options in 2026 (+ How to ...", "https://a.test/x", "list"),
        ("9 Best Headless CMS Reviewed in 2026", "https://a.test/x", "list"),
        ("[AskJS] What headless CMS would you recommend for my ...", "https://a.test/x", None),
        ("Strapi vs Contentful: Which Is Right for You?", "https://a.test/x", "comparison"),
        ("Comparing headless CMS options", "https://a.test/x", "comparison"),
        ("12 Best Contentful Alternatives", "https://a.test/x", "alternatives"),
        ("How to Choose a Headless CMS", "https://a.test/x", "how-to"),
        ("Set up Strapi in 5 steps", "https://a.test/x", "how-to"),
        ("Storyblok Review 2026", "https://a.test/x", "review"),
        ("What Is a Headless CMS?", "https://a.test/x", "explainer"),
        ("Headless CMS explained", "https://a.test/x", "explainer"),
        ("The Complete Guide to Headless CMS", "https://a.test/x", "guide"),
        ("Strapi - Open source Node.js Headless CMS", "https://strapi.io/", "home-page"),
        ("Strapi - Open source Node.js Headless CMS", "https://strapi.io", "home-page"),
        ("Headless CMS for small business", "https://a.test/blog/post", None),
        ("", "", None),
    ],
)
def test_result_format(title, url, expected):
    assert classify_result_format(title, url) == expected


def _normalized(titles, questions=(), ai_overview=None):
    return {
        "normalize_results": [
            {
                "position": i + 1,
                "title": t,
                "url": f"https://site{i}.test/page",
                "domain": f"site{i}.test",
            }
            for i, t in enumerate(titles)
        ],
        "questions": list(questions),
        "features": {"people_also_ask": bool(questions), "ai_overview": ai_overview},
    }


def test_evidence_names_a_dominant_format():
    titles = ["10 best CMS", "Top 5 CMS", "Best CMS for teams", "How to pick a CMS"] + [
        f"CMS notes {i}" for i in range(8)
    ]
    evidence = build_serp_evidence(
        _normalized(titles, ["What is a CMS?", "what is a cms?", "Is Strapi free?"], True)
    )

    assert evidence["results"] == 10  # the top ten only
    assert evidence["dominant_format"] == {
        "format": "list",
        "count": 3,
        "label": "list posts",
        "content_types": ["best-tools", "product-roundup", "resource-list", "checklist"],
    }
    assert evidence["formats"] == {"list": 3, "how-to": 1}
    assert evidence["paa_count"] == 2  # repeated questions count once
    assert evidence["ai_overview"] is True


def test_no_dominant_format_without_a_pattern():
    evidence = build_serp_evidence(_normalized(["10 best CMS", "Top 5 CMS"] + ["Notes"] * 8))

    assert evidence["dominant_format"] is None
    assert evidence["formats"] == {"list": 2}


def test_a_small_serp_needs_three_of_a_kind():
    evidence = build_serp_evidence(_normalized(["10 best CMS", "Top 5 CMS"]))

    assert evidence["results"] == 2
    assert evidence["dominant_format"] is None


def test_a_tie_goes_to_the_higher_ranked_format():
    titles = ["How to a", "10 best b", "How to c", "Top 3 d", "How to e", "Best f"]

    assert build_serp_evidence(_normalized(titles))["dominant_format"]["format"] == "how-to"


def test_no_serp_gives_no_evidence_and_no_titles():
    for value in (None, {}, {"normalize_results": []}):
        assert build_serp_evidence(value) is None
        assert build_serp_titles(value) == []


def test_ai_overview_unknown_stays_unknown():
    normalized = _normalized(["a", "b", "c"])
    normalized["features"].pop("ai_overview")

    assert build_serp_evidence(normalized)["ai_overview"] is None


def test_titles_are_the_top_ten_with_their_format():
    titles = build_serp_titles(
        _normalized(["Strapi vs Contentful"] + [f"Post {i}" for i in range(12)])
    )

    assert len(titles) == 10
    assert titles[0] == {
        "position": 1,
        "title": "Strapi vs Contentful",
        "domain": "site0.test",
        "url": "https://site0.test/page",
        "format": "comparison",
    }


# --- the AI Overview flag, from DataForSEO to the normalised SERP --------------


def _serp(items):
    return {"tasks": [{"status_code": 20000, "data": {}, "result": [{"items": items}]}]}


ORGANIC = {"type": "organic", "title": "A", "url": "https://a.test/x", "rank_group": 1}


def test_parse_records_an_ai_overview_and_never_claims_absence():
    assert _parse_serp_response(_serp([{"type": "ai_overview"}, ORGANIC]))["ai_overview"] is True
    # Only cached AI Overviews come back without the paid async load, so a
    # missing item is "not seen", never "absent".
    assert _parse_serp_response(_serp([ORGANIC]))["ai_overview"] is None
    assert _parse_serp_response(_serp(None))["ai_overview"] is None
    no_result = {"tasks": [{"status_code": 20000, "result": []}]}
    assert _parse_serp_response(no_result)["ai_overview"] is None
    assert _empty_serp_state()["ai_overview"] is None


def test_normalised_features_carry_the_flag():
    state = {
        "serp_payload": {"query": "q"},
        "serp_result": {**_parse_serp_response(_serp([{"type": "ai_overview"}, ORGANIC]))},
    }

    result = normalize_serp_results(state, {}, runtime=SimpleNamespace(store=None))

    assert result["serp_normalized"]["features"]["ai_overview"] is True


# --- the gates -------------------------------------------------------------------


SERP_NORMALIZED = _normalized(
    ["10 best headless CMS", "Top 5 headless CMS", "Best CMS for small teams", "What is a CMS?"],
    ["What is a headless CMS?"],
    True,
)


def test_content_type_gate_carries_the_evidence(monkeypatch):
    payloads = []
    monkeypatch.setattr(
        content_type_module, "_recommend_content_type", lambda *_a: ("blog", "Because.")
    )
    monkeypatch.setattr(
        content_type_module, "interrupt", lambda payload: payloads.append(payload) or "blog"
    )
    state = {
        "serp_normalized": {**SERP_NORMALIZED, "query": "headless cms"},
        "seo_result": {"serp_backlinks": {"main_intent": "commercial"}},
    }

    content_type_module.content_type(state)

    evidence = payloads[0]["serp_evidence"]
    assert evidence["dominant_format"]["format"] == "list"
    assert evidence["paa_count"] == 1
    assert evidence["ai_overview"] is True
    assert payloads[0]["recommendation_reason"] == "Because."


def test_content_type_gate_without_a_serp_sends_none(monkeypatch):
    payloads = []
    monkeypatch.setattr(content_type_module, "_recommend_content_type", lambda *_a: (None, None))
    monkeypatch.setattr(
        content_type_module, "interrupt", lambda payload: payloads.append(payload) or "blog"
    )

    content_type_module.content_type({"serp_payload": {"query": "q", "is_library": True}})

    assert payloads[0]["serp_evidence"] is None


async def test_topic_gate_carries_the_serp_titles(monkeypatch):
    payloads = []
    monkeypatch.setattr(
        topic_module, "_generate_and_validate_topics", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        topic_module,
        "_extract_topics",
        lambda _r: (["Headless CMS for small teams"], "Headless CMS for small teams", "Clear."),
    )
    monkeypatch.setattr(
        topic_module,
        "interrupt",
        lambda payload: payloads.append(payload) or "Headless CMS for small teams",
    )
    state = {
        "serp_normalized": {**SERP_NORMALIZED, "query": "headless cms"},
        "serp_payload": {"query": "headless cms"},
        "content": {"content_type": "blog"},
    }

    await topic_module.topic_generation(state)

    titles = payloads[0]["serp_titles"]
    assert [t["title"] for t in titles] == [
        r["title"] for r in SERP_NORMALIZED["normalize_results"]
    ]
    assert titles[0]["format"] == "list"
