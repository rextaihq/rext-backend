"""The outline gate accepts the user's section order, headings and removals.

The rows the gate offers are the headings the article is written and checked
against; an approved order reaches the writer's plan and the validator's
expected headings unchanged.
"""

import copy

import pytest

import src.flow.engines.content.review.outline as review_module
from src.flow.engines.content.generation.content_generation import (
    _format_outline_for_generation,
)
from src.flow.engines.content.generation.outline_structure import (
    resolve_expected_headings,
    resolve_outline_structure,
)
from src.flow.engines.content.review.outline_edits import (
    MAX_ADDED_SECTIONS,
    addable_lists,
    apply_section_edits,
    editable_sections,
)


def _section(heading, level="H2"):
    return {
        "heading": heading,
        "heading_level": level,
        "description": f"What {heading} covers.",
        "key_points": [f"{heading} point one", f"{heading} point two"],
        "suggested_word_count": 200,
    }


def _blog_outline():
    return {
        "title": "Running shoes for beginners",
        "hero": {"headline": "Running shoes for beginners", "subheadline": "How to choose."},
        "structure": {
            "sections": [
                _section("Why the right shoe matters"),
                _section("Cushioning and support"),
                _section("Heel drop explained", "H3"),
                _section("How to get fitted"),
            ]
        },
        "faqs": {"faqs": [{"question": "How often should I replace them?", "answer": "Often."}]},
        "_render": {"blocks": []},
    }


BLOG_IDS = [f"structure.sections:{i}" for i in range(4)]


def _headings(outline, path=("structure", "sections")):
    node = outline
    for key in path:
        node = node[key]
    return [item["heading"] for item in node]


# --- what the gate offers ----------------------------------------------------


def test_gate_offers_each_body_section_with_a_stable_id():
    rows = editable_sections(_blog_outline(), "blog")

    assert [row["id"] for row in rows] == BLOG_IDS
    assert [row["heading"] for row in rows] == _headings(_blog_outline())
    assert {row["list"] for row in rows} == {"structure.sections"}
    assert [row["heading_level"] for row in rows] == ["H2", "H2", "H3", "H2"]


def test_hero_and_faqs_are_not_offered():
    rows = editable_sections(_blog_outline(), "blog")

    assert all(not row["id"].startswith(("hero", "faqs")) for row in rows)


def test_a_flat_sections_list_is_offered_too():
    outline = {"title": "T", "sections": [_section("One"), _section("Two")]}

    assert [row["id"] for row in editable_sections(outline, "blog")] == [
        "sections:0",
        "sections:1",
    ]


# --- what approval applies ---------------------------------------------------


def test_reorder_and_rename():
    outline = _blog_outline()
    before = copy.deepcopy(outline)
    rows = [
        {"id": BLOG_IDS[3], "heading": "Get fitted first"},
        {"id": BLOG_IDS[0]},
        {"id": BLOG_IDS[1], "heading": "  "},
        {"id": BLOG_IDS[2]},
    ]

    edited = apply_section_edits(outline, "blog", rows)

    assert _headings(edited) == [
        "Get fitted first",
        "Why the right shoe matters",
        "Cushioning and support",
        "Heel drop explained",
    ]
    # the rest of each section travels with its heading
    assert edited["structure"]["sections"][0]["key_points"][0] == "How to get fitted point one"
    assert outline == before  # the input is not changed
    assert edited["hero"] == outline["hero"] and edited["faqs"] == outline["faqs"]


def test_an_unnamed_section_is_removed():
    edited = apply_section_edits(
        _blog_outline(), "blog", [{"id": BLOG_IDS[0]}, {"id": BLOG_IDS[3]}]
    )

    assert _headings(edited) == ["Why the right shoe matters", "How to get fitted"]


def test_heading_level_can_change_and_a_leading_subsection_becomes_a_section():
    edited = apply_section_edits(
        _blog_outline(),
        "blog",
        [{"id": BLOG_IDS[2]}, {"id": BLOG_IDS[0], "heading_level": "H3"}, {"id": BLOG_IDS[1]}],
    )

    levels = [s["heading_level"] for s in edited["structure"]["sections"]]
    assert levels == ["H2", "H3", "H2"]


