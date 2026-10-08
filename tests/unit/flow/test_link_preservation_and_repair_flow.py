"""Regression tests: links survive the content pipeline, and repair converges in one pass.

Two reported defects, pinned end to end:

1. Links visible while an article was generating were missing from the final
   article. Root cause: structured generation (all 34 content types) assembles
   `body_markdown` from the section blocks and discarded the model's own
   `body_markdown` — which the prompt and schema told it to put every link in.
   Repair and humanization then had no verification that a valid link survived
   their rewrite (a dropped citation shipped with zero failed checks), and the
   model's internal-link fallback re-appended a dropped link as a bare line
   that failed as "bolted-on".

2. Validation routinely needed two repair calls. Word count (which a
   minimal-edit repair cannot fix) was routed to repair; issue details were
   truncated to three URLs; and a repair that broke a passing check was accepted,
   so the next validation failed on the new breakage.

The pipeline tests run the real validate -> route -> repair -> humanize ->
final-validate nodes through a LangGraph wired like create_content_engine, with
only the LLM calls replaced.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.graph import END, START, StateGraph

from src.flow.engines.content.generation import humanize_content as humanize_module
from src.flow.engines.content.generation import repair_content as repair_module
from src.flow.engines.content.generation import subheading_seo
from src.flow.engines.content.generation import validation as v
from src.flow.engines.content.generation.humanize_content import humanize_content
from src.flow.engines.content.generation.keyword_density import CONTENT_TYPE_FAMILIES
from src.flow.engines.content.generation.link_integrity import (
    extract_links,
    normalize_url,
    present_urls,
    reconcile_link_lists,
    restore_lost_links,
)
from src.flow.engines.content.generation.repair_content import (
    HUMANIZATION_OWNED_CHECKS,
    repair_content,
)
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.section_rewrite import STATED_SHARE_TO_CUT
from src.flow.engines.content.generation.structured_body import (
    UNPLACED_LINKS_KEY,
    assemble_structured_payload,
    build_structured_content_model,
)
from src.flow.engines.content.generation.validation import (
    final_validate_content,
    validate_content,
)
from src.flow.engines.router.content_quality import validation_router
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.model.structure.contents.base import ContentBlock
from src.flow.states.rext import REXT

ALL_CONTENT_TYPES = sorted(CONTENT_TYPE_FAMILIES)
REPRESENTATIVE_TYPES = [
    "blog",
    "how-to-guide",
    "faq",
    "comparison",
    "in-depth-review",
    "landing-page",
    "pricing-page",
    "documentation",
]

KW = "crm software"
TITLE = "CRM Software for Small Teams: How to Choose the Right One"
INTERNAL = "https://site.test/guides/crm-data-migration"
CITATION = "https://research.test/reports/crm-adoption"
FABRICATED = "https://made-up.test/crm-statistics"

INTERNAL_ANCHOR = "a careful data migration checklist"
CITATION_ANCHOR = "how small teams adopt new sales tools"

SEARCHED = [
    {
        "url": CITATION,
        "title": "How small teams adopt sales tools",
        "snippet": "small teams adopt new sales tools; habits matter more than features",
    }
]

_SENTENCES = [
    "Most small teams begin with spreadsheets and shared inboxes, then notice that follow-ups slip.",
    "A shared record of every conversation fixes that, as long as people keep it current.",
    "Start with the handful of fields your team uses every day and agree on who owns each stage.",
    "Review the pipeline together once a week so problems surface early instead of late.",
    "Keep the setup simple at first and add automation only after the basic habits are in place.",
    "Write down how a lead moves from first contact to signed deal before touching any settings.",
    "Ask the people who answer customers what slows them down, because they know the gaps best.",
    "Pick one owner for the rollout so decisions do not stall while everyone waits on everyone.",
]

_EXTRA_SENTENCES = [
    "Plan a short pilot with two people before inviting the whole team.",
    "Collect the questions that come up during the pilot and answer them in one shared note.",
    "Retire the old spreadsheet on a fixed date so nobody keeps two versions of the truth.",
    "Celebrate the first month of clean records, since that habit is what makes the rest work.",
]


def _para(i: int, extra: str = "") -> str:
    ordered = _SENTENCES[i % 8 :] + _SENTENCES[: i % 8]
    return " ".join(ordered) + (f" {extra}" if extra else "")


INTERNAL_SENTENCE = f"Before you import anything, follow [{INTERNAL_ANCHOR}]({INTERNAL}) so old contacts arrive clean."
CITATION_SENTENCE = (
    f"Research on [{CITATION_ANCHOR}]({CITATION}) points the same way: habits matter more "
    "than features."
)


def _body(
    *, internal: str = INTERNAL_SENTENCE, citation: str = CITATION_SENTENCE, extra: int = 0
) -> str:
    body = (
        "## How Small Teams Choose CRM Software\n\n"
        f"{_para(0, 'Good crm software makes that shared record easy to keep.')}\n\n"
        f"{internal} {_para(1)}\n\n"
        "## Setting Up Follow-Up Reminders That Stick\n\n"
        f"{_para(2)}\n\n"
        f"{citation} {_para(3)}\n\n"
        "## Rolling Out CRM Software Without Losing Data\n\n"
        f"{_para(4, 'Treat crm software as a habit you build, not a purchase you make.')}\n\n"
        f"{_para(5)}\n\n"
        "## Reports Worth Reading Every Monday\n\n"
        f"{_para(6)}\n\n{_para(7)}"
    )
    for i in range(extra):
        body += "\n\n" + " ".join(_EXTRA_SENTENCES[i % 4 :] + _EXTRA_SENTENCES[: i % 4])
    return body


def _article(**overrides: Any) -> dict:
    article = {
        "title": TITLE,
        "meta_title": TITLE,
        "focus_keyphrase": KW,
        "meta_description": (
            "Compare crm software for small teams: the features that matter, how to roll it "
            "out and what to avoid. Read the full guide."
        ),
        "introduction": (
            f"Picking crm software is easier once you know what your team actually needs. {_para(1)}"
        ),
        "body_markdown": _body(),
        "internal_links": [{"url": INTERNAL, "anchor_text": INTERNAL_ANCHOR}],
        "outbound_links": [{"url": CITATION, "anchor_text": CITATION_ANCHOR}],
    }
    article.update(overrides)
    return article


def _words(article: dict) -> int:
    return len(v._combined_text(article).split())


def _outline(target_word_count: int | None = None) -> dict:
    outline = {
        "title": TITLE,
        "focus_keyphrase": KW,
        "internal_links": [
            {
                "url": INTERNAL,
                "title": "CRM data migration checklist",
                "anchor_text": "data migration checklist",
            }
        ],
    }
    outline["target_word_count"] = target_word_count or _words(_article())
    return outline


def _spec(content_type: str = "blog", outline: dict | None = None, inventory=None) -> dict:
    return build_requirements_spec(
        outline or _outline(),
        content_type,
        KW,
        TITLE,
        generation_meta={"searched_results": SEARCHED, "link_inventory": inventory or []},
    )


def _inventory(article: dict, content_type: str = "blog", outline: dict | None = None) -> list:
    """The generation-time baseline, computed exactly as generate_content does."""
    return v.protected_links(article, _spec(content_type, outline), SEARCHED)


def _state(article: dict, content_type: str = "blog", outline: dict | None = None) -> dict:
    outline = outline or _outline()
    return {
        "serp_payload": {"query": KW},
        "content": {
            "final_content": article,
            "content_type": content_type,
            "outline": outline,
            "selected_topic": TITLE,
            "generation_meta": {
                "searched_results": SEARCHED,
                "link_inventory": _inventory(article, content_type, outline),
            },
        },
    }


def _fake_model(responder: Callable[[dict, list], dict], schema_type: str = "blog"):
    """A model double. Asked for the article's schema it answers responder(calls, messages) as
    that schema (the repair, and the rewrite of a body with nothing to split). Asked plainly,
    as the rewrite asks for one part of an article at a time, it answers responder.part(messages)
    as text, or the part unchanged."""
    calls: list[list] = []
    schema = get_generated_content_model(schema_type)

    async def _ainvoke(messages):
        calls.append(messages)
        return schema(**responder(calls, messages))

    async def _ainvoke_part(messages):
        calls.append(messages)
        part = getattr(responder, "part", None)
        return SimpleNamespace(content=part(messages) if part else _part_text(messages))

    bound = MagicMock()
    bound.ainvoke = AsyncMock(side_effect=_ainvoke)
    model = MagicMock()
    model.with_structured_output.return_value = bound
    model.ainvoke = AsyncMock(side_effect=_ainvoke_part)
    model.calls = calls
    return model


# The article of these tests as the rewrite splits it: its introduction and its four sections.
PARTS = 5
_PART_MARK = "Return only this part's markdown, nothing before it and nothing after it."


def _part_text(messages) -> str:
    """The one part a rewrite call carries."""
    return _human_text(messages).split(_PART_MARK, 1)[1].strip()


def _asked_range(messages) -> tuple[int, int]:
    """The words a rewrite call asks its part to come back at."""
    low, high = re.search(r"Return between (\d+) and (\d+) words", _human_text(messages)).groups()
    return int(low), int(high)


def _human_text(messages) -> str:
    return messages[-1].content


def _prompt_field(messages, label: str, next_label: str | None) -> str:
    text = _human_text(messages)
    start = text.index(label) + len(label)
    end = text.index(next_label, start) if next_label else len(text)
    return text[start:end].strip()


def _echo(**replace: str) -> Callable:
    """Return the article the prompt carried, with literal substitutions applied to the prose."""

    def responder(calls, messages):
        intro = _prompt_field(messages, "Introduction:", "Body (Markdown):")
        body = _prompt_field(messages, "Body (Markdown):", None)
        for old, new in replace.items():
            body = body.replace(old, new)
            intro = intro.replace(old, new)
        return {"title": TITLE, "introduction": intro, "body_markdown": body}

    def part(messages):
        text = _part_text(messages)
        for old, new in replace.items():
            text = text.replace(old, new)
        return text

    responder.part = part
    return responder


@pytest.fixture(autouse=True)
def _no_real_heading_model():
    """Heading rewrites must never reach a real model in these tests."""
    with patch.object(subheading_seo, "_llm_rewrite", AsyncMock(return_value=[])):
        yield


async def _run_pipeline(state: dict) -> dict:
    """validate <-> repair -> humanize -> final_validate, wired as in create_content_engine."""
    graph = StateGraph(REXT)
    graph.add_node("validate_content", validate_content)
    graph.add_node("repair_content", repair_content)
    graph.add_node("humanize_content", humanize_content)
    graph.add_node("final_validate_content", final_validate_content)
    graph.add_edge(START, "validate_content")
    graph.add_conditional_edges(
        "validate_content",
        validation_router,
        {"repair_content": "repair_content", "humanize_content": "humanize_content"},
    )
    graph.add_edge("repair_content", "validate_content")
    graph.add_edge("humanize_content", "final_validate_content")
    graph.add_edge("final_validate_content", END)
    return await graph.compile().ainvoke(state)


def _failing(result_checks) -> list[str]:
    return [c["name"] for c in result_checks]


# ── 1. link_integrity primitives ─────────────────────────────────────────────


def test_extract_links_records_anchor_sentence_and_section_but_not_images():
    body = _body() + "\n\n![crm software dashboard](https://img.test/a.png)"
    records = {r["url"]: r for r in extract_links(body, "body_markdown")}
    assert set(records) == {INTERNAL, CITATION}
    assert records[INTERNAL]["anchor_text"] == INTERNAL_ANCHOR
    assert records[INTERNAL]["section"] == "How Small Teams Choose CRM Software"
    assert records[INTERNAL]["sentence"].startswith("Before you import anything, follow a careful")
    assert records[CITATION]["section"] == "Setting Up Follow-Up Reminders That Stick"


@pytest.mark.parametrize(
    "a,b",
    [
        (
            "https://research.test/reports/crm-adoption",
            "https://research.test/reports/crm-adoption/",
        ),
        (
            "https://research.test/reports/crm-adoption",
            "https://RESEARCH.test/reports/crm-adoption#s2",
        ),
        (
            "https://research.test/reports/crm-adoption",
            "https://research.test/reports/crm-adoption?utm_source=x",
        ),
    ],
)
def test_url_variants_of_the_same_page_compare_equal(a, b):
    assert normalize_url(a) == normalize_url(b)


def test_dropped_link_is_restored_on_its_original_anchor_in_its_section():
    before = _article()
    after = _article(
        body_markdown=before["body_markdown"].replace(
            f"[{INTERNAL_ANCHOR}]({INTERNAL})", INTERNAL_ANCHOR
        )
    )
    restored, done, missing = restore_lost_links(after, _inventory(before))
    assert restored["body_markdown"] == before["body_markdown"]
    assert [r["url"] for r in done] == [INTERNAL] and not missing


def test_link_is_restored_into_the_reworded_sentence_that_replaced_its_sentence():
    before = _article()
    reworded = (
        "Research into how small teams adopt new sales tools says it plainly: habits beat features."
    )
    after = _article(body_markdown=_body(citation=reworded))
    restored, done, missing = restore_lost_links(after, _inventory(before))
    assert not missing
    links = {r["url"]: r for r in extract_links(restored["body_markdown"])}
    assert CITATION in links
    assert links[CITATION]["section"] == "Setting Up Follow-Up Reminders That Stick"
    assert "habits beat features" in links[CITATION]["sentence"]


def test_unrestorable_link_is_reported_and_never_appended_as_a_bare_line():
    before = _article()
    after = _article(body_markdown=_body(internal="Clean data first."))
    restored, done, missing = restore_lost_links(after, _inventory(before))
    assert [r["url"] for r in missing] == [INTERNAL] and not done
    assert restored["body_markdown"] == after["body_markdown"]


def test_link_lists_follow_the_prose_so_the_model_validator_cannot_bolt_links_on():
    before = _article()
    after = _article(body_markdown=_body(internal="Clean data first."), internal_links=[])
    reconciled = reconcile_link_lists(before, after)
    schema = get_generated_content_model("blog")
    validated = schema.model_validate(reconciled).model_dump()
    assert INTERNAL not in validated["body_markdown"]
    assert [lnk["url"] for lnk in validated["outbound_links"]] == [CITATION]


# ── 2. structured generation: the root cause ─────────────────────────────────

_STRUCTURED_OUTLINE = {
    "title": TITLE,
    "choosing_crm_section": {"summary": "How to choose", "points": ["fit", "price"]},
    "follow_up_section": {"summary": "Follow-ups", "points": ["habits"]},
}


def _structured_args(blocks, *, block_prose_has_links: bool) -> dict:
    link_body = _body()
    sections = [s for s in re.split(r"(?m)^## ", link_body) if s.strip()]
    args: dict[str, Any] = {
        "title": TITLE,
        "introduction": "Picking crm software is easier once you know what your team needs.",
        # What the prompt and base schema asked for: every link inside body_markdown.
        "body_markdown": link_body,
        "internal_links": [{"url": INTERNAL, "anchor_text": INTERNAL_ANCHOR}],
        "outbound_links": [{"url": CITATION, "anchor_text": CITATION_ANCHOR}],
    }
    for block, section in zip(blocks, sections):
        heading, _, prose = section.partition("\n\n")
        if not block_prose_has_links:
            prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", prose)
        args[block.key] = {"heading": heading.strip(), "markdown": prose.strip()}
    return args


@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_links_written_outside_the_section_blocks_survive_structured_assembly(content_type):
    model, blocks = build_structured_content_model(
        _STRUCTURED_OUTLINE, content_type, get_generated_content_model(content_type)
    )
    args = _structured_args(blocks, block_prose_has_links=False)
    # generate_content: model(**tool_args) -> model_dump() -> assemble
    payload = assemble_structured_payload(model(**args).model_dump(), blocks)

    links = {r["url"]: r for r in extract_links(payload["body_markdown"])}
    assert set(links) == {INTERNAL, CITATION}, content_type
    assert links[INTERNAL]["anchor_text"] == INTERNAL_ANCHOR
    assert links[CITATION]["section"] == "Setting Up Follow-Up Reminders That Stick"
    assert UNPLACED_LINKS_KEY not in payload


@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_links_already_in_blocks_are_untouched_by_assembly(content_type):
    model, blocks = build_structured_content_model(
        _STRUCTURED_OUTLINE, content_type, get_generated_content_model(content_type)
    )
    args = _structured_args(blocks, block_prose_has_links=True)
    args.pop("body_markdown")
    payload = assemble_structured_payload(model(**args).model_dump(), blocks)
    assert payload["body_markdown"].count(INTERNAL) == 1
    assert payload["body_markdown"].count(CITATION) == 1


def test_link_with_no_anchor_in_the_sections_is_recorded_not_silently_dropped():
    model, blocks = build_structured_content_model(
        _STRUCTURED_OUTLINE, "blog", get_generated_content_model("blog")
    )
    args = _structured_args(blocks, block_prose_has_links=False)
    for block in blocks:
        args[block.key]["markdown"] = "Plain section prose about choosing a system."
    payload = assemble_structured_payload(model(**args).model_dump(), blocks)
    unplaced = payload[UNPLACED_LINKS_KEY]
    assert {r["url"] for r in unplaced} == {INTERNAL, CITATION}
    assert all(r["anchor_text"] and r["sentence"] for r in unplaced)
    assert INTERNAL not in payload["body_markdown"]  # no bare-line fallback

    # Recorded as the baseline, it is named by validation with anchor + sentence.
    spec = _spec(inventory=v.protected_links(payload, _spec(), SEARCHED, candidates=unplaced))
    result = v.check_links_preserved(payload, spec)
    assert not result["passed"]
    assert INTERNAL_ANCHOR in result["detail"] and "original sentence" in result["detail"]


@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_structured_schema_tells_the_writer_where_links_belong(content_type):
    model, _ = build_structured_content_model(
        _STRUCTURED_OUTLINE, content_type, get_generated_content_model(content_type)
    )
    fields = model.model_fields
    assert "Leave this null" in fields["body_markdown"].description
    assert "section it is most relevant" in fields["internal_links"].description
    assert "LINKS LIVE HERE" in ContentBlock.model_fields["markdown"].description


# ── 3. which links are protected ─────────────────────────────────────────────


def test_only_valid_relevant_links_are_protected():
    irrelevant = "https://site.test/careers/open-roles"
    article = _article(
        body_markdown=_body()
        + f"\n\nSee [our survey]({FABRICATED}) and [open roles]({irrelevant}) for more."
    )
    outline = _outline()
    outline["internal_links"].append(
        {"url": irrelevant, "title": "Warehouse forklift jobs", "anchor_text": "forklift jobs"}
    )
    kinds = {
        r["url"]: r["kind"] for r in v.protected_links(article, _spec(outline=outline), SEARCHED)
    }
    assert kinds == {INTERNAL: "internal", CITATION: "citation"}


def test_brand_url_is_protected():
    outline = {
        **_outline(),
        "promote_brand": True,
        "brand_voice_promotion": {"brand_name": "Nextly", "brand_url": "https://nextly.test"},
    }
    article = _article(
        body_markdown=_body() + "\n\nTeams using [Nextly](https://nextly.test/) move faster."
    )
    kinds = {
        r["url"]: r["kind"] for r in v.protected_links(article, _spec(outline=outline), SEARCHED)
    }
    assert kinds["https://nextly.test/"] == "brand"


def test_verified_citation_with_trailing_slash_is_not_reported_as_fabricated():
    article = _article(outbound_links=[{"url": CITATION + "/", "anchor_text": CITATION_ANCHOR}])
    result = v.check_facts_and_external_links_integration(article, _spec(), SEARCHED)
    assert result["passed"], result["detail"]


def test_link_issue_details_list_every_link_not_just_three():
    urls = [f"https://site.test/guides/crm-topic-{i}" for i in range(5)]
    outline = _outline()
    outline["internal_links"] = [
        {"url": u, "title": f"crm software small teams guide {i}"} for i, u in enumerate(urls)
    ]
    result = v.check_internal_links_integration(_article(), _spec(outline=outline))
    assert not result["passed"]
    assert all(u in result["detail"] for u in urls)


# ── 4. full pipeline: links survive every stage ──────────────────────────────


@pytest.mark.parametrize("content_type", REPRESENTATIVE_TYPES)
async def test_valid_links_survive_validation_repair_humanization_and_final_validation(
    content_type,
):
    """Humanization drops one link and rewords the other's sentence; both reach the final article."""
    article = _article()
    humanizer = _fake_model(
        _echo(
            **{
                f"[{CITATION_ANCHOR}]({CITATION})": CITATION_ANCHOR,
                f"Before you import anything, follow [{INTERNAL_ANCHOR}]({INTERNAL}) so old "
                "contacts arrive clean.": "Before any import, work through a careful data "
                "migration checklist so the old contacts arrive clean.",
            }
        ),
        content_type,
    )
    repairer = _fake_model(_echo(), content_type)
    with (
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
        patch.object(repair_module, "load_content_model", return_value=repairer),
    ):
        out = await _run_pipeline(_state(article, content_type))

    final = out["content"]["final_content"]
    assert {normalize_url(INTERNAL), normalize_url(CITATION)} <= present_urls(final)
    assert (
        "work through [" in final["body_markdown"]
        or "[a careful data migration checklist]" in final["body_markdown"]
    )
    assert f"\n[{INTERNAL_ANCHOR}]({INTERNAL})" not in final["body_markdown"]  # not bolted on
    final_validation = out["content"]["review"]["final_validation"]
    assert "links_preserved" not in _failing(final_validation["failed_checks"])
    assert repairer.calls == []  # restored deterministically, no repair call needed
    assert len(humanizer.calls) == PARTS  # one rewrite: each part once


