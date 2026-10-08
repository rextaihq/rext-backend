"""The outline sidebar's keywords, tone and audience reach the writer and the rewrite (FB2.18,
revnix/rext-control#699). The keywords couldn't be edited, were weighted like the focus keyphrase
and never checked; the rewrite was told neither the tone nor the audience."""

import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

import src.flow.engines.content.generation.content_generation as node
import src.flow.engines.content.review.outline as review_module
from src.flow.engines.content.generation.humanize_content import _build_prompt_data
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.validation import check_secondary_keywords
from src.flow.engines.content.review.outline import _clean_keywords
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.prompts.system.humanize import HUMANIZE_SYSTEM_PROMPT
from src.services.check_wording import user_detail
from src.services.content_cluster_mapping_service import (
    cluster_heading_map_without_keywords,
    clusters_without_keywords,
    format_cluster_heading_map_for_prompt,
)

FOCUS = "content calendar template"
ARTICLE = {
    "title": "How to use a content calendar template",
    "meta_description": "A content calendar template for small teams.",
    "introduction": "A content calendar template keeps a small team on schedule.",
    "body_markdown": "## Plan the month\n\nPick themes, then dates. An editorial calendar helps.",
}


# -- The gate: the user's keyword list --------------------------------------------------


def test_the_keyword_list_is_cleaned():
    assert _clean_keywords(
        ["  editorial  calendar ", "Editorial Calendar", 42, "", "social media plan", None]
    ) == ["editorial calendar", "social media plan"]
    assert _clean_keywords("not a list") is None
    assert len(_clean_keywords([f"keyword {i}" for i in range(40)])) == 20


def test_a_phrase_over_the_limit_is_dropped_not_cut():
    assert _clean_keywords(["x" * 200, "posting schedule"]) == ["posting schedule"]


def test_the_focus_keyphrase_is_left_out_of_the_secondary_keywords():
    assert _clean_keywords([f" {FOCUS.upper()} ", "posting schedule"], FOCUS) == [
        "posting schedule"
    ]


def _approve(monkeypatch, response, outline=None, **state):
    monkeypatch.setattr(review_module, "interrupt", lambda _payload: response)
    state = {
        **state,
        "content": {
            **state.get("content", {}),
            "content_type": "blog",
            "outline": {
                "title": ARTICLE["title"],
                "sections": [],
                "focus_keyphrase": FOCUS,
                "keywords_to_include": [FOCUS, "editorial calendar"],
                **(outline or {}),
            },
        },
    }
    return review_module.review_outline(state)["content"]["outline"]


@pytest.mark.unit
def test_the_users_keywords_replace_the_outlines_with_the_focus_keyphrase_first(monkeypatch):
    outline = _approve(
        monkeypatch,
        {"action": "approve", "keywords_to_include": ["social media plan", "posting schedule"]},
    )

    assert outline["keywords_to_include"] == [FOCUS, "social media plan", "posting schedule"]


@pytest.mark.unit
def test_without_a_keyword_list_the_outlines_stay(monkeypatch):
    outline = _approve(monkeypatch, {"action": "approve"})

    assert outline["keywords_to_include"] == [FOCUS, "editorial calendar"]
    assert "removed_keywords" not in outline


@pytest.mark.unit
def test_a_long_focus_keyphrase_stays_whole_and_only_once(monkeypatch):
    long_focus = "how to plan a content calendar for a small marketing team " * 2
    long_focus = " ".join(long_focus.split())
    assert len(long_focus) > 80

    outline = _approve(
        monkeypatch,
        {"action": "approve", "keywords_to_include": [long_focus, "posting schedule"]},
        outline={"focus_keyphrase": long_focus, "keywords_to_include": [long_focus]},
    )

    assert outline["keywords_to_include"] == [long_focus, "posting schedule"]


@pytest.mark.unit
def test_the_runs_own_keyphrase_is_pinned_not_an_older_outlines(monkeypatch):
    """An outline saved before pinning can carry the model's phrase; the run's state has
    the user's. The screen showed the model's as the primary and sends it back."""
    outline = _approve(
        monkeypatch,
        {"action": "approve", "keywords_to_include": ["calendar planning", "posting schedule"]},
        outline={
            "focus_keyphrase": "calendar planning",
            "keywords_to_include": ["calendar planning"],
        },
        content={"focus_keyword": FOCUS},
    )

    assert outline["focus_keyphrase"] == FOCUS
    assert outline["keywords_to_include"] == [FOCUS, "posting schedule"]
    assert outline["removed_keywords"] == []