def test_bad_rows_change_nothing():
    outline = _blog_outline()
    for rows in (
        None,
        [],
        "approve",
        [{"id": "nowhere:0"}],
        [{"id": "structure.sections:9"}],
        [{"id": "structure.sections"}, {"heading": "no id"}, "row"],
        [{"id": "hero:0"}],
    ):
        assert _headings(apply_section_edits(outline, "blog", rows)) == _headings(outline)


def test_repeated_and_stale_ids_are_ignored():
    edited = apply_section_edits(
        _blog_outline(),
        "blog",
        [
            {"id": BLOG_IDS[1]},
            {"id": BLOG_IDS[1], "heading": "Second copy"},
            {"id": "structure.sections:7"},
            {"id": BLOG_IDS[0]},
        ],
    )

    assert _headings(edited) == ["Cushioning and support", "Why the right shoe matters"]


def test_a_flat_sections_list_is_reordered():
    outline = {"title": "T", "sections": [_section("One"), _section("Two"), _section("Three")]}

    edited = apply_section_edits(
        outline, "blog", [{"id": "sections:2"}, {"id": "sections:0"}, {"id": "sections:1"}]
    )

    assert _headings(edited, ("sections",)) == ["Three", "One", "Two"]


# --- the writer and the validator follow the approved order -------------------


def test_writer_plan_and_expected_headings_follow_the_order():
    rows = [
        {"id": BLOG_IDS[3], "heading": "Get fitted first"},
        {"id": BLOG_IDS[1]},
        {"id": BLOG_IDS[0]},
    ]
    edited = apply_section_edits(_blog_outline(), "blog", rows)

    expected = resolve_expected_headings(resolve_outline_structure(edited, "blog"))
    assert expected == ["Get fitted first", "Cushioning and support", "Why the right shoe matters"]

    plan = _format_outline_for_generation(edited, "blog")
    positions = [plan.index(heading) for heading in expected]
    assert positions == sorted(positions)
    assert "Heel drop explained" not in plan


# --- the gate ----------------------------------------------------------------


def _approve(monkeypatch, response):
    payloads = []

    def _interrupt(payload):
        payloads.append(payload)
        return response

    monkeypatch.setattr(review_module, "interrupt", _interrupt)
    state = {"content": {"outline": _blog_outline(), "content_type": "blog"}}
    result = review_module.review_outline(state)
    return payloads[0], result["content"]["outline"]


def test_gate_payload_carries_the_editable_sections(monkeypatch):
    payload, _ = _approve(monkeypatch, {"action": "approve"})

    assert [row["id"] for row in payload["editable_sections"]] == BLOG_IDS


def test_approval_without_sections_keeps_the_outline(monkeypatch):
    _, outline = _approve(monkeypatch, {"action": "approve"})

    assert _headings(outline) == _headings(_blog_outline())
    assert outline["_render"] == {"blocks": []}  # untouched when nothing was edited
    assert outline["status"] == "approved"


def test_approval_with_sections_writes_the_order_and_refreshes_the_display(monkeypatch):
    rows = [{"id": BLOG_IDS[2], "heading": "Heel drop, explained simply"}, {"id": BLOG_IDS[0]}]

    _, outline = _approve(monkeypatch, {"action": "approve", "sections": rows})

    assert _headings(outline) == ["Heel drop, explained simply", "Why the right shoe matters"]
    assert outline["status"] == "approved"
    rendered = repr(outline["_render"])
    assert "Heel drop, explained simply" in rendered
    assert "Cushioning and support" not in rendered


# --- adding a section ----------------------------------------------------------


def _best_tools_outline():
    return {
        "title": "Best running apps",
        "tools": [
            {"name": "Strava", "summary": "Social"},
            {"name": "Runkeeper", "summary": "Simple"},
        ],
    }


def test_only_lists_of_headed_sections_take_additions():
    assert addable_lists(_blog_outline(), "blog") == ["structure.sections"]
    assert addable_lists(_best_tools_outline(), "best-tools") == []