def _one_section_body() -> str:
    """The article's body under a single H2: nothing for the rewrite to split, so it is
    rewritten whole."""
    return "## How Small Teams Choose CRM Software\n\n" + _body().split("\n\n", 1)[1].replace(
        "## ", "### "
    )


async def test_humanization_link_loss_that_cannot_be_reanchored_is_repaired_in_one_call():
    """The whole-article rewrite (a body with nothing to split) can lose a link's sentence;
    what cannot be put back in place is repaired in the same call as before."""
    article = _article(body_markdown=_one_section_body())
    humanizer = _fake_model(_echo(**{CITATION_SENTENCE: "Habits beat features, every time."}))

    def repair_responder(calls, messages):
        issues = _human_text(messages)
        assert "links_preserved" in issues and CITATION_ANCHOR in issues
        return _echo(
            **{
                "Habits beat features, every time.": f"[Research on {CITATION_ANCHOR}]({CITATION}) shows habits beat features."
            }
        )(calls, messages)

    repairer = _fake_model(repair_responder)
    with (
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
        patch.object(repair_module, "load_content_model", return_value=repairer),
    ):
        out = await _run_pipeline(_state(article))
    final = out["content"]["final_content"]
    assert normalize_url(CITATION) in present_urls(final)
    assert len(repairer.calls) == 1