@pytest.mark.unit
def test_the_keywords_the_user_took_out_are_recorded(monkeypatch):
    outline = _approve(
        monkeypatch,
        {"action": "approve", "keywords_to_include": [FOCUS, "posting schedule"]},
        outline={"keywords_to_include": [FOCUS, "editorial calendar", "content calendar"]},
    )

    # "content calendar" is part of the focus keyphrase: the writer can't avoid it.
    assert outline["removed_keywords"] == ["editorial calendar"]


@pytest.mark.unit
def test_a_removed_keyword_is_part_of_another_only_as_whole_words(monkeypatch):
    outline = _approve(
        monkeypatch,
        {"action": "approve", "keywords_to_include": [FOCUS, "email marketing"]},
        outline={"keywords_to_include": [FOCUS, "AI", "email marketing"]},
    )

    # "ai" is inside "email marketing" as letters, not as a word: it was removed.
    assert outline["removed_keywords"] == ["AI"]


@pytest.mark.unit
def test_the_screens_copy_of_the_outline_follows_the_sidebar_edits(monkeypatch):
    outline = _approve(
        monkeypatch,
        {
            "action": "approve",
            "keywords_to_include": [FOCUS, "posting schedule"],
            "tone": "Practical",
            "target_audience": ["Marketing leads"],
        },
        outline={"_render": {"keywords_to_include": [FOCUS, "editorial calendar"], "tone": ""}},
    )

    assert outline["_render"]["keywords_to_include"] == [FOCUS, "posting schedule"]
    assert outline["_render"]["tone"] == "Practical"


# -- The cluster notes: a removed keyword leaves them ------------------------------------


def _cluster_map():
    return {
        "enabled": True,
        "h1": {"suggested_heading": ARTICLE["title"], "primary_keyword": FOCUS},
        "h2_sections": [
            {
                "suggested_heading": "Plan the month",
                "cluster_name": "planning",
                "primary_keyword": "monthly content plan",
                "supporting_keywords": ["editorial calendar", "posting schedule"],
                "h3_topics": ["editorial calendar", "Themes first"],
            },
            {
                "suggested_heading": "Editorial calendars",
                "cluster_name": "editorial calendar",
                "primary_keyword": "editorial calendar",
                "supporting_keywords": [],
            },
        ],
        "h3_sections": [],
        "body_copy_clusters": [
            {
                "suggested_heading": "Tools",
                "primary_keyword": "Editorial Calendar",
                "supporting_keywords": ["calendar tools"],
            }
        ],
        "additional_keywords": ["editorial calendar", "calendar tools"],
    }


def test_a_removed_keyword_leaves_the_cluster_map():
    trimmed = cluster_heading_map_without_keywords(_cluster_map(), ["Editorial  calendar"])

    assert [s["suggested_heading"] for s in trimmed["h2_sections"]] == ["Plan the month"]
    assert trimmed["h2_sections"][0]["supporting_keywords"] == ["posting schedule"]
    assert trimmed["h2_sections"][0]["h3_topics"] == ["Themes first"]
    assert trimmed["body_copy_clusters"][0]["primary_keyword"] == ""
    assert trimmed["additional_keywords"] == ["calendar tools"]
    assert "editorial calendar" not in format_cluster_heading_map_for_prompt(trimmed).lower()


def test_a_removed_keyword_leaves_the_maps_h1_entry_too():
    cluster_map = {**_cluster_map(), "h1": {"suggested_heading": "T", "primary_keyword": "AI"}}

    trimmed = cluster_heading_map_without_keywords(cluster_map, ["ai"])

    assert trimmed["h1"] == {"suggested_heading": "T", "primary_keyword": ""}
    prompt = format_cluster_heading_map_for_prompt(trimmed)
    assert "H1 keyword focus: T\n" in prompt and "Primary keyword" not in prompt
    assert "| Primary keyword: " + FOCUS in format_cluster_heading_map_for_prompt(_cluster_map())


def test_without_removed_keywords_the_cluster_map_is_the_same_one():
    cluster_map = _cluster_map()

    assert cluster_heading_map_without_keywords(cluster_map, []) is cluster_map
    assert cluster_heading_map_without_keywords(None, ["x"]) is None


def test_a_removed_keyword_leaves_the_keyword_clusters():
    clusters = [
        {"cluster_name": "a", "keywords": [{"keyword": "editorial calendar"}, {"keyword": "x"}]},
        {"cluster_name": "b", "keywords": [{"keyword": "Editorial Calendar"}]},
    ]

    kept = clusters_without_keywords(clusters, ["editorial calendar"])

    assert [(c["cluster_name"], [k["keyword"] for k in c["keywords"]]) for c in kept] == [
        ("a", ["x"])
    ]
    assert clusters_without_keywords(clusters, []) is clusters