def test_an_added_section_goes_where_the_reviewer_put_it():
    rows = [
        {"id": BLOG_IDS[0]},
        {"new": True, "list": "structure.sections", "heading": "  Caring for your shoes "},
        {"id": BLOG_IDS[1]},
        {"id": BLOG_IDS[2]},
        {"id": BLOG_IDS[3]},
    ]

    edited = apply_section_edits(_blog_outline(), "blog", rows)

    assert _headings(edited) == [
        "Why the right shoe matters",
        "Caring for your shoes",
        "Cushioning and support",
        "Heel drop explained",
        "How to get fitted",
    ]
    added = edited["structure"]["sections"][1]
    # its neighbours' level and word budget, and no invented plan
    assert added == {
        "heading": "Caring for your shoes",
        "description": "",
        "key_points": [],
        "heading_level": "H2",
        "suggested_word_count": 200,
    }


def test_an_added_subsection_keeps_its_level():
    rows = [
        {"id": BLOG_IDS[0]},
        {
            "new": True,
            "list": "structure.sections",
            "heading": "Trail shoes",
            "heading_level": "H3",
        },
        *({"id": row_id} for row_id in BLOG_IDS[1:]),
    ]

    edited = apply_section_edits(_blog_outline(), "blog", rows)

    assert edited["structure"]["sections"][1]["heading_level"] == "H3"


def test_rows_that_only_add_keep_the_list():
    edited = apply_section_edits(
        _blog_outline(),
        "blog",
        [{"new": True, "list": "structure.sections", "heading": "Caring for your shoes"}],
    )

    assert _headings(edited) == [*_headings(_blog_outline()), "Caring for your shoes"]


def test_a_stale_id_beside_an_addition_never_removes_the_sections():
    # An id the list no longer has (a gate from before a regeneration) names no
    # section, so the payload only adds: every section stays.
    edited = apply_section_edits(
        _blog_outline(),
        "blog",
        [
            {"id": "structure.sections:9", "heading": "Gone"},
            {"new": True, "list": "structure.sections", "heading": "Caring for your shoes"},
        ],
    )

    assert _headings(edited) == [*_headings(_blog_outline()), "Caring for your shoes"]


def test_an_added_h4_keeps_its_level_in_a_pillar_outline():
    outline = {
        "structure": {
            "sections": [_section("Pillar"), _section("Branch", "H3"), _section("Leaf", "H4")]
        }
    }
    edited = apply_section_edits(
        outline,
        "pillar-content",
        [
            {"id": "structure.sections:0", "heading": "Pillar"},
            {"id": "structure.sections:1", "heading": "Branch"},
            {"new": True, "list": "structure.sections", "heading": "Twig", "heading_level": "H4"},
            {"id": "structure.sections:2", "heading": "Leaf"},
        ],
    )

    sections = edited["structure"]["sections"]
    assert [(s["heading"], s["heading_level"]) for s in sections] == [
        ("Pillar", "H2"),
        ("Branch", "H3"),
        ("Twig", "H4"),
        ("Leaf", "H4"),
    ]


def test_a_refused_row_never_logs_the_reviewers_words(caplog):
    words = "Call Jane Doe on 555-0100"
    rows = [
        {"new": True, "heading": words},
        {"id": "nonsense", "heading": words},
        {"new": True, "list": "faqs", "heading": words},
        {"new": True, "list": words, "heading": "A heading"},
        {"id": f"{words}:0", "heading": "A heading"},
    ]
    with caplog.at_level("WARNING"):
        apply_section_edits(_blog_outline(), "blog", rows)

    assert caplog.records
    assert "Jane Doe" not in caplog.text


def test_additions_that_cannot_be_taken_are_ignored():
    outline = _best_tools_outline()
    for rows in (
        [{"new": True, "list": "tools", "heading": "Nike Run Club"}],  # a list of entries
        [{"new": True, "list": "nowhere", "heading": "Lost"}],
        [{"new": True, "heading": "No list"}],
    ):
        assert apply_section_edits(outline, "best-tools", rows) == outline

    blank = [{"id": row_id} for row_id in BLOG_IDS]
    blank.append({"new": True, "list": "structure.sections", "heading": "   "})
    assert _headings(apply_section_edits(_blog_outline(), "blog", blank)) == _headings(
        _blog_outline()
    )


def test_additions_are_capped():
    rows = [{"id": row_id} for row_id in BLOG_IDS]
    rows += [
        {"new": True, "list": "structure.sections", "heading": f"Extra {n}"}
        for n in range(MAX_ADDED_SECTIONS + 3)
    ]

    edited = apply_section_edits(_blog_outline(), "blog", rows)

    assert len(_headings(edited)) == len(BLOG_IDS) + MAX_ADDED_SECTIONS