async def test_a_part_whose_rewrite_loses_a_link_is_kept_as_drafted_and_needs_no_repair():
    """Rewritten part by part, a part that comes back without a link it had is not used: the
    link stays in the sentence it was drafted in, and nothing has to be repaired."""
    article = _article()
    humanizer = _fake_model(_echo(**{CITATION_SENTENCE: "Habits beat features, every time."}))
    repairer = _fake_model(_echo())
    with (
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
        patch.object(repair_module, "load_content_model", return_value=repairer),
    ):
        out = await _run_pipeline(_state(article))

    final = out["content"]["final_content"]
    assert CITATION_SENTENCE in final["body_markdown"]
    assert "Habits beat features, every time." not in final["body_markdown"]
    assert repairer.calls == []
    assert len(humanizer.calls) == PARTS


async def test_link_lost_before_humanization_stays_reported_after_it():
    """A link the repair loop could not place must not drop out of the baseline at humanize."""
    original = _article()
    state = _state(original)  # inventory recorded with both links
    state["content"]["final_content"] = _article(body_markdown=_body(internal="Clean data first."))
    humanizer = _fake_model(_echo())
    repairer = _fake_model(_echo())  # cannot place it either
    with (
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
        patch.object(repair_module, "load_content_model", return_value=repairer),
    ):
        humanized = await humanize_content(state)
        inventory = {r["url"] for r in humanized["content"]["generation_meta"]["link_inventory"]}
        assert INTERNAL in inventory
        final = await final_validate_content({**state, **humanized})
    failed = final["content"]["review"]["final_validation"]["failed_checks"]
    assert "links_preserved" in _failing(failed)
    assert INTERNAL_ANCHOR in next(c for c in failed if c["name"] == "links_preserved")["detail"]