# -- The spec and the check -------------------------------------------------------------


def _spec(keywords):
    return build_requirements_spec(
        {"title": ARTICLE["title"], "keywords_to_include": keywords}, "blog", focus_keyword=FOCUS
    )


def test_the_secondary_keywords_are_the_approved_ones_without_the_focus_keyphrase():
    spec = _spec([FOCUS, "editorial calendar", "Content Calendar Template"])

    assert spec["secondary_keywords"] == ["editorial calendar"]


def test_every_secondary_keyword_present_passes():
    assert check_secondary_keywords(ARTICLE, _spec([FOCUS, "editorial calendar"]))["passed"]


def test_a_missing_secondary_keyword_is_a_warning_not_a_block():
    result = check_secondary_keywords(ARTICLE, _spec([FOCUS, "editorial calendar", "batching"]))

    assert result["passed"] is False and result["severity"] == "warning"
    assert "'batching'" in result["detail"] and "editorial calendar" not in result["detail"]


@pytest.mark.parametrize(
    ("keyword", "text", "appears"),
    [
        ("C++", "We use C# here.", False),
        ("C++", "We use C++ here.", True),
        (".NET", "It runs on the net.", False),
        (".NET", "It runs on .NET 8.", True),
        ("node.js", "Built with Node.js and care.", True),
        # In a link's address the reader never sees it; in its anchor text they do.
        ("node.js", "Read [the documentation](https://example.com/node.js-guide).", False),
        ("node.js", "Read [the node.js guide](https://example.com/guide).", True),
        ("what is a content calendar?", "So, what is a content calendar, really", True),
        ("editorial calendar", "An editorial-calendar helps.", True),
    ],
)
def test_a_keyword_with_a_symbol_is_matched_as_written(keyword, text, appears):
    article = {"title": "T", "body_markdown": text}

    assert check_secondary_keywords(article, _spec([FOCUS, keyword]))["passed"] is appears


def test_the_saved_article_keeps_the_approved_secondary_keywords():
    from src.flow.engines.content.generation.requirements_spec import (
        approved_secondary_keywords,
    )

    outline = {"keywords_to_include": [FOCUS, " editorial calendar ", "", FOCUS.upper()]}

    assert approved_secondary_keywords(outline, FOCUS) == ["editorial calendar"]
    assert approved_secondary_keywords({}, FOCUS) == []


def test_an_emptied_keyword_list_is_saved_empty_not_as_the_models_own():
    from src.flow.engines.content.generation.persist_content import _saved_secondary_keywords

    final = {"secondary_keywords": ["a phrase the model chose"]}
    listed = {"outline": {"keywords_to_include": [FOCUS, "posting schedule"]}}
    emptied = {"outline": {"keywords_to_include": [FOCUS]}}

    assert _saved_secondary_keywords(listed, final, FOCUS) == ["posting schedule"]
    # The user removed every secondary keyword: the list holds only the focus keyphrase.
    assert _saved_secondary_keywords(emptied, final, FOCUS) == []
    # An older run's outline carries no list: the model's is all there is.
    assert _saved_secondary_keywords({"outline": {}}, final, FOCUS) == ["a phrase the model chose"]


def test_the_checklist_names_the_missing_keywords():
    one = check_secondary_keywords(ARTICLE, _spec([FOCUS, "editorial calendar", "batching"]))
    line = user_detail("secondary_keywords", one["detail"])

    assert line == "A keyword you approved is missing: batching."
    # A row saved in these words reads the same on the way out of the API.
    assert user_detail("secondary_keywords", line) == line

    many = check_secondary_keywords(
        ARTICLE, _spec([FOCUS, *[f"missing phrase {i}" for i in range(6)], "writer's block"])
    )
    line = user_detail("secondary_keywords", many["detail"])

    assert line == (
        "Keywords you approved are missing: missing phrase 0, missing phrase 1, "
        "missing phrase 2, missing phrase 3 and 3 more."
    )
    assert user_detail("secondary_keywords", line) == line


def test_a_detail_in_other_words_gets_the_plain_line():
    assert user_detail("secondary_keywords", "Something else.") == (
        "Some keywords you approved don't appear in the article as written."
    )


# -- What the writer is told ------------------------------------------------------------


class _Writer:
    def __init__(self, seen):
        self.seen = seen

    async def astream_events(self, payload, *_args, **_kwargs):
        self.seen.extend(payload["messages"])
        yield {
            "event": "on_chain_end",
            "name": "agent",
            "run_id": "root",
            "data": {"output": {"messages": [AIMessage(content=json.dumps(ARTICLE))]}},
        }