def test_the_writer_and_the_validator_expect_an_added_section():
    rows = [
        {"id": BLOG_IDS[0]},
        {"new": True, "list": "structure.sections", "heading": "Caring for your shoes"},
        {"id": BLOG_IDS[3]},
    ]
    edited = apply_section_edits(_blog_outline(), "blog", rows)

    expected = resolve_expected_headings(resolve_outline_structure(edited, "blog"))
    assert expected == ["Why the right shoe matters", "Caring for your shoes", "How to get fitted"]
    assert "Caring for your shoes" in _format_outline_for_generation(edited, "blog")


# --- what the gate shows as the outline's sources ------------------------------


def _gate_payload(monkeypatch, serp_normalized, serp_result=None):
    payloads = []

    def _interrupt(payload):
        payloads.append(payload)
        return {"action": "approve"}

    monkeypatch.setattr(review_module, "interrupt", _interrupt)
    review_module.review_outline(
        {
            "content": {"outline": _blog_outline(), "content_type": "blog"},
            "serp_normalized": serp_normalized,
            "serp_result": serp_result,
        }
    )
    return payloads[0]


def test_gate_payload_carries_additions_and_the_search_evidence(monkeypatch):
    payload = _gate_payload(
        monkeypatch,
        {
            "normalize_results": [
                {
                    "position": 1,
                    "title": "Best shoes",
                    "domain": "a.test",
                    "url": "https://a.test/",
                },
                {
                    "position": 2,
                    "title": "Shoe guide",
                    "domain": "b.test",
                    "url": "https://b.test/",
                },
            ],
            "questions": ["How often?", "how often?", None, "  ", "Which brand?"],
            "related_topics": ["running shoes", "trail shoes"],
        },
        {"related_searches": ["running shoes", "trail shoes", "Running shoes"]},
    )

    assert payload["section_additions"] == ["structure.sections"]
    assert [result["url"] for result in payload["serp_titles"]] == [
        "https://a.test/",
        "https://b.test/",
    ]
    assert payload["serp_questions"] == ["How often?", "Which brand?"]
    assert payload["related_searches"] == ["running shoes", "trail shoes"]


def test_gate_payload_without_a_serp_has_empty_sources(monkeypatch):
    payload = _gate_payload(monkeypatch, None)

    assert payload["serp_titles"] == []
    assert payload["serp_questions"] == []
    assert payload["related_searches"] == []


@pytest.mark.parametrize(
    ("serp_normalized", "serp_result"),
    [
        # A failed lookup (fetch_serp's empty state) before normalization.
        ({}, {"organic_results": [], "related_searches": [], "serp_status": "lookup_failed"}),
        # State that isn't the shape it should be.
        (["not", "a dict"], "provider error"),
        # The right keys holding the wrong things.
        ({"normalize_results": 5, "questions": 7}, {"related_searches": "running shoes"}),
        # A result whose title and address aren't text: the shared title reader
        # raises on it, and the gate sends no evidence rather than stopping.
        ({"normalize_results": [{"position": 1, "title": 42, "url": 7}]}, None),
    ],
)
def test_an_odd_or_missing_serp_never_breaks_the_gate(monkeypatch, serp_normalized, serp_result):
    payload = _gate_payload(monkeypatch, serp_normalized, serp_result)

    assert payload["serp_titles"] == []
    assert payload["serp_questions"] == []
    assert payload["related_searches"] == []
    # The gate answers as before.
    assert [row["id"] for row in payload["editable_sections"]] == BLOG_IDS
    assert payload["section_additions"] == ["structure.sections"]


def test_related_searches_are_googles_not_the_models_backfill(monkeypatch):
    # With no related searches on the page, competitor.py fills related_topics
    # with the model's suggested keywords; Sources must not show them as Google's.
    payload = _gate_payload(
        monkeypatch,
        {"related_topics": ["suggested keyword one", "suggested keyword two"]},
        {"related_searches": []},
    )

    assert payload["related_searches"] == []