# ── 5. repair converges on the first attempt ────────────────────────────────


def _with_fabricated_citation() -> dict:
    return _article(
        body_markdown=_body().replace(
            _para(5), f"{_para(5)} A [recent survey]({FABRICATED}) says most teams agree."
        ),
        outbound_links=[
            {"url": CITATION, "anchor_text": CITATION_ANCHOR},
            {"url": FABRICATED, "anchor_text": "recent survey"},
        ],
    )


@pytest.mark.parametrize("content_type", REPRESENTATIVE_TYPES)
async def test_first_repair_resolves_the_failure_and_keeps_valid_links(content_type):
    """The repair removes the fabricated citation but, as models do, also drops a valid link."""
    article = _with_fabricated_citation()
    repairer = _fake_model(
        _echo(
            **{
                f" A [recent survey]({FABRICATED}) says most teams agree.": "",
                f"[{INTERNAL_ANCHOR}]({INTERNAL})": INTERNAL_ANCHOR,
            }
        ),
        content_type,
    )
    humanizer = _fake_model(_echo(), content_type)
    with (
        patch.object(repair_module, "load_content_model", return_value=repairer),
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
    ):
        out = await _run_pipeline(_state(article, content_type))

    review = out["content"]["review"]
    assert review["repair_attempts"] == 1, review["repair_history"]
    assert len(repairer.calls) == 1
    assert review["repair_history"][0]["accepted"] is True
    assert review["repair_history"][0]["unresolved_checks"] == []
    assert review["validation"]["passed"] is True

    final = out["content"]["final_content"]
    assert FABRICATED not in final["body_markdown"]  # invalid link removable
    assert FABRICATED not in {lnk["url"] for lnk in final["outbound_links"]}
    assert {normalize_url(INTERNAL), normalize_url(CITATION)} <= present_urls(final)
    assert f"\n\n[{INTERNAL_ANCHOR}]({INTERNAL})" not in final["body_markdown"]