@pytest.mark.asyncio
async def test_the_writer_gets_the_focus_keyphrase_apart_from_the_secondary_keywords(
    monkeypatch,
):
    seen = []

    async def nothing(*_args, **_kwargs):
        return None

    async def create_content_agent(**_kwargs):
        return _Writer(seen)

    monkeypatch.setattr(node, "consume_stage_credits", nothing)
    monkeypatch.setattr(node, "_fetch_known_entities", AsyncMock(return_value=(None, [])))
    monkeypatch.setattr(node, "research_official_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        node,
        "enforce_subheadings_for_spec",
        AsyncMock(side_effect=lambda content, *a, **k: content),
    )
    monkeypatch.setattr(node, "get_stream_writer", lambda: lambda _event: None)
    monkeypatch.setattr(node, "can_afford_stage", AsyncMock(return_value=False))
    monkeypatch.setattr(node, "create_content_agent", create_content_agent)
    await node.generate_content(
        {
            "content": {
                "selected_topic": ARTICLE["title"],
                "content_type": "blog",
                "outline": {
                    "focus_keyphrase": FOCUS,
                    "keywords_to_include": [FOCUS, "editorial calendar", "posting schedule"],
                    "removed_keywords": ["calendar tools"],
                    "cluster_heading_map": {
                        **_cluster_map(),
                        "h2_sections": [
                            {
                                "suggested_heading": "Plan the month",
                                "cluster_name": "planning",
                                "primary_keyword": "monthly content plan",
                                "supporting_keywords": ["calendar tools"],
                            }
                        ],
                        "body_copy_clusters": [],
                        "additional_keywords": [],
                    },
                },
            },
            "seo_result": {
                "keyword_clusters": [
                    {
                        "cluster_name": "planning",
                        "keywords": [{"keyword": "calendar tools"}, {"keyword": "theme days"}],
                    }
                ]
            },
            "serp_payload": {"user_id": "u", "workspace_id": "w", "keyword": FOCUS},
        }
    )
    message = "\n".join(str(m.content) for m in seen)

    assert f'Focus keyphrase: "{FOCUS}"' in message
    assert "Secondary keywords the user approved: editorial calendar, posting schedule" in message
    assert "Use each secondary keyword at least once" in message
    # A keyword the user added is in no cluster: the cluster rule names it as allowed.
    assert (
        "Use only the approved keyword clusters above. The secondary keywords the user" in message
    )
    assert "use each one even when no keyword cluster lists it" in message
    # A keyword the user removed is named once, as removed, and is in no cluster note.
    assert message.count("calendar tools") == 1
    assert "KEYWORDS THE USER REMOVED: calendar tools" in message
    # The approved headings win where one already contains a removed phrase.
    assert "A heading of the approved outline that already contains one stays" in message
    assert "Keywords: theme days" in message


# -- What the rewrite is told -----------------------------------------------------------


def test_the_rewrite_gets_the_reader_the_tone_and_the_secondary_keywords():
    data = _build_prompt_data(
        content_payload=dict(ARTICLE),
        content_type="blog",
        focus_keyword=FOCUS,
        secondary_keywords=["editorial calendar"],
        audience=["Marketing leads", "Small agencies"],
        tone="Practical, plain-spoken",
    )

    assert "Written for: Marketing leads, Small agencies" in data["reader_instruction"]
    assert "Tone: Practical, plain-spoken" in data["reader_instruction"]
    assert "secondary keywords; keep each at least once" in data["keyword_instruction"]
    assert "editorial calendar" in data["keyword_instruction"]
    human = get_humanize_prompt().format_messages(**data)[1].content
    assert "READER AND TONE" in human


def test_the_chosen_tone_wins_over_the_rewrites_casual_style():
    assert "the tone given in the message below, asks for a formal register" in (
        HUMANIZE_SYSTEM_PROMPT
    )
    assert "that tone is formal, the tone wins" in HUMANIZE_SYSTEM_PROMPT
    assert "or the tone in the message below, says otherwise" in HUMANIZE_SYSTEM_PROMPT


def test_the_rewrite_template_has_no_unfilled_placeholders():
    for placeholder in (
        "[exact persona + skill level]",
        "[casual/direct/spicy/calm]",
        "(fill these)",
    ):
        assert placeholder not in HUMANIZE_SYSTEM_PROMPT


def test_without_a_reader_or_tone_nothing_is_added():
    data = _build_prompt_data(content_payload=dict(ARTICLE), content_type="blog")

    assert data["reader_instruction"] == ""