def test_approval_with_an_added_section_writes_it(monkeypatch):
    rows = [
        {"id": BLOG_IDS[0]},
        {"new": True, "list": "structure.sections", "heading": "Caring for your shoes"},
    ]

    _, outline = _approve(monkeypatch, {"action": "approve", "sections": rows})

    assert _headings(outline) == ["Why the right shoe matters", "Caring for your shoes"]
    assert "Caring for your shoes" in repr(outline["_render"])


# --- the writer keeps what the user approved (G70 #586, G71 #587) -------------


def _tools_outline():
    outline = _blog_outline()
    outline["structure"]["sections"] = [
        _section("Top tools for agencies"),
        _section("1. Rext AI", "H3"),
        _section("2. Surfer SEO", "H3"),
        _section("3. Contentbot", "H3"),
        _section("4. Postiv", "H3"),
        _section("5. SEO.ai", "H3"),
        _section("FAQs on AI writing tools"),
    ]
    return outline


TOOL_IDS = [f"structure.sections:{i}" for i in range(7)]


def test_moved_numbered_items_are_numbered_again_in_their_new_order():
    """A moved item kept its old number, and the writer put it back where the number said."""
    rows = [{"id": TOOL_IDS[i]} for i in (0, 1, 5, 2, 3, 6)]  # 5. SEO.ai up two, Postiv removed

    edited = apply_section_edits(_tools_outline(), "blog", rows)

    assert _headings(edited) == [
        "Top tools for agencies",
        "1. Rext AI",
        "2. SEO.ai",
        "3. Surfer SEO",
        "4. Contentbot",
        "FAQs on AI writing tools",
    ]
    plan = _format_outline_for_generation(edited, "blog")
    assert plan.index("2. SEO.ai") < plan.index("3. Surfer SEO") < plan.index("4. Contentbot")


def test_a_single_numbered_heading_keeps_its_number():
    outline = _blog_outline()
    outline["structure"]["sections"][1]["heading"] = "3 ways cushioning helps"
    outline["structure"]["sections"][3]["heading"] = "1. Get fitted"
    rows = [{"id": BLOG_IDS[i]} for i in (3, 0, 1, 2)]

    edited = apply_section_edits(outline, "blog", rows)

    assert _headings(edited)[:2] == ["1. Get fitted", "Why the right shoe matters"]
    assert "3 ways cushioning helps" in _headings(edited)


def test_a_renamed_faq_section_is_still_where_the_faqs_go():
    """Renamed, it no longer says FAQ: the writer wrote it and then added a second FAQ."""
    from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
    from src.flow.engines.content.generation.outline_structure import faq_section_heading

    rows = [{"id": TOOL_IDS[i]} for i in range(6)]
    rows.append({"id": TOOL_IDS[6], "heading": "Questions agencies ask"})

    edited = apply_section_edits(_tools_outline(), "blog", rows)

    assert faq_section_heading(edited, "blog") == "Questions agencies ask"
    plan = _format_outline_for_generation(edited, "blog")
    assert 'in the section "Questions agencies ask"' in plan
    assert "Holds faqs" not in plan and "holds_faqs" not in plan
    block = PersonaInjectionMiddleware()._build_outline_block(edited, "blog")
    assert 'section "Questions agencies ask"' in block
    assert "Holds faqs" not in block and "holds_faqs" not in block


def test_an_outline_without_a_faq_section_keeps_the_faq_at_the_end():
    from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
    from src.flow.engines.content.generation.outline_structure import faq_section_heading

    outline = _blog_outline()  # the FAQs, but no section whose heading says FAQ

    assert faq_section_heading(outline, "blog") is None
    assert "in the FAQ section" in _format_outline_for_generation(outline, "blog")
    block = PersonaInjectionMiddleware()._build_outline_block(outline, "blog")
    assert "a FAQ section at the end of the article" in block


def test_the_writer_is_not_told_to_adapt_the_order():
    from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware

    block = PersonaInjectionMiddleware()._build_outline_block(_tools_outline(), "blog")

    assert "adapt where needed" not in block
    assert "in this order, under these headings" in block


def test_the_writer_is_given_the_target_length_not_3000_words():
    from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware

    block = PersonaInjectionMiddleware()._build_outline_block(_tools_outline(), "blog")

    assert "3000 words" not in block
    assert "Keep to the target word count" in block