async def test_repair_prompt_carries_the_links_to_keep_and_a_length_guard():
    article = _with_fabricated_citation()
    repairer = _fake_model(
        _echo(**{f" A [recent survey]({FABRICATED}) says most teams agree.": ""})
    )
    state = _state(article)
    validated = await validate_content(state)
    with patch.object(repair_module, "load_content_model", return_value=repairer):
        await repair_content(validated)
    prompt = _human_text(repairer.calls[0])
    assert "LINKS THAT MUST SURVIVE" in prompt
    assert f"[{INTERNAL_ANCHOR}]({INTERNAL})" in prompt
    assert f"({CITATION})" in prompt.split("LINKS THAT MUST SURVIVE")[1]
    assert FABRICATED not in prompt.split("LINKS THAT MUST SURVIVE")[1].split("LENGTH")[0]
    assert "LENGTH — the article is currently" in prompt


async def test_already_valid_content_is_not_repaired_or_rewritten_by_validation():
    article = _article()
    repairer = _fake_model(_echo())
    with patch.object(repair_module, "load_content_model", return_value=repairer):
        validated = await validate_content(_state(article))
    validation = validated["content"]["review"]["validation"]
    assert validation["passed"] and not validation["repair_required"]
    assert validation_router(validated) == "humanize_content"
    final = validated["content"]["final_content"]
    assert final["body_markdown"] == article["body_markdown"]
    assert final["introduction"] == article["introduction"]
    assert repairer.calls == []


async def test_repair_that_breaks_a_passing_check_keeps_the_part_that_broke_nothing():
    """The fix is in one paragraph, the damage in others: the fix stays (rext-control#818)."""
    article = _with_fabricated_citation()
    # Removes the fabricated citation, and also strips the focus keyphrase from the body.
    repairer = _fake_model(
        _echo(
            **{
                f" A [recent survey]({FABRICATED}) says most teams agree.": "",
                "crm software": "the tool",
                "CRM Software": "The Tool",
            }
        )
    )
    with patch.object(repair_module, "load_content_model", return_value=repairer):
        first = await repair_content(await validate_content(_state(article)))

    (attempt,) = first["content"]["review"]["repair_history"]
    assert attempt["accepted"] is True
    assert attempt["regressed_checks"]  # what the repair as returned broke
    assert attempt["salvaged"]["how"] == "blocks" and attempt["salvaged"]["kept"] == 1
    assert attempt["unresolved_checks"] == [] and attempt["lost_checks"] == []
    body = first["content"]["final_content"]["body_markdown"]
    assert FABRICATED not in body  # the fix is kept
    assert "crm software" in body and "the tool" not in body  # the damage is not
    passed = await validate_content(first)
    assert passed["content"]["review"]["validation"]["passed"]
    assert len(repairer.calls) == 1  # no second attempt was needed


async def test_repair_with_no_harmless_part_is_discarded_and_the_retry_is_told_why():
    article = _with_fabricated_citation()
    survey = f" A [recent survey]({FABRICATED}) says most teams agree."

    def responder(calls, messages):
        answer = _echo(**{survey: ""})(calls, messages)
        if len(calls) == 1:
            # A rewrite that can't be taken apart: the paragraphs run together, and the
            # focus keyphrase is gone from all of it.
            for field in ("introduction", "body_markdown"):
                answer[field] = (
                    answer[field]
                    .replace("\n\n", "\n")
                    .replace("crm software", "the tool")
                    .replace("CRM Software", "The Tool")
                )
        return answer

    repairer = _fake_model(responder)
    state = _state(article)
    with patch.object(repair_module, "load_content_model", return_value=repairer):
        first = await repair_content(await validate_content(state))
        history = first["content"]["review"]["repair_history"]
        assert history[0]["accepted"] is False
        assert "salvaged" not in history[0]
        # Nothing was accepted: the pre-repair article stands.
        assert first["content"]["final_content"]["body_markdown"] == article["body_markdown"]

        second_state = await validate_content(first)
        assert validation_router(second_state) == "repair_content"  # it has not had its turn
        second = await repair_content(second_state)

    retry_prompt = _human_text(repairer.calls[1])
    assert "PREVIOUS REPAIR ATTEMPT FAILED" in retry_prompt
    assert second["content"]["review"]["repair_history"][1]["accepted"] is True
    assert FABRICATED not in second["content"]["final_content"]["body_markdown"]
    passed = await validate_content(second)
    assert passed["content"]["review"]["validation"]["passed"]


async def test_repair_does_not_undo_a_link_fixed_by_a_previous_repair():
    """An approved link embedded by attempt 1 is protected from attempt 2 onward."""
    article = _article(
        body_markdown=_body(internal="Clean the data before any import."), internal_links=[]
    )
    embedded = f"Clean the data with [{INTERNAL_ANCHOR}]({INTERNAL}) before any import."

    def responder(calls, messages):
        if len(calls) == 1:
            return _echo(**{"Clean the data before any import.": embedded})(calls, messages)
        return _echo(**{embedded: "Clean the data before any import."})(calls, messages)

    repairer = _fake_model(responder)
    with patch.object(repair_module, "load_content_model", return_value=repairer):
        first = await repair_content(await validate_content(_state(article)))
        assert INTERNAL in first["content"]["final_content"]["body_markdown"]
        inventory_urls = {r["url"] for r in first["content"]["generation_meta"]["link_inventory"]}
        assert INTERNAL in inventory_urls
        # Force a second repair pass on unrelated grounds and let the model drop the link.
        forced = await validate_content(first)
        forced["content"]["review"]["validation"]["failed_checks"] = [
            {"name": "unsupported_claims", "passed": False, "severity": "blocking", "detail": "x"}
        ]
        second = await repair_content(forced)
    assert INTERNAL in second["content"]["final_content"]["body_markdown"]


# ── 6. word count belongs to humanization ────────────────────────────────────


def _short_article_outline() -> dict:
    # Target well above the article's length so word_count_band is the only failure.
    return _outline(target_word_count=round(_words(_article()) * 1.25))


def _in_band_body_responder(extra_paragraphs: int) -> Callable:
    def responder(calls, messages):
        out = _echo()(calls, messages)
        out["body_markdown"] = _body(extra=extra_paragraphs)
        return out

    def part(messages):
        # A part comes back as long as it was asked to: sentences added until it is in its range.
        text = _part_text(messages)
        low, high = _asked_range(messages)
        added = 0
        while len(text.split()) < (low + high) // 2:
            text += " " + _EXTRA_SENTENCES[added % 4]
            added += 1
        return text

    responder.part = part
    return responder


@pytest.mark.parametrize("content_type", REPRESENTATIVE_TYPES)
async def test_word_count_only_failure_never_calls_repair_and_humanization_fixes_it(content_type):
    outline = _short_article_outline()
    article = _article()
    low, high = v.compute_word_target_band(outline["target_word_count"])
    assert _words(article) < low

    # Pick enough extra paragraphs to land inside the band.
    extra = next(
        n for n in range(1, 200) if low <= _words(_article(body_markdown=_body(extra=n))) <= high
    )

    # The one rewrite asks every part for more words than it has, and that fixes the length.
    humanizer = _fake_model(_in_band_body_responder(extra), content_type)
    repairer = _fake_model(_echo(), content_type)
    with (
        patch.object(repair_module, "load_content_model", return_value=repairer),
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
    ):
        out = await _run_pipeline(_state(article, content_type, outline))

    review = out["content"]["review"]
    assert repairer.calls == []
    assert review.get("repair_attempts", 0) == 0
    assert _failing(review["validation"]["failed_checks"]) == ["word_count_band"]
    assert review["validation"]["repair_required"] is False
    assert _failing(review["validation"]["deferred_checks"]) == ["word_count_band"]

    assert len(humanizer.calls) == PARTS
    for call in humanizer.calls:
        asked_low, asked_high = _asked_range(call)
        assert asked_low >= len(_part_text(call).split()) and asked_high > asked_low
    final = out["content"]["final_content"]
    assert low <= _words(final) <= high
    assert "word_count_band" not in _failing(review["final_validation"]["failed_checks"])
    assert {normalize_url(INTERNAL), normalize_url(CITATION)} <= present_urls(final)


async def test_humanizer_is_called_exactly_once_even_when_length_is_still_out_of_band():
    outline = _short_article_outline()
    article = _article()
    humanizer = _fake_model(_echo())  # the one rewrite (each part once) leaves the article short
    repairer = _fake_model(_echo())
    with (
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
        patch.object(repair_module, "load_content_model", return_value=repairer),
    ):
        out = await _run_pipeline(_state(article, "blog", outline))

    assert len(humanizer.calls) == PARTS
    assert repairer.calls == []
    review = out["content"]["review"]
    assert _failing(review["final_validation"]["failed_checks"]) == ["word_count_band"]


async def test_mixed_failures_repair_only_the_non_word_count_issue_then_humanize_fixes_length():
    outline = _short_article_outline()
    article = _with_fabricated_citation()
    low, high = v.compute_word_target_band(outline["target_word_count"])
    extra = next(
        n for n in range(1, 200) if low <= _words(_article(body_markdown=_body(extra=n))) <= high
    )

    repairer = _fake_model(
        _echo(**{f" A [recent survey]({FABRICATED}) says most teams agree.": ""})
    )

    humanizer = _fake_model(_in_band_body_responder(extra))
    with (
        patch.object(repair_module, "load_content_model", return_value=repairer),
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
    ):
        out = await _run_pipeline(_state(article, "blog", outline))

    review = out["content"]["review"]
    assert len(humanizer.calls) == PARTS
    assert len(repairer.calls) == 1
    issues = _human_text(repairer.calls[0]).split("ISSUES TO FIX:")[1].split("Title (READ-ONLY")[0]
    assert "facts_and_external_links" in issues
    assert "word_count_band" not in issues
    assert review["repair_attempts"] == 1
    assert review["repair_history"][0]["targeted_checks"] == ["facts_and_external_links"]
    # After the one repair only word count remains, and it does not route back to repair.
    assert _failing(review["validation"]["failed_checks"]) == ["word_count_band"]
    final = out["content"]["final_content"]
    assert low <= _words(final) <= high
    assert FABRICATED not in final["body_markdown"]
    assert review["final_validation"]["passed"], review["final_validation"]["failed_checks"]


def test_word_count_is_the_only_humanization_owned_check():
    assert HUMANIZATION_OWNED_CHECKS == ("word_count_band",)
    assert v.check_word_count_band in v.CHECK_REGISTRY
    assert v.check_links_preserved in v.CHECK_REGISTRY
    assert v.check_links_preserved in v.FINAL_VALIDATE_CHECKS


def test_router_still_repairs_validations_recorded_before_repair_required_existed():
    legacy = {"content": {"review": {"validation": {"passed": False, "gave_up": False}}}}
    assert validation_router(legacy) == "repair_content"


async def test_run_targeted_repair_makes_no_call_for_word_count_alone():
    repairer = _fake_model(_echo())
    with patch.object(repair_module, "load_content_model", return_value=repairer):
        result = await repair_module.run_targeted_repair(
            final_content=_article(),
            content_type="blog",
            failed_checks=[{"name": "word_count_band", "detail": "100 words outside band"}],
        )
    assert result is None and repairer.calls == []


# ── 7. the rewrite, one part at a time (rext-control#787) ────────────────────


def _as_the_model_answers(messages, share: float) -> str:
    """A part back the way the rewrite's model returns one: over the middle of the range it was
    given by the share the rewrite allows for (section_rewrite's STATED_SHARE constants), so at
    the length that was wanted from it. Sentences are dropped from its end, or added."""
    text = _part_text(messages)
    low, high = _asked_range(messages)
    wanted = round((low + high) / 2 / share)
    heading, _, prose = text.partition("\n\n") if text.startswith("#") else ("", "", text)
    sentences = re.split(r"(?<=[.!?])\s+", prose.replace("\n\n", " "))
    while len(" ".join(sentences).split()) > wanted and len(sentences) > 1:
        sentences.pop()
    prose = " ".join(sentences)
    while len(prose.split()) < wanted - 12:
        prose += " " + _EXTRA_SENTENCES[len(prose) % 4]
    return f"{heading}\n\n{prose}" if heading else prose


async def test_an_article_over_its_range_comes_back_inside_it_part_by_part():
    """The whole-article rewrite was told to trim and came back longer (staging: 1,493 words
    became 2,019). Each part is told its own length, and the article is the sum of them."""
    article = _article()
    outline = _outline(target_word_count=round(_words(article) / 1.2))
    low, high = v.compute_word_target_band(outline["target_word_count"])
    assert _words(article) > high
    responder = _echo()
    responder.part = lambda messages: _as_the_model_answers(messages, STATED_SHARE_TO_CUT)
    humanizer = _fake_model(responder)

    with (
        patch.object(repair_module, "load_content_model", return_value=_fake_model(_echo())),
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
    ):
        out = await _run_pipeline(_state(article, "blog", outline))

    assert len(humanizer.calls) == PARTS
    for call in humanizer.calls:
        assert _asked_range(call)[1] < len(_part_text(call).split())
    final = out["content"]["final_content"]
    assert low <= _words(final) <= high
    assert "word_count_band" not in _failing(
        out["content"]["review"]["final_validation"]["failed_checks"]
    )
    # Its sections are the ones it had, under the headings they were drafted with.
    assert re.findall(r"(?m)^## .+$", final["body_markdown"]) == re.findall(
        r"(?m)^## .+$", article["body_markdown"]
    )


async def test_a_part_that_comes_back_far_too_long_is_kept_as_it_was_drafted():
    article = _article()

    def part(messages):
        text = _part_text(messages)
        if text.startswith("## Reports Worth Reading Every Monday"):
            return text + " " + " ".join(_EXTRA_SENTENCES * 6)
        return text.replace("Most small teams", "Nearly every small team")

    responder = _echo()
    responder.part = part
    with (
        patch.object(repair_module, "load_content_model", return_value=_fake_model(_echo())),
        patch.object(humanize_module, "load_humanize_model", return_value=_fake_model(responder)),
    ):
        out = await _run_pipeline(_state(article))

    body = out["content"]["final_content"]["body_markdown"]
    drafted = article["body_markdown"].split("## Reports Worth Reading Every Monday")[1]
    assert body.split("## Reports Worth Reading Every Monday")[1].strip() == drafted.strip()
    assert "Nearly every small team" in body
    assert _EXTRA_SENTENCES[0] not in body


async def test_a_body_with_nothing_to_split_is_rewritten_whole_as_before():
    article = _article(body_markdown=_one_section_body())
    humanizer = _fake_model(_echo())

    with (
        patch.object(repair_module, "load_content_model", return_value=_fake_model(_echo())),
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
    ):
        await _run_pipeline(_state(article))

    humanizer.with_structured_output.assert_called_once()
    assert len(humanizer.calls) == 1
    assert "Body (Markdown):" in _human_text(humanizer.calls[0])


async def test_a_page_whose_every_part_is_too_short_to_send_is_rewritten_whole():
    """Review round 2: several two-line sections under a one-line introduction. By section no
    part of it is long enough to be sent, so nothing was rewritten at all; the whole-article
    rewrite takes it, as it did before."""
    article = _article(
        introduction="Sign in or reset your password in under a minute.",
        body_markdown=(
            "## Sign In\n\nOpen the app and enter your email address.\n\n"
            "## Reset a Password\n\nUse the link under the sign-in button."
        ),
    )
    humanizer = _fake_model(_echo())

    with (
        patch.object(repair_module, "load_content_model", return_value=_fake_model(_echo())),
        patch.object(humanize_module, "load_humanize_model", return_value=humanizer),
    ):
        await _run_pipeline(_state(article))

    humanizer.with_structured_output.assert_called_once()
    assert len(humanizer.calls) == 1
    assert "Body (Markdown):" in _human_text(humanizer.calls[0])
